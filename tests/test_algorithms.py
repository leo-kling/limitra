"""Per-algorithm tests covering memory backend specifics."""

import time

from limitra import (
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
)

# ---------------------------------------------------------------------------
# TokenBucketLimiter specifics
# ---------------------------------------------------------------------------


class TestTokenBucket:
    """Tests specific to the token bucket algorithm."""

    def test_get_wait_time_zero_when_allowed(self) -> None:
        """Wait time is 0 when tokens are available."""
        lim = TokenBucketLimiter(capacity=5, fill_rate=1)
        assert lim.get_wait_time("u1") == 0.0

    def test_get_wait_time_positive_when_blocked(self) -> None:
        """Wait time is positive after the bucket is exhausted."""
        lim = TokenBucketLimiter(capacity=1, fill_rate=0.5)
        lim.allow_request("u1")
        assert lim.get_wait_time("u1") > 0

    def test_get_status_keys(self) -> None:
        """get_status returns tokens_remaining and capacity."""
        lim = TokenBucketLimiter(capacity=5, fill_rate=1)
        lim.allow_request("u1")
        status = lim.get_status("u1")
        assert "tokens_remaining" in status
        assert "capacity" in status
        assert status["capacity"] == 5

    def test_tokens_replenish_over_time(self) -> None:
        """Tokens refill at fill_rate after exhaustion."""
        lim = TokenBucketLimiter(capacity=2, fill_rate=2)
        lim.allow_request("u1")
        lim.allow_request("u1")
        assert lim.allow_request("u1") is False
        time.sleep(0.6)
        assert lim.allow_request("u1") is True


# ---------------------------------------------------------------------------
# LeakyBucketLimiter specifics
# ---------------------------------------------------------------------------


class TestLeakyBucket:
    """Tests specific to the leaky bucket algorithm."""

    def test_get_wait_time_zero_when_empty(self) -> None:
        """Wait time is 0 when the bucket is empty."""
        lim = LeakyBucketLimiter(capacity=5, fill_rate=1)
        assert lim.get_wait_time("u1") == 0.0

    def test_get_wait_time_positive_when_full(self) -> None:
        """Wait time is positive when the bucket is full."""
        lim = LeakyBucketLimiter(capacity=1, fill_rate=0.5)
        lim.allow_request("u1")
        assert lim.get_wait_time("u1") > 0

    def test_get_status_keys(self) -> None:
        """get_status returns water_level and available."""
        lim = LeakyBucketLimiter(capacity=5, fill_rate=1)
        lim.allow_request("u1")
        status = lim.get_status("u1")
        assert "water_level" in status
        assert "available" in status

    def test_level_drops_over_time(self) -> None:
        """Water level drains at fill_rate after the bucket fills."""
        lim = LeakyBucketLimiter(capacity=1, fill_rate=2)
        lim.allow_request("u1")
        assert lim.allow_request("u1") is False
        time.sleep(0.6)
        assert lim.allow_request("u1") is True


# ---------------------------------------------------------------------------
# FixedWindowRateLimiter specifics
# ---------------------------------------------------------------------------


class TestFixedWindow:
    """Tests specific to the fixed window algorithm."""

    def test_get_status_keys(self) -> None:
        """get_status returns count and available."""
        lim = FixedWindowRateLimiter(capacity=5, fill_rate=1)
        lim.allow_request("u1")
        status = lim.get_status("u1")
        assert "count" in status
        assert "available" in status
        assert status["count"] == 1


# ---------------------------------------------------------------------------
# SlidingWindowRateLimiter specifics
# ---------------------------------------------------------------------------


class TestSlidingWindow:
    """Tests specific to the sliding window algorithm."""

    def test_weighted_count_prevents_bursts(self) -> None:
        """Sliding window should reject bursts that exceed capacity across boundary."""
        lim = SlidingWindowRateLimiter(capacity=3, fill_rate=1)
        lim.allow_request("u1")
        lim.allow_request("u1")
        lim.allow_request("u1")
        assert lim.allow_request("u1") is False
