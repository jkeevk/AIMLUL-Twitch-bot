import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitchio import Message

from src.bot.twitch_bot import TwitchBot
from src.commands.triggers.text_triggers import build_triggers
from src.utils.token_manager import TokenManager


@pytest.fixture
def mock_token_manager() -> TokenManager:
    """Returns a mocked TokenManager with async refresh methods and dummy tokens."""
    tm = MagicMock(spec=TokenManager)
    tm.tokens = {"BOT_TOKEN": MagicMock(client_id="cid", client_secret="csecret")}
    tm.refresh_access_token = AsyncMock(return_value="new_token")
    tm.has_streamer_token = MagicMock(return_value=True)
    return tm


@pytest.fixture
def bot_instance(mock_token_manager: TokenManager) -> TwitchBot:
    """Returns a TwitchBot instance with all external dependencies mocked."""
    with patch(
        "src.bot.twitch_bot.load_settings",
        return_value={
            "channels": ["#test_channel"],
            "database": {"dsn": "sqlite+aiosqlite:///:memory:"},
            "refresh_token_delay_time": 0.01,
        },
    ):
        bot = TwitchBot(token_manager=mock_token_manager, bot_token="initial_token")

    bot.db = MagicMock()
    bot.db.connect = AsyncMock()
    bot.db.close = AsyncMock()
    bot.command_handler = MagicMock()
    bot.eventsub.setup = AsyncMock()
    bot.api = MagicMock()
    bot.handle_commands = AsyncMock()
    bot.triggers_map = build_triggers(bot)

    return bot


@pytest.mark.asyncio
async def test_event_ready_starts_token_refresh(bot_instance: TwitchBot):
    """Verify that event_ready connects to DB, sets up EventSub, and starts the periodic token refresh task."""
    await bot_instance.event_ready()

    bot_instance.db.connect.assert_awaited_once()
    bot_instance.eventsub.setup.assert_awaited_once()
    assert bot_instance.token_refresh_task is not None
    assert not bot_instance.token_refresh_task.done()

    bot_instance.token_refresh_task.cancel()
    with patch("asyncio.sleep", return_value=AsyncMock()):
        with pytest.raises(asyncio.CancelledError):
            await bot_instance.token_refresh_task


@pytest.mark.asyncio
async def test_event_message_calls_trigger_handler(bot_instance: TwitchBot):
    """
    Verify that event_message calls the correct trigger handler.

    when a message matches a trigger keyword (case-insensitive).
    """
    trigger_key = bot_instance.triggers["gnome_keywords"][0]

    mock_message = MagicMock(spec=Message)
    mock_message.content = trigger_key.upper()
    mock_message.echo = False
    mock_message.author.name = "test_user"

    handler_mock = AsyncMock()
    bot_instance.triggers["handlers"]["gnome"] = handler_mock

    await bot_instance.event_message(mock_message)
    handler_mock.assert_awaited_once_with(mock_message)


@pytest.mark.asyncio
async def test_event_message_calls_handle_commands(bot_instance: TwitchBot):
    """Verify that event_message calls handle_commands when the message does not match any trigger keyword."""
    mock_message = MagicMock(spec=Message)
    mock_message.content = "some random text"
    mock_message.echo = False
    mock_message.author.name = "test_user"

    bot_instance.triggers_map = {}
    await bot_instance.event_message(mock_message)
    bot_instance.handle_commands.assert_awaited_once_with(mock_message)


@pytest.mark.asyncio
async def test_command_activation_deactivation(bot_instance: TwitchBot):
    """Test bot activation and deactivation commands: bot_sleep should deactivate, bot_wake should reactivate."""
    ctx = AsyncMock()
    ctx.author.name = "admin_user"

    with patch("src.bot.twitch_bot.is_admin", return_value=True):
        await bot_instance.bot_sleep(ctx)
        assert not bot_instance.active
        ctx.send.assert_awaited_once_with("banka Алибидерчи! Бот выключен.")

        ctx.send.reset_mock()
        await bot_instance.bot_wake(ctx)
        assert bot_instance.active
        ctx.send.assert_awaited_once_with("deshovka Бот снова активен!")


@pytest.mark.asyncio
async def test_close_cancels_token_task_and_closes_db(bot_instance: TwitchBot):
    """Test that close() cancels the token refresh task and closes the database."""
    bot_instance.token_refresh_task = asyncio.create_task(asyncio.sleep(10))
    bot_instance._closing = asyncio.Event()

    if hasattr(bot_instance, "_connection"):
        bot_instance._connection = AsyncMock()
        bot_instance._connection._close = AsyncMock()

    await bot_instance.close()
    assert bot_instance.token_refresh_task.cancelled()
    bot_instance.db.close.assert_awaited_once()
