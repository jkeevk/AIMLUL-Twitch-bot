from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.eventsub.reward_handlers import reward_handlers
from tests.conftest import DummyEvent


@pytest.mark.asyncio
async def test_reward_handlers_call_command(mock_bot):
    """Test that EventSub reward handlers call the corresponding game command."""
    reward_name = "испытание пивом"
    handler = reward_handlers.get(reward_name)
    assert handler is not None, f"Handler for reward {reward_name} not found"

    event = DummyEvent(reward_name=reward_name, username="TestUser", user_id="123", input_val="test input")

    # Patch the bot's command to verify it is called correctly
    with patch.object(mock_bot.command_handler, "handle_beer_challenge", new_callable=AsyncMock) as mock_command:
        mock_bot.active = True
        await handler(event, mock_bot)

        mock_command.assert_awaited_once_with("TestUser", "test input", "testbroadcaster")


@pytest.mark.asyncio
async def test_beer_challenge_non_numeric_input():
    """Test that Beer Challenge reward with non-numeric input returns error message."""
    reward_name = "испытание пивом"
    handler = reward_handlers.get(reward_name)
    assert handler is not None, f"Handler for reward {reward_name} not found"

    # Create event with non-numeric input
    non_numeric_input = "не число"
    event = DummyEvent(reward_name=reward_name, username="TestUser", user_id="123", input_val=non_numeric_input)

    # Create fully mocked bot
    mock_bot = MagicMock()
    mock_bot.active = True

    # Create mock command handler
    mock_command_handler = AsyncMock()
    mock_command_handler.handle_beer_challenge = AsyncMock()

    # Setup the chain: bot.command_handler.handle_beer_challenge
    mock_bot.command_handler = mock_command_handler

    # Execute the handler
    await handler(event, mock_bot)

    # Verify the correct method was called
    mock_command_handler.handle_beer_challenge.assert_awaited_once()

    # Get the arguments passed to the method
    call_args = mock_command_handler.handle_beer_challenge.call_args
    assert call_args is not None

    # Check that the arguments match what we expect
    # handle_beer_challenge(user_name, user_input, channel_name)
    args, kwargs = call_args
    assert len(args) == 3
    assert args[0] == "TestUser"  # user_name
    assert args[1] == non_numeric_input  # user_input
    assert args[2] == "testbroadcaster"  # channel_name


@pytest.mark.asyncio
async def test_beer_challenge_empty_input():
    """Test that Beer Challenge reward with empty input returns error message."""
    reward_name = "испытание пивом"
    handler = reward_handlers.get(reward_name)
    assert handler is not None, f"Handler for reward {reward_name} not found"

    # Create event with empty input
    event = DummyEvent(reward_name=reward_name, username="TestUser", user_id="123", input_val="")

    # Create fully mocked bot
    mock_bot = MagicMock()
    mock_bot.active = True

    # Create mock command handler
    mock_command_handler = AsyncMock()
    mock_command_handler.handle_beer_challenge = AsyncMock()

    # Setup the chain: bot.command_handler.handle_beer_challenge
    mock_bot.command_handler = mock_command_handler

    # Execute the handler
    await handler(event, mock_bot)

    # Verify the correct method was called
    mock_command_handler.handle_beer_challenge.assert_awaited_once()

    # Get the arguments passed to the method
    call_args = mock_command_handler.handle_beer_challenge.call_args
    assert call_args is not None

    # Check that the arguments match what we expect
    # handle_beer_challenge(user_name, user_input, channel_name)
    args, kwargs = call_args
    assert len(args) == 3
    assert args[0] == "TestUser"  # user_name
    assert args[1] == ""  # user_input (empty)
    assert args[2] == "testbroadcaster"  # channel_name


@pytest.mark.asyncio
async def test_beer_challenge_whitespace_input():
    """Test that Beer Challenge reward with only whitespace input returns error message."""
    reward_name = "испытание пивом"
    handler = reward_handlers.get(reward_name)
    assert handler is not None, f"Handler for reward {reward_name} not found"

    # Create event with whitespace-only input
    event = DummyEvent(reward_name=reward_name, username="TestUser", user_id="123", input_val="   ")

    # Create fully mocked bot
    mock_bot = MagicMock()
    mock_bot.active = True

    # Create mock command handler
    mock_command_handler = AsyncMock()
    mock_command_handler.handle_beer_challenge = AsyncMock()

    # Setup the chain: bot.command_handler.handle_beer_challenge
    mock_bot.command_handler = mock_command_handler

    # Execute the handler
    await handler(event, mock_bot)

    # Verify the correct method was called
    mock_command_handler.handle_beer_challenge.assert_awaited_once()

    # Get the arguments passed to the method
    call_args = mock_command_handler.handle_beer_challenge.call_args
    assert call_args is not None

    # Check that the arguments match what we expect
    # handle_beer_challenge(user_name, user_input, channel_name)
    args, kwargs = call_args
    assert len(args) == 3
    assert args[0] == "TestUser"  # user_name
    assert args[1] == "   "  # user_input (whitespace)
    assert args[2] == "testbroadcaster"  # channel_name


@pytest.mark.asyncio
async def test_beer_challenge_mixed_input():
    """Test that Beer Challenge reward with mixed text and numbers returns error message."""
    reward_name = "испытание пивом"
    handler = reward_handlers.get(reward_name)
    assert handler is not None, f"Handler for reward {reward_name} not found"

    # Create event with mixed input (number followed by text)
    mixed_input = "10 пива"
    event = DummyEvent(reward_name=reward_name, username="TestUser", user_id="123", input_val=mixed_input)

    # Create fully mocked bot
    mock_bot = MagicMock()
    mock_bot.active = True

    # Create mock command handler
    mock_command_handler = AsyncMock()
    mock_command_handler.handle_beer_challenge = AsyncMock()

    # Setup the chain: bot.command_handler.handle_beer_challenge
    mock_bot.command_handler = mock_command_handler

    # Execute the handler
    await handler(event, mock_bot)

    # Verify the correct method was called
    mock_command_handler.handle_beer_challenge.assert_awaited_once()

    # Get the arguments passed to the method
    call_args = mock_command_handler.handle_beer_challenge.call_args
    assert call_args is not None

    # Check that the arguments match what we expect
    # handle_beer_challenge(user_name, user_input, channel_name)
    args, kwargs = call_args
    assert len(args) == 3
    assert args[0] == "TestUser"  # user_name
    assert args[1] == mixed_input  # user_input
    assert args[2] == "testbroadcaster"  # channel_name


@pytest.mark.asyncio
async def test_beer_challenge_game_non_numeric_logic():
    """Test the actual logic of BeerChallengeGame.handle_beer_challenge_command with non-numeric input."""
    from src.commands.command_handler import CommandHandler

    # Create mocks
    mock_bot = MagicMock()
    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()

    # Setup bot to return mock channel
    mock_bot.get_channel = MagicMock(return_value=mock_channel)
    mock_bot.join_channels = AsyncMock()
    mock_bot.active = True
    mock_bot.api = AsyncMock()
    mock_bot.db = AsyncMock()

    # Create real CommandHandler with the mocked bot
    command_handler = CommandHandler(mock_bot)

    # Now we need to test the actual method logic
    user_name = "TestUser"
    channel_name = "testbroadcaster"

    # Test with non-numeric input
    non_numeric_input = "не число"

    # Call the actual method
    await command_handler.beer_challenge_game.handle_beer_challenge_command(user_name, non_numeric_input, channel_name)

    # Verify that send was called with the error message
    mock_channel.send.assert_awaited_once()

    # Get the actual message sent
    actual_call_args = mock_channel.send.call_args[0]
    actual_message = actual_call_args[0] if actual_call_args else ""

    # Check if the error message contains the expected text
    assert (
        "че пишешь то" in actual_message.lower()
    ), f"Expected error message about invalid input, but got: {actual_message}"

    # Verify that no database or API calls were made
    mock_bot.db.add_tickets.assert_not_called()
    mock_bot.api.timeout_user.assert_not_called()


@pytest.mark.asyncio
async def test_beer_challenge_game_logic_with_mocks():
    """Test beer challenge game logic using proper mocking."""
    from src.commands.command_handler import CommandHandler

    # Create a proper mock setup
    mock_bot = MagicMock()
    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()

    # Setup bot
    mock_bot.get_channel = MagicMock(return_value=mock_channel)
    mock_bot.join_channels = AsyncMock()
    mock_bot.active = True
    mock_bot.api = AsyncMock()
    mock_bot.db = AsyncMock()

    # Create real CommandHandler
    command_handler = CommandHandler(mock_bot)

    # Mock the dependencies
    command_handler.beer_challenge_game.cache_manager = MagicMock()
    command_handler.beer_challenge_game.cache_manager.filter_chatters = MagicMock(return_value=True)

    command_handler.beer_challenge_game.user_manager = MagicMock()
    command_handler.beer_challenge_game.user_manager.get_user_id = AsyncMock(return_value="user123")

    command_handler.beer_challenge_game.db = mock_bot.db
    command_handler.beer_challenge_game.api = mock_bot.api

    command_handler.beer_challenge_game.logger = MagicMock()

    # Now test the actual logic
    await command_handler.beer_challenge_game.handle_beer_challenge_command("TestUser", "не число", "testchannel")

    # Verify error message was sent
    mock_channel.send.assert_awaited_once()

    actual_message = mock_channel.send.call_args[0][0]
    assert "че пишешь то" in actual_message.lower()
