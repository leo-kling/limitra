"""Shared pytest fixtures for the limitra test suite."""

from collections.abc import Iterator
from typing import Any

import pytest

from limitra._config import reset_config

try:
    import redis as redis_lib
    from testcontainers.redis import RedisContainer
except ImportError:
    RedisContainer = None
    redis_lib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Config reset — ensures each test starts with a clean limitra global state
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_limitra_config() -> Iterator[None]:
    """Reset limitra global config before and after each test."""
    reset_config()
    yield
    reset_config()


# ---------------------------------------------------------------------------
# Testcontainers Redis — one container for the whole session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", name="redis_container")
def _make_redis_container() -> Iterator[Any]:
    """Session-scoped Redis container via testcontainers."""
    if RedisContainer is None:
        pytest.skip("testcontainers not installed — pip install testcontainers[redis]")
        return
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(name="redis_client")
def _make_redis_client(redis_container: Any) -> Iterator[Any]:
    """Function-scoped Redis client. DB is flushed before and after each test."""
    assert redis_lib is not None
    host = redis_container.get_container_host_ip()
    port = int(redis_container.get_exposed_port(6379))
    client = redis_lib.Redis(host=host, port=port, db=0, decode_responses=False)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture(name="redis_url")
def _make_redis_url(redis_container: Any) -> str:
    """Return a redis:// URL pointing at the test container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"
