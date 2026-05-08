"""Token bucket rate limiter: allows bursts up to capacity, then throttles."""

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
local tokens, last_fill
if data then
    local s = cjson.decode(data)
    tokens = tonumber(s.tokens)
    last_fill = tonumber(s.last_fill)
    tokens = math.min(capacity, tokens + (now - last_fill) * fill_rate)
else
    redis.call('SETEX', key, ttl, cjson.encode({tokens=capacity-1, last_fill=now}))
    return 1
end
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('SETEX', key, ttl, cjson.encode({tokens=tokens, last_fill=now}))
return allowed
"""


class TokenBucketLimiter(BaseRateLimiter):
    """Allows bursts up to capacity, then throttles to fill_rate tokens/sec."""

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

    def _current_tokens(self, data: Any, now: float) -> float:
        return min(
            self.capacity,
            float(data["tokens"]) + (now - float(data["last_fill"])) * self.fill_rate,
        )

    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """Return True if a token is available; consume it and return False otherwise."""
        key = self.get_key(identifier)
        now = time.time()
        if self.backend == "redis":
            try:
                result = self._redis.eval(
                    _LUA_SCRIPT, 1, key, self.capacity, self.fill_rate, now, self._ttl
                )
                return bool(result)
            except _RedisError:
                if self.fail_open:
                    return True
        return self._allow_memory(key, now)

    def _allow_memory(self, key: str, now: float) -> bool:
        """In-memory token bucket logic protected by a per-key lock."""
        with self._get_key_lock(key):
            data = self._get_from_backend(key)
            if data is None:
                self._set_to_backend(
                    key, {"tokens": self.capacity - 1, "last_fill": now}, self._ttl
                )
                return True
            tokens = self._current_tokens(data, now)
            if tokens >= 1:
                self._set_to_backend(
                    key, {"tokens": tokens - 1, "last_fill": now}, self._ttl
                )
                return True
            self._set_to_backend(key, {"tokens": tokens, "last_fill": now}, self._ttl)
            return False

    def get_wait_time(self, identifier: Optional[str] = None) -> float:
        """Return seconds until the next token is available (0 if tokens remain)."""
        _, now, data = self._get_state(identifier)
        if data is None:
            return 0.0
        tokens = self._current_tokens(data, now)
        return max(0.0, (1 - tokens) / self.fill_rate) if tokens < 1 else 0.0

    def get_status(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return current token count and utilisation for the given identifier."""
        _, now, data = self._get_state(identifier)
        if data is None:
            return {"tokens_remaining": self.capacity, "capacity": self.capacity}
        tokens = self._current_tokens(data, now)
        return {
            "tokens_remaining": round(tokens, 2),
            "capacity": self.capacity,
            "utilization_pct": round((1 - tokens / self.capacity) * 100, 1),
        }

    def get_usage(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Return usage information in a consistent format."""
        _, now, data = self._get_state(identifier)
        tokens = self._current_tokens(data, now) if data is not None else float(self.capacity)
        return {
            "count": int(self.capacity - tokens),
            "limit": self.capacity,
            "remaining": int(tokens),
            "limited": tokens < 1,
        }
