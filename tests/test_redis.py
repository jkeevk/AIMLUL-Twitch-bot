from unittest.mock import MagicMock

import pytest

from src.core import redis_client


@pytest.mark.asyncio
async def test_create_redis_uses_default_url(monkeypatch):
    mock_redis_from_url = MagicMock()
    monkeypatch.setattr(redis_client.redis, "from_url", mock_redis_from_url)

    monkeypatch.delenv("REDIS_URL", raising=False)

    client = redis_client.create_redis()

    mock_redis_from_url.assert_called_once_with(
        "redis://localhost:6379/0",
        decode_responses=True,
        max_connections=20
    )
    assert client == mock_redis_from_url()

@pytest.mark.asyncio
async def test_create_redis_uses_env_url(monkeypatch):
    mock_redis_from_url = MagicMock()
    monkeypatch.setattr(redis_client.redis, "from_url", mock_redis_from_url)

    monkeypatch.setenv("REDIS_URL", "redis://custom:6379/1")

    client = redis_client.create_redis()

    mock_redis_from_url.assert_called_once_with(
        "redis://custom:6379/1",
        decode_responses=True,
        max_connections=20
    )
    assert client == mock_redis_from_url()
