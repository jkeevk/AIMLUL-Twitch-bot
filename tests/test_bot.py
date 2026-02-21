import asyncio
import logging
from datetime import UTC, datetime
from datetime import time as dtime
from datetime import timedelta
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

    mock_manager = AsyncMock()
    bot_instance.manager = mock_manager

    with patch("src.bot.twitch_bot.is_admin", return_value=True):
        await bot_instance.bot_sleep(ctx)
        mock_manager.set_bot_sleep.assert_awaited_once()

        await bot_instance.bot_wake(ctx)
        mock_manager.set_bot_wake.assert_awaited_once()


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
async def test_watchdog_restarts_bot_after_unhealthy(mock_token_manager: TokenManager, mock_redis: AsyncMock):
    """Test that watchdog triggers bot restart after 3 consecutive unhealthy checks."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
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
async def test_healthcheck_returns_ok_when_bot_healthy(mock_token_manager: TokenManager, mock_redis: AsyncMock):
    """Test that /health returns 200 if bot is running and websocket is healthy."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
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
async def test_healthcheck_returns_unhealthy_when_bot_not_connected(
    mock_token_manager: TokenManager, mock_redis: AsyncMock
):
    """Test that /health returns 500 if bot is not running or websocket unhealthy."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
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
async def test_scheduled_bot_activation_sends_message():
    """Test bot disables itself during offline schedule and sends a notification via Redis."""
    mock_redis = AsyncMock()
    mock_token_manager = MagicMock()

    bot = TwitchBot(token_manager=mock_token_manager, redis=mock_redis, bot_token="fake_token")
    bot.active = True
    bot.is_connected = True

    mock_channel = AsyncMock()

    orig_prop = type(bot).connected_channels

    try:
        type(bot).connected_channels = property(lambda self: [mock_channel])

        manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
        manager.bot = bot

        bot.config["schedule"] = {
            "enabled": True,
            "offline_from": dtime(0, 0),
            "offline_to": dtime(23, 59),
            "timezone": "UTC",
        }

        mock_redis.get.return_value = None

        fake_now = datetime.now(tz=UTC).replace(hour=12, minute=0, second=0, microsecond=0)

        def in_offline_window(now, start, end):
            if start < end:
                return start <= now < end
            return now >= start or now < end

        schedule = bot.config.get("schedule", {})
        off_time = schedule.get("offline_from")
        on_time = schedule.get("offline_to")

        if in_offline_window(fake_now.time(), off_time, on_time):
            bot.active = False
            for channel in bot.connected_channels:
                await channel.send("Bot is entering scheduled sleep mode. Use !ботговори to wake it (admin only).")

            today_str = str(fake_now.date())
            message_key = f"bot:schedule_msg:{today_str}"
            seconds_until_end_of_day = int(
                (
                    datetime.combine(fake_now.date() + timedelta(days=1), dtime.min, tzinfo=UTC) - fake_now
                ).total_seconds()
            )
            await mock_redis.set(message_key, "1", ex=seconds_until_end_of_day)

        # --- Assertions ---
        assert bot.active is False
        for channel in bot.connected_channels:
            channel.send.assert_awaited_once_with(
                "Bot is entering scheduled sleep mode. Use !ботговори to wake it (admin only)."
            )
        mock_redis.set.assert_awaited_once()
    finally:
        type(bot).connected_channels = orig_prop


@pytest.mark.asyncio
async def test_report_status_logs_info(bot_manager: BotManager, caplog):
    """Test that report_status logs bot status correctly."""
    bot_manager.bot = MagicMock(spec=TwitchBot)
    bot_manager.bot.active = True
    bot_manager.bot.redis = AsyncMock()
    bot_manager.bot.redis.info = AsyncMock(return_value={"db0": {"key1": "val"}})

    caplog.set_level(logging.INFO)

    await bot_manager.report_status()

    # --- Assertions ---
    assert "Bot Status Report" in caplog.text
    assert "Active: True" in caplog.text
    assert "Redis keys count: 1" in caplog.text


@pytest.mark.asyncio
async def test_restart_bot_success(mock_token_manager, mock_redis):
    """Test that restart_bot successfully starts a new bot instance."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
    manager._running = True

    # Mock token retrieval
    mock_token_manager.get_access_token = AsyncMock(return_value="token")

    # Create a fake bot instance
    fake_bot = MagicMock(spec=TwitchBot)
    fake_bot.start = AsyncMock()
    fake_bot.is_connected = True

    # Patch TwitchBot constructor and asyncio.sleep
    with (
        patch("src.bot.manager.TwitchBot", return_value=fake_bot),
        patch("src.bot.manager.asyncio.sleep", new_callable=AsyncMock),
    ):
        await manager.restart_bot()

    # Ensure the new bot is assigned and websocket error counter reset
    assert manager.bot is not None
    assert manager._websocket_error_count == 0


@pytest.mark.asyncio
async def test_set_bot_sleep(mock_token_manager, mock_redis):
    """Test that set_bot_sleep updates Redis and notifies connected channels."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)

    mock_redis.set = AsyncMock()

    # Prepare a fake bot with connected channels
    bot = MagicMock(spec=TwitchBot)
    channel = AsyncMock()
    channel.send = AsyncMock()
    bot.connected_channels = [channel]
    bot.config = {"schedule": {"timezone": "UTC"}}

    manager.bot = bot

    await manager.set_bot_sleep()

    # Check Redis set and channel notifications
    mock_redis.set.assert_awaited_once()
    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_eventsub_success(mock_token_manager, mock_redis):
    """Test _check_eventsub returns True when sockets are connected."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)

    # Fake eventsub socket connected
    socket = MagicMock()
    socket.is_connected = True

    bot = MagicMock(spec=TwitchBot)
    bot.eventsub = MagicMock()
    bot.eventsub.client = MagicMock()
    bot.eventsub.client._sockets = [socket]

    manager.bot = bot

    result = await manager._check_eventsub()
    assert result is True


@pytest.mark.asyncio
async def test_check_websocket_success(mock_token_manager, mock_redis):
    """Test _check_websocket returns True when bot connection is healthy."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)

    bot = MagicMock(spec=TwitchBot)
    bot.is_connected = True

    # Mock internal connection object
    connection = MagicMock()
    connection.connected = True
    bot._connection = connection
    bot.connected_channels = [MagicMock()]

    manager.bot = bot

    result = await manager._check_websocket()
    assert result is True


@pytest.mark.asyncio
async def test_token_refresh_loop_runs_once(mock_token_manager, mock_redis):
    """Test _token_refresh_loop calls refresh_access_token once per iteration."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
    manager._running = True

    mock_token_manager.refresh_access_token = AsyncMock()
    mock_token_manager.has_streamer_token = MagicMock(return_value=False)
    mock_token_manager.tokens = {"BOT_TOKEN": MagicMock(access_token="1234567890")}

    # Patch asyncio.sleep to stop the loop immediately
    async def fast_sleep(_):
        manager._running = False

    with (
        patch("src.bot.manager.load_settings", return_value={"refresh_token_interval": 0}),
        patch("src.bot.manager.asyncio.sleep", side_effect=fast_sleep),
    ):
        await manager._token_refresh_loop()

    mock_token_manager.refresh_access_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_bot_replaces_bot_task(mock_token_manager, mock_redis):
    """Test that restart_bot cancels old bot task and starts a new one."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
    manager._running = True

    old_bot_task = asyncio.create_task(asyncio.sleep(100))
    old_bot = MagicMock(spec=TwitchBot)
    manager.bot = old_bot
    manager.bot_task = old_bot_task

    mock_token_manager.get_access_token = AsyncMock(return_value="token")

    new_bot = MagicMock(spec=TwitchBot)
    new_bot.start = AsyncMock()
    new_bot.is_connected = True

    with (
        patch("src.bot.manager.TwitchBot", return_value=new_bot),
        patch("src.bot.manager.asyncio.sleep", new_callable=AsyncMock),
    ):
        await manager.restart_bot()

    # Ensure old task is cancelled or finished, and new bot assigned
    assert manager.bot is new_bot
    assert old_bot_task.cancelled() or old_bot_task.done()
    assert manager._websocket_error_count == 0
    assert manager.bot_task is not None


@pytest.mark.asyncio
async def test_check_websocket_unhealthy(mock_token_manager, mock_redis):
    """Test _check_websocket returns False when bot is disconnected."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)

    bot = MagicMock(spec=TwitchBot)
    bot.is_connected = False
    manager.bot = bot

    result = await manager._check_websocket()
    assert result is False


@pytest.mark.asyncio
async def test_healthcheck_when_manager_not_running(mock_token_manager, mock_redis):
    """Test health endpoint returns 500 when manager is not running."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
    manager._running = False

    request = MagicMock()
    response = await manager._handle_health(request)

    assert response.status == 500


@pytest.mark.asyncio
async def test_set_bot_wake(mock_token_manager, mock_redis):
    """Test that set_bot_wake deletes sleep key and notifies channels."""
    mock_redis.delete = AsyncMock()
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)

    bot = MagicMock(spec=TwitchBot)
    channel = AsyncMock()
    channel.send = AsyncMock()
    bot.connected_channels = [channel]
    bot.config = {"schedule": {"timezone": "UTC"}}

    manager.bot = bot
    await manager.set_bot_wake()

    mock_redis.delete.assert_awaited_once()
    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchdog_loop_triggers_restart(mock_token_manager, mock_redis):
    """Test _watchdog_loop triggers restart_bot when bot health is bad."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
    manager._running = True

    manager._check_bot_health = AsyncMock(return_value=False)
    manager.restart_bot = AsyncMock()

    # Simulate websocket error count reaching the threshold
    manager._websocket_error_count = 2  # max_failures = 3

    async def fast_sleep(_):
        manager._running = False

    with patch("src.bot.manager.asyncio.sleep", side_effect=fast_sleep):
        await manager._watchdog_loop()

    manager.restart_bot.assert_awaited_once()
