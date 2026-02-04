import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis
from twitchio.ext.commands import Context

from src.bot.manager import BotManager
from src.bot.twitch_bot import TwitchBot
from src.commands.command_handler import CommandHandler
from src.commands.games.collectors_game import CollectorsGame
from src.commands.games.simple_commands import SimpleCommandsGame
from src.commands.games.twenty_one import TwentyOneGame
from src.commands.managers.cache_manager import CacheManager
from src.commands.triggers.text_triggers import build_triggers
from src.utils.token_manager import TokenManager


@pytest.fixture
def mock_token_manager() -> TokenManager:
    """Mocked TokenManager with async refresh and placeholder tokens."""
    tm = MagicMock(spec=TokenManager)
    tm.tokens = {"BOT_TOKEN": MagicMock(client_id="cid", client_secret="csecret")}
    tm.refresh_access_token = AsyncMock(return_value="new_token")
    tm.has_streamer_token = MagicMock(return_value=True)
    return tm


@pytest.fixture
def bot_instance(mock_token_manager: TokenManager, mock_redis: AsyncMock) -> TwitchBot:
    """Return a TwitchBot instance with dependencies mocked, no start() called."""
    with patch(
        "src.bot.twitch_bot.load_settings",
        return_value={
            "channels": ["#test_channel"],
            "database": {"dsn": "sqlite+aiosqlite:///:memory:"},
            "refresh_token_delay_time": 0.01,
        },
    ):
        bot = TwitchBot(token_manager=mock_token_manager, bot_token="initial_token", redis=mock_redis)

    bot.db = MagicMock()
    bot.db.connect = AsyncMock()
    bot.db.close = AsyncMock()
    bot.command_handler = MagicMock()
    bot.eventsub.setup = AsyncMock()
    bot.api = MagicMock()
    bot.handle_commands = AsyncMock()
    bot.triggers_map = build_triggers(bot)

    return bot


@pytest.fixture
def bot_manager(bot_instance: TwitchBot, mock_token_manager: TokenManager, mock_redis: AsyncMock) -> BotManager:
    """Return a TwitchBot instance with dependencies mocked, no start() called."""
    manager = BotManager(token_manager=mock_token_manager, redis=mock_redis)
    manager.bot = bot_instance
    return manager


@dataclass
class DummyAuthor:
    id: str | int
    name: str
    display_name: str
    privileged: bool = False

    def __init__(self, user_id: str | int, name: str, privileged: bool = False):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.privileged = privileged


class DummyMessage:
    """Represents a mock chat message."""

    def __init__(self, author: DummyAuthor, channel_name: str = "testchannel"):
        self.author = author
        self.channel = channel or MagicMock()
        self.channel.name = channel_name


class DummyChannel:
    """Represents a mock channel."""

    def __init__(self, name: str):
        self.name = name
        self.chatters = []


class DummyCtx:
    """Represents a mock command context."""

    def __init__(self, author: DummyAuthor, channel: "DummyChannel", message_content: str = ""):
        self.author = author
        self.channel = channel
        self.sent: list[str] = []
        self.message = type("Message", (), {"content": message_content})()

    async def send(self, msg: str):
        """Store a message in the "sent" messages list."""
        self.sent.append(msg)


class DummyEvent:
    """Dummy EventSub event for testing reward handlers."""

    def __init__(self, reward_name, username, user_id, input_val=""):
        self.data = MagicMock()
        self.data.reward = MagicMock()
        self.data.reward.title = reward_name
        self.data.user = MagicMock()
        self.data.user.name = username
        self.data.user.id = user_id
        self.data.broadcaster = MagicMock()
        self.data.broadcaster.name = "TestBroadcaster"
        self.data.input = input_val


@pytest.fixture
def mock_bot(mock_cache_manager):
    """Create a mocked TwitchBot instance for general testing."""
    bot = MagicMock(spec=TwitchBot)
    bot.active = True
    bot.api = AsyncMock()
    bot.db = AsyncMock()
    bot.config = {"admins": []}
    bot.cache_manager = mock_cache_manager
    command_handler = CommandHandler(bot)
    command_handler.beer_challenge_game = AsyncMock()
    command_handler.beer_challenge_game.handle_beer_challenge_command = AsyncMock()
    command_handler.twenty_one_game = AsyncMock()
    command_handler.beer_barrel_game = AsyncMock()

    bot.command_handler = command_handler
    return bot


@pytest.fixture
def beer_barrel_game():
    """Fixture for BeerBarrelGame instance."""
    from src.commands.games.beer_barrel import BeerBarrelGame

    # Create a mock command handler
    command_handler = MagicMock()
    command_handler.bot = MagicMock()
    command_handler.api = MagicMock()
    command_handler.cache_manager = MagicMock()
    command_handler.get_current_time = MagicMock(return_value=time.time())

    # Create the game instance
    game = BeerBarrelGame(command_handler)

    # Ensure all attributes are properly set
    game.bot = command_handler.bot
    game.api = command_handler.api
    game.cache_manager = command_handler.cache_manager
    game.logger = MagicMock()

    # Reset game state
    game._is_running = False
    game.active_players.clear()
    game.kaban_players.clear()

    return game


@pytest.fixture
def mock_context():
    """Create a mocked Context for testing commands."""
    ctx = MagicMock(spec=Context)
    ctx.author = MagicMock()
    ctx.author.name = "TestUser"
    ctx.author.id = "123"
    ctx.channel = MagicMock()
    ctx.channel.name = "testbroadcaster"
    ctx.send = AsyncMock()
    return ctx


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mocked Redis instance for async cache manager."""
    redis = AsyncMock(spec=Redis)
    redis.get.return_value = None
    redis.setex.return_value = True
    redis.exists.return_value = 0
    return redis


@pytest.fixture
def mock_cache_manager(mock_redis: AsyncMock) -> CacheManager:
    """Return a CacheManager instance with Redis mocked."""
    cm = CacheManager(redis=mock_redis)

    cm.update_user_cooldown = AsyncMock()
    cm.can_user_participate = AsyncMock(return_value=True)
    cm.set_command_cooldown = AsyncMock()
    cm.get_command_cooldown = AsyncMock(return_value=True)
    cm.get_or_update_chatters = AsyncMock(return_value=[])
    cm.get_cached_chatters = AsyncMock(return_value=[])
    cm.update_chatters_cache = AsyncMock()
    cm.get_user_id = AsyncMock(return_value=None)

    return cm


@pytest.fixture
def mock_api() -> MagicMock:
    """Mock API for timeout calls."""
    api = MagicMock()
    api.timeout_user = AsyncMock(return_value=(200, {}))
    return api


@pytest.fixture
def simple_commands_game(mock_bot: MagicMock, mock_cache_manager: MagicMock, mock_api: MagicMock) -> SimpleCommandsGame:
    """Fixture for the SimpleCommandsGame instance with proper bot/cache_manager."""
    mock_bot.cache_manager = mock_cache_manager
    mock_bot.api = mock_api
    mock_bot.db = AsyncMock()

    from src.commands.command_handler import CommandHandler

    handler = CommandHandler(bot=mock_bot)

    handler.cache_manager = mock_cache_manager
    handler.api = mock_api
    handler.simple_commands_game = None

    from src.commands.games.simple_commands import SimpleCommandsGame

    game = SimpleCommandsGame(command_handler=handler)
    game.bot = mock_bot
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
def collectors_game(mock_bot: MagicMock, mock_cache_manager: MagicMock, mock_api: MagicMock) -> CollectorsGame:
    """Fixture for the CollectorsGame instance."""
    handler = MagicMock()
    handler.bot = mock_bot
    handler.cache_manager = mock_cache_manager
    handler.api = mock_api

    game = CollectorsGame(command_handler=handler)
    game.bot = mock_bot
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
