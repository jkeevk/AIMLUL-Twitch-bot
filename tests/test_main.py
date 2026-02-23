from unittest.mock import AsyncMock, patch

import pytest

import src.main as main_module


@pytest.mark.asyncio
async def test_main_starts_and_stops_bot():
    """Check normal startup and shutdown of main().

    Ensures that TokenManager, Redis, and BotManager are initialized,
    the bot starts, and then stops correctly.
    """
    # Create AsyncMock instances for dependencies
    mock_token_manager = AsyncMock()
    mock_redis = AsyncMock()
    mock_manager = AsyncMock()

    # Patch all dependencies in main_module
    with (
        patch("src.main.TokenManager", return_value=mock_token_manager) as token_patch,
        patch("src.main.create_redis", return_value=mock_redis) as redis_patch,
        patch("src.main.BotManager", return_value=mock_manager) as manager_patch,
        patch("src.main.logger") as mock_logger,
    ):

        # Run main() asynchronously
        await main_module.main()

        # Assertions to ensure correct calls
        token_patch.assert_called_once_with(main_module.CONFIG_PATH)
        redis_patch.assert_called_once()
        manager_patch.assert_called_once_with(mock_token_manager, redis=mock_redis)
        mock_manager.start.assert_awaited_once()
        mock_manager.stop.assert_awaited_once()
        mock_logger.info.assert_any_call("Starting bot...")


@pytest.mark.asyncio
async def test_main_logs_exception_and_stops_bot_on_error():
    """Ensure main() handles BotManager.start() exceptions gracefully.

    If BotManager.start() raises an exception, main() should catch it,
    log the error, and still call BotManager.stop() to clean up.
    """
    mock_manager = AsyncMock()
    # Simulate an error when starting the bot
    mock_manager.start.side_effect = Exception("fail")

    # Patch all dependencies in main_module
    with (
        patch("src.main.TokenManager", return_value=AsyncMock()),
        patch("src.main.create_redis", return_value=AsyncMock()),
        patch("src.main.BotManager", return_value=mock_manager),
        patch("src.main.logger") as mock_logger,
    ):

        # Run main() asynchronously
        await main_module.main()

        # Ensure stop was called and exception was logged
        mock_manager.stop.assert_awaited_once()
        mock_logger.exception.assert_called_once()
