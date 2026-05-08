"""Leaky bucket rate limiter: smooths traffic by draining at a constant rate."""

import time
from typing import Any, Dict, Optional

from ..base import BaseRateLimiter

try:
    from redis import RedisError as _RedisError
except ImportError:
    _RedisError = Exception  # type: ignore[assignment,misc]


_LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local fill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local data = redis.call('GET', key)
local level, last
if data then
    local s = cjson.decode(data)
    level = tonumber(s.level)
    last = tonumber(s.last)
else
    level = 0
    last = now
end
level = math.max(0, level - (now - last) * fill_rate)
local allowed = 0
if level + 1 <= capacity then
    level = level + 1
    allowed = 1
end
redis.call('SETEX', key, ttl, cjson.encode({level=level, last=now}))
return {allowed, level}
"""


class LeakyBucketLimiter(BaseRateLimiter):
    """Smooths traffic: requests drain at fill_rate/sec, bursts are absorbed up to capacity."""

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
        self._ttl = int((capacity / fill_rate) * 2) + 60

    def _current_level(self, data: Any, now: float) -> float:
        return max(0.0, float(data["level"]) - (now - float(data["last"])) * self.fill_rate)

    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """Return True if the bucket has room; add one unit and return False otherwise."""
        key = self.get_key(identifier)
        if self.backend == "redis":
            try:
                result = self._redis.eval(
                    _LUA_SCRIPT,
                    1,
                    key,
                    self.capacity,
                    self.fill_rate,
                    time.time(),
                    self._ttl,
                )
                return bool(result[0])
            except _RedisError:
                if self.fail_open:
                    return True
        return self._allow_memory(key)

    def _allow_memory(self, key: str) -> bool:
        """In-memory leaky bucket logic protected by a per-key lock."""
        now = time.time()
        with self._get_key_lock(key):
            data = self._get_from_backend(key)
            if data is None:
                self._set_to_backend(key, {"level": 1.0, "last": now}, self._ttl)
                return True
            level = self._current_level(data, now)
            if level + 1 <= self.capacity:
                self._set_to_backend(key, {"level": level + 1, "last": now}, self._ttl)
                return True
            self._set_to_backend(key, {"level": level, "last": now}, self._ttl)
            return False

    def get_wait_time(self, identifier: Optional[str] = None) -> float:
        """Return seconds until the bucket drains enough to accept a request."""
        _, now, data = self._get_state(identifier)
        if data is None:
            return 0.0
        level = self._current_level(data, now)
        if level + 1 <= self.capacity:
            return 0.0
        return max(0.0, (level + 1 - self.capacity) / self.fill_rate)

    def get_status(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return current water level and available capacity for the given identifier."""
        _, now, data = self._get_state(identifier)
        if data is None:
            return {"water_level": 0.0, "capacity": self.capacity, "available": float(self.capacity)}
        level = self._current_level(data, now)
        return {
            "water_level": round(level, 2),
            "capacity": self.capacity,
            "available": round(max(0.0, self.capacity - level), 2),
            "utilization_pct": round((level / self.capacity) * 100, 1),
        }

    def get_usage(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return usage information in a consistent format."""
        _, now, data = self._get_state(identifier)
        water_level = self._current_level(data, now) if data is not None else 0.0
        return {
            "count": int(water_level),
            "limit": self.capacity,
            "remaining": max(0, int(self.capacity - water_level)),
            "limited": water_level + 1 > self.capacity,
        }
