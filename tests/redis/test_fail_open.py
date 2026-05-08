"""fail_open Redis tests — allow requests when Redis is unavailable."""

import redis

from limitra import (
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
)


# ---------------------------------------------------------------------------
# fail_open — Redis backend
# ---------------------------------------------------------------------------


class TestFailOpenRedis:
    """Verify fail_open=True allows requests when Redis is unavailable."""

    def _bad_redis(self) -> redis.Redis:
        """Return a Redis client pointing at a non-existent server."""
        return redis.Redis(host="127.0.0.1", port=19999, socket_connect_timeout=0.05)

    def test_fail_open_fixed_window(self) -> None:
        """FixedWindowRateLimiter with fail_open=True allows on RedisError."""
        lim = FixedWindowRateLimiter(
            capacity=5,
            fill_rate=1,
            backend="redis",
            redis_client=self._bad_redis(),
            fail_open=True,
        )
        assert lim.allow_request("u1") is True

    def test_fail_open_leaky_bucket(self) -> None:
        """LeakyBucketLimiter with fail_open=True allows on RedisError."""
        lim = LeakyBucketLimiter(
            capacity=5,
            fill_rate=1,
            backend="redis",
            redis_client=self._bad_redis(),
            fail_open=True,
        )
        assert lim.allow_request("u1") is True

    def test_fail_open_sliding_window(self) -> None:
        """SlidingWindowRateLimiter with fail_open=True allows on RedisError."""
        lim = SlidingWindowRateLimiter(
            capacity=5,
            fill_rate=1,
            backend="redis",
            redis_client=self._bad_redis(),
            fail_open=True,
        )
        assert lim.allow_request("u1") is True

    def test_fail_open_token_bucket(self) -> None:
        """TokenBucketLimiter with fail_open=True allows on RedisError."""
        lim = TokenBucketLimiter(
            capacity=5,
            fill_rate=1,
            backend="redis",
            redis_client=self._bad_redis(),
            fail_open=True,
        )
        assert lim.allow_request("u1") is True
