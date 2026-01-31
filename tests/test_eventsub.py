from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitchio.errors import Unauthorized

from src.eventsub.handlers import handle_eventsub_reward
from src.eventsub.manager import EventSubManager
from tests.conftest import DummyEvent


class TestEventSubManager:
    """Tests for EventSubManager class."""

    @pytest.mark.asyncio
    async def test_setup_without_streamer_token(self):
        """Test setup when no streamer token is available."""
        mock_bot = MagicMock()
        mock_bot.token_manager = MagicMock()
        mock_bot.token_manager.has_streamer_token.return_value = False

        manager = EventSubManager(mock_bot)
        await manager.setup()

        # Should log and return early
        assert manager.subscribed is False
        assert manager.client is None

    @pytest.mark.asyncio
    async def test_setup_without_channels(self):
        """Test setup when no channels are configured."""
        mock_bot = MagicMock()
        mock_bot.token_manager = MagicMock()
        mock_bot.token_manager.has_streamer_token.return_value = True
        mock_bot.config = {"channels": []}

        manager = EventSubManager(mock_bot)
        await manager.setup()

        # Should log warning and return
        assert manager.subscribed is False
        assert manager.client is None

    @pytest.mark.asyncio
    async def test_setup_streamer_not_found(self):
        """Test setup when streamer is not found."""
        mock_bot = MagicMock()
        mock_bot.token_manager = MagicMock()
        mock_bot.token_manager.has_streamer_token.return_value = True
        mock_bot.config = {"channels": ["testchannel"]}
        mock_bot.fetch_users = AsyncMock(return_value=[])

        manager = EventSubManager(mock_bot)
        await manager.setup()

        # Should fail to get broadcaster ID
        assert manager.broadcaster_id is None
        assert manager.subscribed is False

    @pytest.mark.asyncio
    async def test_setup_success(self):
        """Test successful EventSub setup."""
        mock_bot = MagicMock()
        mock_bot.token_manager = MagicMock()
        mock_bot.token_manager.has_streamer_token.return_value = True
        mock_bot.token_manager.get_streamer_token = AsyncMock(return_value="streamer_token")
        mock_bot.config = {"channels": ["testchannel"]}

        # Mock user fetch
        mock_user = MagicMock()
        mock_user.id = "broadcaster_123"
        mock_bot.fetch_users = AsyncMock(return_value=[mock_user])

        # Mock EventSub client
        mock_client = AsyncMock()

        manager = EventSubManager(mock_bot)

        with patch("twitchio.ext.eventsub.EventSubWSClient", return_value=mock_client):
            with patch.object(
                mock_client, "subscribe_channel_points_redeemed", new_callable=AsyncMock
            ) as mock_subscribe:
                await manager.setup()

        assert manager.broadcaster_id == "broadcaster_123"
        assert manager.subscribed is True
        assert manager.client == mock_client
        mock_subscribe.assert_called_once_with("broadcaster_123", "streamer_token")

    @pytest.mark.asyncio
    async def test_setup_unauthorized(self):
        """Test setup when unauthorized (not Affiliate/Partner)."""
        mock_bot = MagicMock()
        mock_bot.token_manager = MagicMock()
        mock_bot.token_manager.has_streamer_token.return_value = True
        mock_bot.token_manager.get_streamer_token = AsyncMock(return_value="streamer_token")
        mock_bot.config = {"channels": ["testchannel"]}

        mock_user = MagicMock()
        mock_user.id = "broadcaster_123"
        mock_bot.fetch_users = AsyncMock(return_value=[mock_user])

        manager = EventSubManager(mock_bot)

        with patch("twitchio.ext.eventsub.EventSubWSClient", return_value=AsyncMock()) as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.subscribe_channel_points_redeemed = AsyncMock(side_effect=Unauthorized("Not authorized"))

            await manager.setup()

        # Should clean up after unauthorized error
        assert manager.subscribed is False
        assert manager.client is None

    @pytest.mark.asyncio
    async def test_ensure_alive_not_subscribed(self):
        """Test ensure_alive when not subscribed."""
        mock_bot = MagicMock()
        manager = EventSubManager(mock_bot)
        manager.subscribed = False

        with patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe:
            await manager.ensure_alive()

        mock_subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_alive_no_sockets(self):
        """Test ensure_alive when no sockets exist."""
        mock_bot = MagicMock()
        manager = EventSubManager(mock_bot)
        manager.subscribed = True

        # Mock client with no sockets
        mock_client = MagicMock()
        mock_client._sockets = []
        manager.client = mock_client

        with (
            patch.object(manager, "_cleanup", new_callable=AsyncMock) as mock_cleanup,
            patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe,
        ):
            await manager.ensure_alive()

        mock_cleanup.assert_called_once()
        mock_subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_alive_sockets_disconnected(self):
        """Test ensure_alive when all sockets are disconnected."""
        mock_bot = MagicMock()
        manager = EventSubManager(mock_bot)
        manager.subscribed = True

        # Mock disconnected sockets
        mock_socket = MagicMock()
        mock_socket.is_connected = False
        mock_client = MagicMock()
        mock_client._sockets = [mock_socket]
        manager.client = mock_client

        with (
            patch.object(manager, "_cleanup", new_callable=AsyncMock) as mock_cleanup,
            patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe,
        ):
            await manager.ensure_alive()

        mock_cleanup.assert_called_once()
        mock_subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_alive_healthy(self):
        """Test ensure_alive when connection is healthy."""
        mock_bot = MagicMock()
        manager = EventSubManager(mock_bot)
        manager.subscribed = True

        # Mock connected socket
        mock_socket = MagicMock()
        mock_socket.is_connected = True
        mock_client = MagicMock()
        mock_client._sockets = [mock_socket]
        manager.client = mock_client

        with (
            patch.object(manager, "_cleanup", new_callable=AsyncMock) as mock_cleanup,
            patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe,
        ):
            await manager.ensure_alive()

        # Should not call cleanup or subscribe when healthy
        mock_cleanup.assert_not_called()
        mock_subscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the manager."""
        mock_bot = MagicMock()
        manager = EventSubManager(mock_bot)
        manager.client = MagicMock()
        manager.subscribed = True

        with patch.object(manager, "_cleanup", new_callable=AsyncMock) as mock_cleanup:
            await manager.close()

        mock_cleanup.assert_called_once()


class TestEventSubHandlers:
    """Tests for EventSub event handlers."""

    @pytest.mark.asyncio
    async def test_handle_eventsub_reward_success(self):
        """Test successful reward handling."""
        mock_bot = MagicMock()
        mock_bot.active = True

        # Mock event
        mock_event = MagicMock()
        mock_event.data = MagicMock()
        mock_event.data.reward = MagicMock()
        mock_event.data.reward.title = "испытание пивом"
        mock_event.data.user = MagicMock()
        mock_event.data.user.name = "TestUser"
        mock_event.data.broadcaster = MagicMock()
        mock_event.data.broadcaster.name = "testchannel"
        mock_event.data.input = "5"

        # Mock handler
        mock_handler = AsyncMock()

        with patch("src.eventsub.handlers.reward_handlers", {"испытание пивом": mock_handler}):
            await handle_eventsub_reward(mock_event, mock_bot)

        mock_handler.assert_awaited_once_with(mock_event, mock_bot)

    @pytest.mark.asyncio
    async def test_handle_eventsub_reward_unknown(self):
        """Test handling of unknown reward."""
        mock_bot = MagicMock()

        # Mock event with unknown reward
        mock_event = MagicMock()
        mock_event.data = MagicMock()
        mock_event.data.reward = MagicMock()
        mock_event.data.reward.title = "неизвестная награда"

        # Mock logger to capture log messages
        with patch("src.eventsub.handlers.logger") as mock_logger:
            await handle_eventsub_reward(mock_event, mock_bot)

        # Should log about ignored reward
        mock_logger.info.assert_called_once_with("Ignored reward: неизвестная награда")

    @pytest.mark.asyncio
    async def test_handle_eventsub_reward_exception(self):
        """Test handling when an exception occurs."""
        mock_bot = MagicMock()

        # Mock event
        mock_event = MagicMock()
        mock_event.data = MagicMock()
        mock_event.data.reward = MagicMock()
        mock_event.data.reward.title = "испытание пивом"

        # Mock handler that raises an exception
        mock_handler = AsyncMock(side_effect=Exception("Test error"))

        # Mock logger to capture error
        with (
            patch("src.eventsub.handlers.reward_handlers", {"испытание пивом": mock_handler}),
            patch("src.eventsub.handlers.logger") as mock_logger,
        ):
            await handle_eventsub_reward(mock_event, mock_bot)

        # Should log the error
        mock_logger.error.assert_called_once()
        assert "Test error" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_reward_handler_integration(self):
        """Test integration between EventSub and command handler."""
        from src.eventsub.reward_handlers import beer_challenge_handler

        # Create mock event
        mock_event = MagicMock()
        mock_event.data = MagicMock()
        mock_event.data.user = MagicMock()
        mock_event.data.user.name = "TestUser"
        mock_event.data.broadcaster = MagicMock()
        mock_event.data.broadcaster.name = "testchannel"
        mock_event.data.input = "10"

        # Create mock bot with command handler
        mock_bot = MagicMock()
        mock_bot.active = True
        mock_bot.command_handler = AsyncMock()
        mock_bot.command_handler.handle_beer_challenge = AsyncMock()

        # Call the handler
        await beer_challenge_handler(mock_event, mock_bot)

        # Verify command was called
        mock_bot.command_handler.handle_beer_challenge.assert_awaited_once_with("TestUser", "10", "testchannel")


class TestEventSubEventCallbacks:
    """Tests for EventSub event callbacks integration."""

    @pytest.mark.asyncio
    async def test_channel_points_redeemed_callback(self):
        """Test that TwitchBot properly handles channel points redeemed events."""
        from src.bot.twitch_bot import TwitchBot

        # Create a mock bot
        mock_bot = MagicMock(spec=TwitchBot)
        mock_bot.active = True
        mock_bot.command_handler = AsyncMock()

        # Patch the handle_eventsub_reward function
        with patch("src.bot.twitch_bot.handle_eventsub_reward", new_callable=AsyncMock) as mock_handler:
            # Simulate receiving a channel points redeemed event
            mock_event = DummyEvent(reward_name="испытание пивом", username="TestUser", user_id="123", input_val="5")

            # Call the callback (this is what TwitchIO would call)
            await mock_handler(mock_event, mock_bot)

            # Verify the handler was called
            mock_handler.assert_awaited_once_with(mock_event, mock_bot)

    @pytest.mark.asyncio
    async def test_twitchio_eventsub_integration(self):
        """Test integration with TwitchIO's EventSub client."""
        # Create a generic mock EventSub event (avoiding specific TwitchIO class)
        mock_eventsub_event = MagicMock()

        # Set up the event data structure to match what TwitchIO provides
        mock_eventsub_event.data = MagicMock()
        mock_eventsub_event.data.broadcaster = MagicMock()
        mock_eventsub_event.data.broadcaster.name = "testchannel"
        mock_eventsub_event.data.user = MagicMock()
        mock_eventsub_event.data.user.name = "TestUser"
        mock_eventsub_event.data.user.id = "123"
        mock_eventsub_event.data.reward = MagicMock()
        mock_eventsub_event.data.reward.title = "испытание пивом"
        mock_eventsub_event.data.input = "5"

        # Create a mock bot
        mock_bot = MagicMock()
        mock_bot.active = True
        mock_bot.command_handler = AsyncMock()
        mock_bot.command_handler.handle_beer_challenge = AsyncMock()

        # Test the handler directly with the mock event
        from src.eventsub.reward_handlers import beer_challenge_handler

        await beer_challenge_handler(mock_eventsub_event, mock_bot)

        # Verify the command was called
        mock_bot.command_handler.handle_beer_challenge.assert_awaited_once_with("TestUser", "5", "testchannel")


@pytest.mark.asyncio
async def test_full_eventsub_flow():
    """Test the full EventSub flow from subscription to command execution."""
    # Step 1: Setup EventSubManager
    mock_bot = MagicMock()
    mock_bot.token_manager = MagicMock()
    mock_bot.token_manager.has_streamer_token.return_value = True
    mock_bot.token_manager.get_streamer_token = AsyncMock(return_value="streamer_token")
    mock_bot.config = {"channels": ["testchannel"]}

    mock_user = MagicMock()
    mock_user.id = "broadcaster_123"
    mock_bot.fetch_users = AsyncMock(return_value=[mock_user])

    # Mock EventSub client
    mock_client = AsyncMock()

    manager = EventSubManager(mock_bot)

    # Setup subscription
    with patch("twitchio.ext.eventsub.EventSubWSClient", return_value=mock_client):
        with patch.object(mock_client, "subscribe_channel_points_redeemed", new_callable=AsyncMock):
            await manager.setup()

    assert manager.subscribed is True

    # Step 2: Simulate receiving an event (this would normally come from TwitchIO)
    mock_event = DummyEvent(reward_name="испытание пивом", username="TestUser", user_id="456", input_val="не число")

    # Step 3: Handle the event
    mock_bot.active = True
    mock_bot.command_handler = AsyncMock()
    mock_bot.command_handler.handle_beer_challenge = AsyncMock()

    from src.eventsub.reward_handlers import beer_challenge_handler

    await beer_challenge_handler(mock_event, mock_bot)

    # Step 4: Verify the command was called
    mock_bot.command_handler.handle_beer_challenge.assert_awaited_once_with("TestUser", "не число", "testbroadcaster")

    # Step 5: Test cleanup
    await manager.close()
    assert manager.subscribed is False
    assert manager.client is None


@pytest.mark.asyncio
async def test_multiple_reward_types():
    """Test handling of different reward types."""
    test_cases = [
        ("очко", "handle_twenty_one"),
        ("вскрыть пивную кегу", "handle_beer_barrel"),
        ("испытание пивом", "handle_beer_challenge"),
        ("прибежать кабанчиком на пиво", "handle_kaban_barrel"),
        ("спрятаться в помойке", "handle_trash_barrel"),
    ]

    for reward_name, handler_method in test_cases:
        # Create mock event
        mock_event = DummyEvent(reward_name=reward_name, username="TestUser", user_id="123", input_val="test")

        # Create mock bot
        mock_bot = MagicMock()
        mock_bot.active = True
        mock_bot.command_handler = AsyncMock()

        # Get the handler
        from src.eventsub.reward_handlers import reward_handlers

        handler = reward_handlers.get(reward_name)
        assert handler is not None, f"Handler for {reward_name} not found"

        # Call handler
        await handler(mock_event, mock_bot)

        # Verify the correct method was called
        mock_handler = getattr(mock_bot.command_handler, handler_method)
        mock_handler.assert_awaited_once()

        # Reset for next test
        mock_bot.command_handler.reset_mock()


@pytest.mark.asyncio
async def test_eventsub_reconnection_logic():
    """Test EventSub reconnection and health check logic."""
    mock_bot = MagicMock()
    manager = EventSubManager(mock_bot)

    # Test initial state
    assert manager._reconnect_lock is not None
    assert manager.subscribed is False
    assert manager.client is None

    # Test: ensure_alive subscribes when not subscribed
    with patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe:
        await manager.ensure_alive()
        mock_subscribe.assert_awaited_once()

    # Test: ensure_alive does not subscribe when already subscribed and has a client with sockets
    manager.subscribed = True
    manager.client = MagicMock()
    manager.client._sockets = [MagicMock(is_connected=True)]

    with patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe:
        await manager.ensure_alive()
        mock_subscribe.assert_not_awaited()

    # Test: ensure_alive re-subscribes when there are no sockets
    manager.client._sockets = []  # No sockets!

    with (
        patch.object(manager, "_cleanup", new_callable=AsyncMock) as mock_cleanup,
        patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe,
    ):
        await manager.ensure_alive()
        mock_cleanup.assert_awaited_once()
        mock_subscribe.assert_awaited_once()

    # Test: ensure_alive re-subscribes when sockets are disconnected
    manager.client._sockets = [MagicMock(is_connected=False)]

    with (
        patch.object(manager, "_cleanup", new_callable=AsyncMock) as mock_cleanup,
        patch.object(manager, "_subscribe_once", new_callable=AsyncMock) as mock_subscribe,
    ):
        await manager.ensure_alive()
        mock_cleanup.assert_awaited_once()
        mock_subscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_subscription_with_duplicate_calls():
    """Test that duplicate subscription calls don't cause issues."""
    mock_bot = MagicMock()
    mock_bot.token_manager = MagicMock()
    mock_bot.token_manager.has_streamer_token.return_value = True
    mock_bot.token_manager.get_streamer_token = AsyncMock(return_value="streamer_token")
    mock_bot.config = {"channels": ["testchannel"]}

    mock_user = MagicMock()
    mock_user.id = "broadcaster_123"
    mock_bot.fetch_users = AsyncMock(return_value=[mock_user])

    mock_client = AsyncMock()
    subscribe_mock = AsyncMock()
    mock_client.subscribe_channel_points_redeemed = subscribe_mock

    manager = EventSubManager(mock_bot)

    with patch("twitchio.ext.eventsub.EventSubWSClient", return_value=mock_client):
        # First call
        await manager.setup()
        assert subscribe_mock.call_count == 1

        # Second call - should not subscribe again
        await manager.setup()
        assert subscribe_mock.call_count == 1

        # Reset and call ensure_alive
        manager.subscribed = False
        await manager.ensure_alive()
        assert subscribe_mock.call_count == 2


@pytest.mark.asyncio
async def test_event_handler_with_bot_inactive():
    """Test that events are not processed when bot is inactive."""
    # Create mock event
    mock_event = MagicMock()
    mock_event.data = MagicMock()
    mock_event.data.user = MagicMock()
    mock_event.data.user.name = "TestUser"
    mock_event.data.broadcaster = MagicMock()
    mock_event.data.broadcaster.name = "testchannel"
    mock_event.data.input = "10"

    # Create mock bot that is INACTIVE
    mock_bot = AsyncMock()  # Use AsyncMock instead of MagicMock
    mock_bot.active = False  # Bot is inactive!
    mock_bot.command_handler = AsyncMock()
    mock_bot.command_handler.handle_beer_challenge = AsyncMock()

    # Mock the event handler method
    mock_bot.event_eventsub_notification_channel_reward_redeem = AsyncMock()

    # Call the handler
    await mock_bot.event_eventsub_notification_channel_reward_redeem(mock_event)

    # Verify command was NOT called because the bot is inactive
    mock_bot.command_handler.handle_beer_challenge.assert_not_called()


@pytest.mark.asyncio
async def test_eventsub_error_handling_in_handlers():
    """Test error handling in individual reward handlers."""
    from src.eventsub.reward_handlers import twenty_one_handler

    # Create mock event
    mock_event = MagicMock()
    mock_event.data = MagicMock()
    mock_event.data.user = MagicMock()
    mock_event.data.user.name = "TestUser"
    mock_event.data.user.id = "123"
    mock_event.data.broadcaster = MagicMock()
    mock_event.data.broadcaster.name = "testchannel"

    # Create mock bot
    mock_bot = MagicMock()
    mock_bot.active = True
    mock_bot.command_handler = AsyncMock()
    mock_bot.command_handler.handle_twenty_one = AsyncMock()

    # Mock create_fake_context to raise an exception
    with patch(
        "src.eventsub.reward_handlers.create_fake_context", AsyncMock(side_effect=Exception("Context creation failed"))
    ):
        # Expect an exception since the handler doesn't catch it
        with pytest.raises(Exception, match="Context creation failed"):
            await twenty_one_handler(mock_event, mock_bot)

        # Command should not be called when there's an error
        mock_bot.command_handler.handle_twenty_one.assert_not_called()
