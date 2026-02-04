import os
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)


def create_redis() -> redis.Redis:
    """
    Initialize and return an asynchronous Redis client.

    Reads the Redis connection URL from the environment variable `REDIS_URL`.
    Default to `redis://localhost:6379/0` if not set.

    The client is configured with:
        - `decode_responses=True` to automatically decode bytes to strings
        - `max_connections=20` to limit the connection pool size

    Returns:
        redis.Redis: An instance of the asynchronous Redis client ready for use.
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    client = redis.from_url(
        url,
        decode_responses=True,
        max_connections=20,
    )

    logger.info("Redis client initialized")
    return client

