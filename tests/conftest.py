from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.commands.games.collectors_game import CollectorsGame
from src.commands.games.simple_commands import SimpleCommandsGame
from src.commands.games.twenty_one import TwentyOneGame


@dataclass
class DummyAuthor:
    """Represents a mock user/author for testing."""

    def __init__(self, id_: str | int, name: str, privileged: bool = False):
        self.id = id_
        self.name = name
        self.is_mod = privileged
        self.is_broadcaster = privileged


@dataclass
class DummyMessage:
    """Represents a mock chat message."""

    def __init__(self, author: DummyAuthor, channel_name: str = "testchannel"):
        self.author = author
        self.channel = MagicMock()
        self.channel.name = channel_name


@dataclass
class DummyChannel:
    """Represents a mock channel."""

    def __init__(self, name: str):
        self.name = name
        self.chatters = []


@dataclass
class DummyCtx:
    """Represents a mock command context."""

    def __init__(self, author: DummyAuthor, channel: DummyChannel):
        self.author = author
        self.channel = channel
        self.sent: list[str] = []

    async def send(self, msg: str):
        """Store a message in the sent messages list."""
        self.sent.append(msg)


@pytest.fixture
def mock_bot() -> MagicMock:
    """Mock bot object with minimal configuration."""
    bot = MagicMock()
    bot.nick = "botnick"
    bot.config = {"admins": [], "privileged": []}
    return bot


@pytest.fixture
def mock_cache_manager() -> MagicMock:
    """Mock cache manager for testing."""
    cm = MagicMock()
    cm.should_update_cache.return_value = False
    cm.get_cached_chatters.return_value = []
    cm.filter_chatters.return_value = []
    cm.command_cooldowns = {}
    return cm


@pytest.fixture
def mock_user_manager() -> MagicMock:
    """Mock user manager with async ID resolution."""
    um = MagicMock()
    um.get_user_id = AsyncMock(return_value="some-id")
    return um


@pytest.fixture
def mock_api() -> MagicMock:
    """Mock API for timeout calls."""
    api = MagicMock()
    api.timeout_user = AsyncMock(return_value=(200, {}))
    return api


@pytest.fixture
def simple_commands_game(
    mock_bot: MagicMock, mock_cache_manager: MagicMock, mock_user_manager: MagicMock, mock_api: MagicMock
) -> SimpleCommandsGame:
    """Fixture for the SimpleCommandsGame instance."""
    handler = MagicMock()
    handler.bot = mock_bot
    handler.cache_manager = mock_cache_manager
    handler.user_manager = mock_user_manager
    handler.api = mock_api
    handler.get_current_time.return_value = 1000

    game = SimpleCommandsGame(command_handler=handler)
    game.bot = mock_bot
    game.cache_manager = mock_cache_manager
    game.user_manager = mock_user_manager
    game.api = mock_api

    return game


@pytest.fixture
def twenty_one_game() -> TwentyOneGame:
    """Fixture for the TwentyOneGame instance."""
    handler_mock = MagicMock()
    handler_mock.bot = MagicMock()
    game = TwentyOneGame(command_handler=handler_mock)
    return game


@pytest.fixture
def collectors_game(
    mock_bot: MagicMock, mock_cache_manager: MagicMock, mock_user_manager: MagicMock, mock_api: MagicMock
) -> CollectorsGame:
    """Fixture for the CollectorsGame instance."""
    handler = MagicMock()
    handler.bot = mock_bot
    handler.cache_manager = mock_cache_manager
    handler.user_manager = mock_user_manager
    handler.api = mock_api

    game = CollectorsGame(command_handler=handler)
    game.bot = mock_bot
    game.cache_manager = mock_cache_manager
    game.user_manager = mock_user_manager
    game.api = mock_api

    return game


@pytest.fixture
def privileged_author() -> DummyAuthor:
    """Fixture for a privileged/moderator author."""
    return DummyAuthor(1, "PrivilegedUser", privileged=True)


@pytest.fixture
def normal_author() -> DummyAuthor:
    """Fixture for a normal, non-privileged author."""
    return DummyAuthor(2, "NormalUser", privileged=False)


@pytest.fixture
def channel() -> DummyChannel:
    """Fixture for a dummy channel."""
    return DummyChannel("testchannel")


@pytest.fixture
def ctx_privileged(privileged_author: DummyAuthor, channel: DummyChannel) -> DummyCtx:
    """Fixture for a context with a privileged author."""
    return DummyCtx(privileged_author, channel)


@pytest.fixture
def ctx_normal(normal_author: DummyAuthor, channel: DummyChannel) -> DummyCtx:
    """Fixture for a context with a normal author."""
    return DummyCtx(normal_author, channel)
