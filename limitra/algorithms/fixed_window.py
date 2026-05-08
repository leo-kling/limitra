"""Fixed window rate limiter: counts requests per discrete time slot."""

import time
from typing import Any, Dict, Optional

from ..base import BaseRateLimiter

try:
    from redis import RedisError as _RedisError
except ImportError:
    _RedisError = Exception  # type: ignore[assignment,misc]

_LUA_SCRIPT = """
local window_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local count = redis.call('INCR', window_key)
if count == 1 then
    redis.call('EXPIRE', window_key, ttl)
end
return count <= capacity and 1 or 0
"""


class FixedWindowRateLimiter(BaseRateLimiter):
    """Fastest algorithm. Counts requests per fixed time slot.

    Known caveat: allows 2× capacity at window boundaries.
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
        super().__init__(
            capacity,
            fill_rate,
            scope,
            backend,
            redis_client,
            project,
            prefix,
            suffix,
            fail_open,
        )
        self._window = 1 / fill_rate
        self._ttl = int(self._window * 2) + 60

    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """Return True if the request count for the current window slot is below capacity."""
        key = self.get_key(identifier)
        now = time.time()
        slot = int(now / self._window)
        if self.backend == "redis":
            try:
                window_key = f"{key}:{slot}"
                result = self._redis.eval(
                    _LUA_SCRIPT, 1, window_key, self.capacity, self._ttl
                )
                return bool(result)
            except _RedisError:
                if self.fail_open:
                    return True
        return self._allow_memory(key, slot)

    def _allow_memory(self, key: str, slot: int) -> bool:
        """In-memory fixed window logic protected by a per-key lock."""
        with self._get_key_lock(key):
            data = self._get_from_backend(key)
            if data is None or int(data["slot"]) < slot:
                self._set_to_backend(key, {"count": 1, "slot": slot}, self._ttl)
                return True
            if data["count"] < self.capacity:
                self._set_to_backend(
                    key, {"count": data["count"] + 1, "slot": slot}, self._ttl
                )
                return True
            return False

    def get_wait_time(self, identifier: Optional[str] = None) -> float:
        """Return seconds until the current window slot resets (0 if requests are allowed)."""
        key = self.get_key(identifier)
        now = time.time()
        slot = int(now / self._window)
        if self.backend == "redis":
            try:
                raw = self._redis.get(f"{key}:{slot}")
                count = int(raw) if raw else 0
            except Exception:  # pylint: disable=broad-except
                return 0.0
        else:
            data = self._get_from_backend(key)
            count = int(data["count"]) if (data and int(data["slot"]) == slot) else 0
        if count < self.capacity:
            return 0.0
        return self._window - (now % self._window)

    def reset(self, identifier: Optional[str] = None) -> None:
        """Reset counters. For Redis, deletes the window-specific slot key."""
        key = self.get_key(identifier)
        if self.backend == "redis":
            slot = int(time.time() / self._window)
            self._redis.delete(f"{key}:{slot}")
        else:
            self._delete_from_backend(key)

    def get_status(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return request count and remaining capacity for the current window slot."""
        key = self.get_key(identifier)
        now = time.time()
        slot = int(now / self._window)
        if self.backend == "redis":
            try:
                raw = self._redis.get(f"{key}:{slot}")
                count = int(raw) if raw else 0
            except _RedisError:
                count = 0
        else:
            _, _, data = self._get_state(identifier)
            count = int(data["count"]) if (data and int(data["slot"]) == slot) else 0
        return {
            "count": count,
            "capacity": self.capacity,
            "available": max(0, self.capacity - count),
        }
