import asyncio
from datetime import datetime
from datetime import time as dtime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from twitchio import Message

from src.bot.manager import BotManager
from src.bot.twitch_bot import TwitchBot
from src.utils.token_manager import TokenManager


@pytest.mark.asyncio
async def test_event_ready_starts_token_refresh(bot_manager: BotManager):
    """Verify that event_ready triggers DB connect, EventSub setup, and starts token refresh a task via manager."""
    bot_manager.bot.db.connect = AsyncMock()
    bot_manager.bot.eventsub.setup = AsyncMock()
    bot_manager._token_refresh_loop = AsyncMock()

    await bot_manager.bot.event_ready()

    bot_manager.bot.db.connect.assert_awaited_once()
    bot_manager.bot.eventsub.setup.assert_awaited_once()

    bot_manager.token_refresh_task = asyncio.create_task(bot_manager._token_refresh_loop())

    assert bot_manager.token_refresh_task is not None
    assert not bot_manager.token_refresh_task.done()

    bot_manager.token_refresh_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await bot_manager.token_refresh_task


@pytest.mark.asyncio
async def test_event_message_calls_trigger_handler(bot_instance: TwitchBot):
    """
    Verify that event_message calls the correct trigger handler.

    This happens when a message matches a trigger keyword (case-insensitive).
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
    bot_instance.handle_commands = AsyncMock()

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
async def test_close_cancels_token_task_and_closes_db(bot_manager: BotManager):
    """Test that stopping the manager cancels the token refresh task and closes the database."""
    bot_manager.refresh_task = asyncio.create_task(asyncio.sleep(10))

    bot_manager.bot = MagicMock(spec=TwitchBot)
    bot_manager.bot.db = MagicMock()
    bot_manager.bot.db.close = AsyncMock()

    async def close_side_effect():
        await bot_manager.bot.db.close()

    bot_manager.bot.close = AsyncMock(side_effect=close_side_effect)

    await bot_manager.stop()

    assert bot_manager.refresh_task.cancelled()
    bot_manager.bot.db.close.assert_awaited_once()
    bot_manager.bot.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchdog_restarts_bot_after_unhealthy(mock_token_manager: TokenManager):
    """Test that watchdog triggers bot restart after 3 consecutive unhealthy checks."""
    manager = BotManager(token_manager=mock_token_manager)
    manager._running = True
    manager.bot = MagicMock(spec=TwitchBot)
    manager.bot.is_connected = False
    manager.restart_bot = AsyncMock()

    asyncio_sleep_original = asyncio.sleep
    asyncio.sleep = AsyncMock()

    for _ in range(3):
        healthy = await manager._check_bot_health()
        if not healthy:
            manager._websocket_error_count += 1
            if manager._websocket_error_count >= 3:
                await manager.restart_bot()
        else:
            manager._websocket_error_count = 0

    assert manager._websocket_error_count == 3
    manager.restart_bot.assert_awaited_once()

    asyncio.sleep = asyncio_sleep_original


@pytest.mark.asyncio
async def test_healthcheck_returns_ok_when_bot_healthy(mock_token_manager: TokenManager):
    """Test that /health returns 200 if bot is running and websocket is healthy."""
    manager = BotManager(token_manager=mock_token_manager)
    manager._running = True
    manager.bot = MagicMock(spec=TwitchBot)
    manager.bot.is_connected = True
    manager._check_websocket = AsyncMock(return_value=True)

    request = MagicMock()
    response = await manager._handle_health(request)

    assert isinstance(response, web.Response)
    assert response.status == 200
    text = response.text
    assert "OK" in text


@pytest.mark.asyncio
async def test_healthcheck_returns_unhealthy_when_bot_not_connected(mock_token_manager: TokenManager):
    """Test that /health returns 500 if bot is not running or websocket unhealthy."""
    manager = BotManager(token_manager=mock_token_manager)
    manager._running = True
    manager.bot = MagicMock(spec=TwitchBot)
    manager.bot.is_connected = False
    manager._check_websocket = AsyncMock(return_value=True)

    request = MagicMock()
    response = await manager._handle_health(request)

    assert isinstance(response, web.Response)
    assert response.status == 500
    text = response.text
    assert "UNHEALTHY" in text


@pytest.mark.asyncio
async def test_scheduled_bot_activation_sends_message(mock_token_manager: TokenManager):
    """Test bot disables itself during offline schedule and sends a notification."""
    bot = TwitchBot(token_manager=mock_token_manager, bot_token="fake_token")
    bot.active = True
    bot.is_connected = True
    bot.db = MagicMock()
    bot.db.set_scheduled_offline = AsyncMock()

    bot.send_message = AsyncMock()

    manager = BotManager(token_manager=mock_token_manager)
    manager.bot = bot

    bot.config["schedule"] = {
        "enabled": True,
        "offline_from": dtime(0, 0),
        "offline_to": dtime(23, 59),
        "timezone": "UTC",
    }

    fake_now_time = dtime(12, 0)

    def in_offline_window(now, start, end):
        if start < end:
            return start <= now < end
        return now >= start or now < end

    schedule = bot.config.get("schedule", {})
    off_time = schedule.get("offline_from")
    on_time = schedule.get("offline_to")

    if in_offline_window(fake_now_time, off_time, on_time):
        bot.active = False
        bot.scheduled_offline = True
        await bot.send_message("Бот автоматически отключен по расписанию")
        await bot.db.set_scheduled_offline(datetime.now().date(), sent_message=True)

    assert bot.active is False
    assert bot.scheduled_offline is True
    bot.db.set_scheduled_offline.assert_awaited_once()
    bot.send_message.assert_awaited_once_with("Бот автоматически отключен по расписанию")
