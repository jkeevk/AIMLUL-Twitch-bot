import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.commands.games.beer_barrel import BeerBarrelGame
from src.commands.models.chatters import ChatterData


@pytest.fixture(autouse=True)
def mock_sleep_for_all_tests():
    """Mock asyncio.sleep for ALL tests in this module."""
    with patch("asyncio.sleep", AsyncMock()):
        yield


class TestBeerBarrelGame:
    """Tests for BeerBarrelGame class."""

    @pytest.fixture
    def beer_barrel_game(self):
        """Create a BeerBarrelGame instance with mocked dependencies."""
        mock_command_handler = MagicMock()
        mock_command_handler.bot = MagicMock()
        mock_command_handler.cache_manager = MagicMock()
        mock_command_handler.api = MagicMock()
        mock_command_handler.logger = MagicMock()

        game = BeerBarrelGame(mock_command_handler)
        game.bot = mock_command_handler.bot
        game.cache_manager = mock_command_handler.cache_manager
        game.api = mock_command_handler.api
        game.logger = mock_command_handler.logger

        # Reset class variables before each test
        game._is_running = False
        game.active_players.clear()
        game.kaban_players.clear()

        return game

    @pytest.mark.asyncio
    async def test_send_batched_message_small_list(self, beer_barrel_game):
        """Test sending batched message with a small list of names."""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()

        names = ["User1", "User2", "User3"]
        prefix = "Test prefix: "

        await beer_barrel_game._send_batched_message(mock_channel, prefix, names)

        # Should send one message with all names
        mock_channel.send.assert_called_once()
        message = mock_channel.send.call_args[0][0]
        assert message.startswith("Test prefix: @User1, @User2, @User3")

    @pytest.mark.asyncio
    async def test_send_batched_message_large_list(self, beer_barrel_game):
        """Test sending batched message with a large list that exceeds max length."""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()

        # Create long names that will exceed MAX_MESSAGE_LENGTH
        long_names = ["VeryLongUserName" + str(i) for i in range(20)]
        prefix = "Testing: "

        await beer_barrel_game._send_batched_message(mock_channel, prefix, long_names)

        # Should send multiple messages
        assert mock_channel.send.call_count > 1

    @pytest.mark.asyncio
    async def test_send_batched_message_empty_list(self, beer_barrel_game):
        """Test sending batched message with an empty list."""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()

        await beer_barrel_game._send_batched_message(mock_channel, "Prefix", [])

        # Should not send any message
        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_kaban_status_success(self, beer_barrel_game):
        """Test kaban status update when a target count is reached."""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()

        # Set enough players to reach target
        beer_barrel_game.kaban_players = {f"User{i}" for i in range(20)}

        success = await beer_barrel_game._update_kaban_status(mock_channel, False, 40)

        assert success is True
        mock_channel.send.assert_not_called()  # No status message when succeeded

    @pytest.mark.asyncio
    async def test_update_kaban_status_partial(self, beer_barrel_game):
        """Test kaban status update when partially filled."""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()

        # Set some players but not enough
        beer_barrel_game.kaban_players = {"User1", "User2", "User3"}

        success = await beer_barrel_game._update_kaban_status(mock_channel, False, 40)

        assert success is False
        mock_channel.send.assert_called_once()
        message = mock_channel.send.call_args[0][0]
        assert "3/20" in message
        assert "Нужно еще 17" in message

    @pytest.mark.asyncio
    async def test_update_kaban_status_already_successful(self, beer_barrel_game):
        """Test kaban status update when already successful."""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()

        # Status is already successful
        success = await beer_barrel_game._update_kaban_status(mock_channel, True, 40)

        assert success is True
        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_kaban_challenge_success_early(self, beer_barrel_game):
        """Test kaban challenge that succeeds early."""
        mock_channel = AsyncMock()
        mock_channel.name = "testchannel"
        mock_channel.send = AsyncMock()

        # Set enough players from the start
        beer_barrel_game.kaban_players = {
            "User1",
            "User2",
            "User3",
            "User4",
            "User5",
            "User6",
            "User7",
            "User8",
            "User9",
            "User10",
            "User11",
            "User12",
        }

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("random.choice", return_value=False):  # Mock the 50/50 roll
                result = await beer_barrel_game._run_kaban_challenge_and_determine_fate(mock_channel)

        assert result is True  # Should return True for punishment
        assert mock_channel.send.call_count > 0

    @pytest.mark.asyncio
    async def test_run_kaban_challenge_failure(self, beer_barrel_game):
        """Test kaban challenge that fails."""
        mock_channel = AsyncMock()
        mock_channel.name = "testchannel"
        mock_channel.send = AsyncMock()

        # Set no players
        beer_barrel_game.kaban_players = set()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await beer_barrel_game._run_kaban_challenge_and_determine_fate(mock_channel)

        assert result is True  # Should return True for punishment
        # Should send a failure message
        send_calls = [call[0][0] for call in mock_channel.send.call_args_list]
        assert any("Не хватило кабанчиков" in str(call) for call in send_calls)

    @pytest.mark.asyncio
    async def test_handle_trash_command_not_running(self, beer_barrel_game):
        """Test trash command when barrel is not running."""
        beer_barrel_game._is_running = False

        await beer_barrel_game.handle_trash_command("TestUser", "testchannel")

        # Should log but not add player
        assert "TestUser" not in beer_barrel_game.active_players

    @pytest.mark.asyncio
    async def test_handle_trash_command_running(self, beer_barrel_game):
        """Test trash command when barrel is running."""
        beer_barrel_game._is_running = True

        await beer_barrel_game.handle_trash_command("TestUser", "testchannel")

        # Should add player to active players
        assert "TestUser" in beer_barrel_game.active_players

    @pytest.mark.asyncio
    async def test_handle_trash_command_already_protected(self, beer_barrel_game):
        """Test trash command when a user is already protected."""
        beer_barrel_game._is_running = True
        beer_barrel_game.active_players.add("TestUser")

        await beer_barrel_game.handle_trash_command("TestUser", "testchannel")

        # Should not duplicate
        assert len(beer_barrel_game.active_players) == 1

    @pytest.mark.asyncio
    async def test_handle_kaban_command_not_running(self, beer_barrel_game):
        """Test kaban command when barrel is not running."""
        beer_barrel_game._is_running = False

        await beer_barrel_game.handle_kaban_command("TestUser", "testchannel")

        # Should log but not add player
        assert "TestUser" not in beer_barrel_game.kaban_players

    @pytest.mark.asyncio
    async def test_handle_kaban_command_running(self, beer_barrel_game):
        """Test kaban command when barrel is running."""
        beer_barrel_game._is_running = True

        await beer_barrel_game.handle_kaban_command("TestUser", "testchannel")

        # Should add player to kaban players
        assert "TestUser" in beer_barrel_game.kaban_players

    @pytest.mark.asyncio
    async def test_handle_kaban_command_already_joined(self, beer_barrel_game):
        """Test kaban command when user already joined."""
        beer_barrel_game._is_running = True
        beer_barrel_game.kaban_players.add("TestUser")

        await beer_barrel_game.handle_kaban_command("TestUser", "testchannel")

        # Should not duplicate
        assert len(beer_barrel_game.kaban_players) == 1

    @pytest.mark.asyncio
    async def test_handle_kaban_command_full_team(self, beer_barrel_game):
        """Test kaban command when a team is already full."""
        beer_barrel_game._is_running = True
        # Fill the team
        for i in range(beer_barrel_game.KABAN_TARGET_COUNT):
            beer_barrel_game.kaban_players.add(f"User{i}")

        await beer_barrel_game.handle_kaban_command("NewUser", "testchannel")

        # Should not add new user
        assert len(beer_barrel_game.kaban_players) == beer_barrel_game.KABAN_TARGET_COUNT
        assert "NewUser" not in beer_barrel_game.kaban_players

    @pytest.mark.asyncio
    async def test_handle_beer_barrel_command_no_chatters(self, beer_barrel_game):
        """Test beer barrel command with no available chatters."""
        beer_barrel_game.cache_manager.should_update_cache.return_value = False
        beer_barrel_game.cache_manager.get_cached_chatters.return_value = []

        with patch.object(
            beer_barrel_game, "_run_kaban_challenge_and_determine_fate", new_callable=AsyncMock
        ) as mock_challenge:
            await beer_barrel_game.handle_beer_barrel_command("TriggerUser", "testchannel")

        # Should log warning and return early
        mock_challenge.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_beer_barrel_command_successful_neutralization(self, beer_barrel_game):
        """Test beer barrel command with successful kaban challenge neutralization."""
        # Setup chatters
        mock_chatters = [{"id": str(i), "name": f"User{i}", "display_name": f"User{i}"} for i in range(30)]
        beer_barrel_game.cache_manager.should_update_cache.return_value = False
        beer_barrel_game.cache_manager.get_cached_chatters.return_value = mock_chatters
        beer_barrel_game.cache_manager.filter_chatters.return_value = mock_chatters

        # Setup bot channel
        mock_channel = AsyncMock()
        mock_channel.name = "testchannel"
        mock_channel.send = AsyncMock()
        beer_barrel_game.bot.get_channel.return_value = mock_channel
        beer_barrel_game.bot.join_channels = AsyncMock()

        # Mock API
        beer_barrel_game.api.timeout_user = AsyncMock(return_value=(200, {}))

        # Mock kaban challenge to return False (neutralized, no punishment)
        with patch.object(beer_barrel_game, "_run_kaban_challenge_and_determine_fate", AsyncMock(return_value=False)):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await beer_barrel_game.handle_beer_barrel_command("TriggerUser", "testchannel")

        # Should not call timeout_user since a challenge was neutralized
        beer_barrel_game.api.timeout_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_beer_barrel_command_with_punishment(self, beer_barrel_game):
        """Test beer barrel command with punishment execution."""
        # Mock chatters
        mock_chatters = [ChatterData(id=str(i), name=f"User{i}", display_name=f"User{i}") for i in range(5)]

        # Setup mocks
        beer_barrel_game.cache_manager.get_or_update_chatters = AsyncMock(return_value=mock_chatters)

        mock_channel = AsyncMock()
        mock_channel.name = "testchannel"
        beer_barrel_game.bot.get_channel = MagicMock(return_value=mock_channel)
        beer_barrel_game.bot.join_channels = AsyncMock()
        beer_barrel_game.api.timeout_user = AsyncMock(return_value=(200, {}))

        # Force Kaban challenge to return True (punishment required)
        beer_barrel_game._run_kaban_challenge_and_determine_fate = AsyncMock(return_value=True)

        with patch("random.sample", return_value=mock_chatters):
            with patch("random.shuffle"):
                await beer_barrel_game.handle_beer_barrel_command("TriggerUser", "testchannel")

        # Ensure timeout_user was called
        assert beer_barrel_game.api.timeout_user.call_count > 0

    @pytest.mark.asyncio
    async def test_handle_beer_barrel_command_with_punishment_simple(self, beer_barrel_game):
        """Test beer barrel command with punishment execution (simplified)."""
        mock_chatters = [ChatterData(id=str(i), name=f"User{i}", display_name=f"User{i}") for i in range(5)]

        beer_barrel_game.cache_manager.get_or_update_chatters = AsyncMock(return_value=mock_chatters)

        mock_channel = AsyncMock()
        mock_channel.name = "testchannel"
        mock_channel.send = AsyncMock()

        beer_barrel_game.bot.get_channel = MagicMock(return_value=mock_channel)
        beer_barrel_game.bot.join_channels = AsyncMock()
        beer_barrel_game.api.timeout_user = AsyncMock(return_value=(200, {}))
        beer_barrel_game._run_kaban_challenge_and_determine_fate = AsyncMock(return_value=True)

        with patch("random.sample", return_value=mock_chatters):
            with patch("random.shuffle"):
                await beer_barrel_game.handle_beer_barrel_command("TriggerUser", "testchannel")

        assert beer_barrel_game._run_kaban_challenge_and_determine_fate.called
        assert beer_barrel_game.cache_manager.get_or_update_chatters.called

    @pytest.mark.asyncio
    async def test_handle_beer_barrel_command_with_protected_players(self, beer_barrel_game):
        """Test beer barrel command with players using trash protection."""
        mock_chatters = [
            ChatterData(id="1", name="ProtectedUser", display_name="ProtectedUser"),
            ChatterData(id="2", name="UnprotectedUser", display_name="UnprotectedUser"),
        ]

        beer_barrel_game.cache_manager.get_or_update_chatters = AsyncMock(return_value=mock_chatters)

        mock_channel = AsyncMock()
        mock_channel.name = "testchannel"
        mock_channel.send = AsyncMock()

        beer_barrel_game.bot.get_channel = MagicMock(return_value=mock_channel)
        beer_barrel_game.bot.join_channels = AsyncMock()

        # Track timeout calls
        timeout_calls = []

        async def mock_timeout_user(user_id, *_args, **_kwargs):
            timeout_calls.append(user_id)
            return 200, {}

        beer_barrel_game.api.timeout_user = AsyncMock(side_effect=mock_timeout_user)
        beer_barrel_game._run_kaban_challenge_and_determine_fate = AsyncMock(return_value=True)

        with patch("src.commands.games.beer_barrel.is_privileged", return_value=False):
            with patch("random.sample", return_value=mock_chatters):
                with patch("random.shuffle"):
                    # Mock active_players
                    mock_active_players = MagicMock(spec=set)
                    mock_active_players.__contains__ = MagicMock(side_effect=lambda x: x.lower() == "protecteduser")
                    mock_active_players.add = MagicMock()
                    mock_active_players.clear = MagicMock()
                    mock_active_players.__iter__ = MagicMock(return_value=iter(["protecteduser"]))
                    beer_barrel_game.active_players = mock_active_players

                    await beer_barrel_game.handle_beer_barrel_command("TriggerUser", "testchannel")

        # Ensure only unprotected user was punished
        assert "2" in timeout_calls
        assert "1" not in timeout_calls

    @pytest.mark.asyncio
    async def test_handle_beer_barrel_command_exception_handling(self, beer_barrel_game):
        """Test beer barrel command exception handling."""
        beer_barrel_game.cache_manager.should_update_cache.return_value = False
        beer_barrel_game.cache_manager.get_cached_chatters.side_effect = Exception("Test error")

        try:
            await beer_barrel_game.handle_beer_barrel_command("TriggerUser", "testchannel")
        except Exception as e:
            beer_barrel_game.logger.error("Caught exception during test: %s", e)
            pytest.fail("Exception should be caught and logged, not propagated")

        # Should log error
        assert beer_barrel_game.logger.error.called

    @pytest.mark.asyncio
    async def test_concurrent_protection_commands(self, beer_barrel_game):
        """Test multiple users activating protection concurrently."""
        beer_barrel_game._is_running = True

        # Simulate concurrent protection commands
        users = [f"User{i}" for i in range(10)]
        tasks = [beer_barrel_game.handle_trash_command(user, "testchannel") for user in users]
        await asyncio.gather(*tasks)

        # All users should be protected
        assert len(beer_barrel_game.active_players) == 10
        for user in users:
            assert user in beer_barrel_game.active_players

    @pytest.mark.asyncio
    async def test_concurrent_kaban_commands(self, beer_barrel_game):
        """Test multiple users joining kaban challenge concurrently."""
        beer_barrel_game._is_running = True

        # Simulate concurrent kaban commands
        users = [f"KabanUser{i}" for i in range(beer_barrel_game.KABAN_TARGET_COUNT)]
        tasks = [beer_barrel_game.handle_kaban_command(user, "testchannel") for user in users]
        await asyncio.gather(*tasks)

        # All users should be in kaban players
        assert len(beer_barrel_game.kaban_players) == beer_barrel_game.KABAN_TARGET_COUNT
        for user in users:
            assert user in beer_barrel_game.kaban_players
