"""Base class for all limitra rate limiter implementations."""

import json
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class BaseRateLimiter(ABC):
    """Abstract base for all rate limiters.

    Provides backend storage helpers, key generation, and thread-safe
    per-key locking used by every concrete algorithm.
    """

    def __init__(
        self,
        capacity: int,
        fill_rate: float,
        scope: str = "user",
        backend: str = "memory",
        redis_client: Optional[Any] = None,
        project: Optional[str] = None,
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        fail_open: bool = False,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if fill_rate <= 0:
            raise ValueError("fill_rate must be positive")
        if backend not in ("memory", "redis"):
            raise ValueError("backend must be 'memory' or 'redis'")
        if backend == "redis" and redis_client is None:
            raise ValueError("redis_client is required when backend='redis'")

        self.capacity = capacity
        self.fill_rate = fill_rate
        self.scope = scope
        self.backend = backend
        self.redis_client = redis_client
        self.project = project
        self.prefix = prefix
        self.suffix = suffix
        self.fail_open = fail_open

        self._memory_storage: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._key_locks: Dict[str, threading.Lock] = {}
        self._key_locks_lock = threading.Lock()

    def _get_key_lock(self, key: str) -> threading.Lock:
        """Return a per-key Lock, creating it lazily."""
        with self._key_locks_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    @property
    def _redis(self) -> Any:
        """Narrowed, non-optional access to redis_client (only valid when backend='redis')."""
        assert self.redis_client is not None
        return self.redis_client

    def get_key(self, identifier: Optional[str] = None) -> str:
        """Build the storage key for the given identifier.

        Format: [prefix:][ project:]scope[:identifier][:suffix]
        """
        parts = []
        if self.prefix:
            parts.append(self.prefix)
        if self.project:
            parts.append(self.project)
        parts.append(self.scope)
        if self.scope != "global" and identifier is not None:
            parts.append(str(identifier))
        if self.suffix:
            parts.append(self.suffix)
        return ":".join(parts)

    def _get_state(self, identifier: Optional[str]) -> Tuple[str, float, Any]:
        """Return (key, now, stored_data) — shared prelude for status/wait methods."""
        key = self.get_key(identifier)
        return key, time.time(), self._get_from_backend(key)

    def _get_from_backend(self, key: str) -> Optional[Any]:
        """Fetch the stored value for key from the active backend."""
        if self.backend == "memory":
            with self._lock:
                return self._memory_storage.get(key)
        data = self._redis.get(key)
        return json.loads(data) if data else None

    def _set_to_backend(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Persist value for key in the active backend."""
        if self.backend == "memory":
            with self._lock:
                self._memory_storage[key] = value
        else:
            self._redis.set(key, json.dumps(value))
            if ttl:
                self._redis.expire(key, int(ttl))

    def _delete_from_backend(self, key: str) -> None:
        """Delete key from the active backend."""
        if self.backend == "memory":
            with self._lock:
                self._memory_storage.pop(key, None)
        else:
            self._redis.delete(key)

    @abstractmethod
    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """Return True if the request is allowed, False if the limit is exceeded."""

    def reset(self, identifier: Optional[str] = None) -> None:
        """Reset rate limit counters for the given identifier."""
        self._delete_from_backend(self.get_key(identifier))

    def get_wait_time(self, _identifier: Optional[str] = None) -> float:
        """Return seconds until the next request is allowed (0 if allowed now)."""
        return 0.0

    def get_usage(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return usage in a consistent format: count, limit, remaining, limited."""
        status = self.get_status(identifier)
        count: int = status["count"]
        available: int = status["available"]
        return {
            "count": count,
            "limit": self.capacity,
            "remaining": available,
            "limited": count >= self.capacity,
        }

    def get_status(self, _identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return algorithm-specific status for the given identifier."""
        return {"count": 0, "capacity": self.capacity, "available": self.capacity}

    def get_config(self) -> Dict[str, Any]:
        """Return a dictionary of the limiter's configuration."""
        return {
            "capacity": self.capacity,
            "fill_rate": self.fill_rate,
            "scope": self.scope,
            "backend": self.backend,
            "project": self.project,
            "prefix": self.prefix,
            "suffix": self.suffix,
        }
