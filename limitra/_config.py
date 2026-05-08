"""Global configuration singleton for limitra."""

from dataclasses import dataclass
from typing import Any, Optional

try:
    import redis as _redis_lib
except ImportError:
    _redis_lib = None  # type: ignore[assignment]


@dataclass
class _Config:
    """Holds global defaults applied to every rate limiter."""

    redis_client: Optional[Any] = None
    project: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    default_algorithm: str = "sliding_window"
    default_backend: str = "memory"
    fail_open: bool = False


class _ConfigStore:
    """Mutable holder for the active configuration (avoids module-level global)."""

    _current: _Config = _Config()

    @classmethod
    def get(cls) -> _Config:
        """Return the active configuration."""
        return cls._current

    @classmethod
    def set(cls, config: _Config) -> None:
        """Replace the active configuration."""
        cls._current = config

    @classmethod
    def reset(cls) -> None:
        """Reset to default configuration."""
        cls._current = _Config()


def LimitraConfig(  # pylint: disable=invalid-name
    redis_url: Optional[str] = None,
    redis_client: Optional[Any] = None,
    redis_db: int = 0,
    project: Optional[str] = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    default_algorithm: str = "sliding_window",
    default_backend: str = "redis",
    fail_open: bool = False,
) -> None:
    """Configure global defaults for all rate limiters.

    Args:
        redis_url: Redis connection URL (e.g. "redis://localhost:6379")
        redis_client: Pre-built Redis client (alternative to redis_url)
        redis_db: Redis database index when using redis_url
        project: Namespace prefix for all keys — use to isolate microservices
                 sharing the same Redis instance (e.g. "user-service")
        prefix: Optional key prefix added before project (e.g. "rl")
        suffix: Optional key suffix added after identifier (e.g. "v2")
        default_algorithm: Algorithm used when none is specified in @rate_limit
        default_backend: "redis" or "memory"
    """
    if redis_url is not None:
        if _redis_lib is None:
            raise ImportError("redis package required: pip install limitra")
        redis_client = _redis_lib.from_url(redis_url, db=redis_db)

    _ConfigStore.set(
        _Config(
            redis_client=redis_client or _ConfigStore.get().redis_client,
            project=project,
            prefix=prefix,
            suffix=suffix,
            default_algorithm=default_algorithm,
            default_backend=default_backend,
            fail_open=fail_open,
        )
    )


def get_config() -> _Config:
    """Return the active global configuration."""
    return _ConfigStore.get()


def reset_config() -> None:
    """Reset global configuration to defaults (used in tests)."""
    _ConfigStore.reset()
