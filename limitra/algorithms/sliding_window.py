"""Sliding window rate limiter: weighted count prevents boundary bursts."""

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
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local data = redis.call('GET', key)
local slot = math.floor(now / window)
local curr, prev, stored_slot
if data then
    local s = cjson.decode(data)
    curr = tonumber(s.curr)
    prev = tonumber(s.prev)
    stored_slot = tonumber(s.slot)
else
    curr = 0
    prev = 0
    stored_slot = slot
end
if stored_slot < slot then
    prev = (stored_slot == slot - 1) and curr or 0
    curr = 0
    stored_slot = slot
end
local elapsed_pct = (now % window) / window
local weighted = curr + (1 - elapsed_pct) * prev
local allowed = 0
if weighted < capacity then
    curr = curr + 1
    allowed = 1
end
redis.call('SETEX', key, ttl, cjson.encode({slot=stored_slot, curr=curr, prev=prev}))
return allowed
"""


class SlidingWindowRateLimiter(BaseRateLimiter):
    """Best general-purpose choice: fast and prevents boundary bursts via weighted count."""

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
        self._ttl = int(self._window * 3) + 60

    def _resolve_window(self, data: Optional[Any], now: float) -> "tuple[int, int, int, float]":
        """Return (slot, curr, prev, weighted_count) with slot-advance applied."""
        slot = int(now / self._window)
        if data is None:
            return slot, 0, 0, 0.0
        stored_slot = int(data["slot"])
        curr = int(data["curr"])
        prev = int(data["prev"])
        if stored_slot < slot:
            prev = curr if stored_slot == slot - 1 else 0
            curr = 0
        elapsed_pct = (now % self._window) / self._window
        return slot, curr, prev, curr + (1 - elapsed_pct) * prev

    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """Return True if the weighted request count is below capacity."""
        key = self.get_key(identifier)
        now = time.time()
        if self.backend == "redis":
            try:
                result = self._redis.eval(
                    _LUA_SCRIPT, 1, key, self.capacity, self._window, now, self._ttl
                )
                return bool(result)
            except _RedisError:
                if self.fail_open:
                    return True
        return self._allow_memory(key, now)

    def _allow_memory(self, key: str, now: float) -> bool:
        """In-memory sliding window logic protected by a per-key lock."""
        with self._get_key_lock(key):
            data = self._get_from_backend(key)
            slot, curr, prev, weighted = self._resolve_window(data, now)
            allowed = weighted < self.capacity
            if allowed:
                curr += 1
            self._set_to_backend(key, {"slot": slot, "curr": curr, "prev": prev}, self._ttl)
            return allowed

    def get_wait_time(self, identifier: Optional[str] = None) -> float:
        """Return seconds until the weighted count will drop below capacity (0 if allowed)."""
        _, now, data = self._get_state(identifier)
        if data is None:
            return 0.0
        _, curr, prev, weighted = self._resolve_window(data, now)
        if weighted < self.capacity:
            return 0.0
        if prev > 0 and curr < self.capacity:
            needed_elapsed = self._window * (1 - (self.capacity - curr) / prev)
            wait = needed_elapsed - (now % self._window)
            if wait > 0:
                return wait
        return self._window - (now % self._window)

    def get_status(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return weighted request count and remaining capacity."""
        _, now, data = self._get_state(identifier)
        if data is None:
            return {"count": 0, "capacity": self.capacity, "available": self.capacity}
        _, _, _, weighted = self._resolve_window(data, now)
        weighted_int = int(weighted)
        return {
            "count": weighted_int,
            "capacity": self.capacity,
            "available": max(0, self.capacity - weighted_int),
        }
