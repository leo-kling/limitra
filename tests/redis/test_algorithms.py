"""Redis backend algorithm tests — all 4 algorithms, key isolation, thread safety."""

import pytest

from limitra import (
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
)

from ..shared import ALGO_CLASSES, run_concurrent_requests

# ---------------------------------------------------------------------------
# Redis backend — all 4 algorithms (testcontainers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALGO_CLASSES, ids=lambda c: c.__name__)
class TestAlgorithmRedis:
    """Redis backend tests for every algorithm."""

    def test_allows_within_limit(self, cls, redis_client) -> None:
        """All requests below capacity are allowed."""
        lim = cls(capacity=5, fill_rate=1, backend="redis", redis_client=redis_client)
        results = [lim.allow_request("u1") for _ in range(5)]
        assert all(results)

    def test_blocks_over_limit(self, cls, redis_client) -> None:
        """Requests beyond capacity are blocked."""
        lim = cls(capacity=3, fill_rate=1, backend="redis", redis_client=redis_client)
        for _ in range(3):
            lim.allow_request("u1")
        assert lim.allow_request("u1") is False

    def test_reset_restores_access(self, cls, redis_client) -> None:
        """reset() clears the counter and allows requests again."""
        lim = cls(capacity=1, fill_rate=1, backend="redis", redis_client=redis_client)
        assert lim.allow_request("u1") is True
        assert lim.allow_request("u1") is False
        lim.reset("u1")
        assert lim.allow_request("u1") is True

    def test_independent_per_identifier(self, cls, redis_client) -> None:
        """Different identifiers have separate counters."""
        lim = cls(capacity=1, fill_rate=1, backend="redis", redis_client=redis_client)
        assert lim.allow_request("alice") is True
        assert lim.allow_request("alice") is False
        assert lim.allow_request("bob") is True

    def test_global_scope(self, cls, redis_client) -> None:
        """Global scope shares a single counter across all identifiers."""
        lim = cls(
            capacity=2,
            fill_rate=1,
            scope="global",
            backend="redis",
            redis_client=redis_client,
        )
        assert lim.allow_request(None) is True
        assert lim.allow_request(None) is True
        assert lim.allow_request(None) is False


# ---------------------------------------------------------------------------
# Redis key isolation: two projects on the same Redis instance
# ---------------------------------------------------------------------------


class TestRedisKeyIsolation:
    """Verify that project and prefix namespacing isolates counters."""

    def test_project_namespacing(self, redis_client) -> None:
        """Two limiters with different projects share no counters."""
        lim_a = SlidingWindowRateLimiter(
            capacity=1,
            fill_rate=1,
            project="svc-a",
            backend="redis",
            redis_client=redis_client,
        )
        lim_b = SlidingWindowRateLimiter(
            capacity=1,
            fill_rate=1,
            project="svc-b",
            backend="redis",
            redis_client=redis_client,
        )
        assert lim_a.allow_request("u1") is True
        assert lim_a.allow_request("u1") is False
        assert lim_b.allow_request("u1") is True

    def test_prefix_isolation(self, redis_client) -> None:
        """Two limiters with different prefixes share no counters."""
        lim1 = FixedWindowRateLimiter(
            capacity=1,
            fill_rate=1,
            prefix="app1",
            backend="redis",
            redis_client=redis_client,
        )
        lim2 = FixedWindowRateLimiter(
            capacity=1,
            fill_rate=1,
            prefix="app2",
            backend="redis",
            redis_client=redis_client,
        )
        assert lim1.allow_request("u1") is True
        assert lim1.allow_request("u1") is False
        assert lim2.allow_request("u1") is True


# ---------------------------------------------------------------------------
# Thread safety — Redis backend
# ---------------------------------------------------------------------------


class TestRedisThreadSafety:
    """Concurrent correctness under the Redis backend."""

    def test_concurrent_requests(self, redis_client) -> None:
        """Exactly capacity requests are allowed under concurrent load."""
        capacity = 30
        lim = SlidingWindowRateLimiter(
            capacity=capacity,
            fill_rate=0.01,
            backend="redis",
            redis_client=redis_client,
        )
        assert run_concurrent_requests(lim, "shared", 60) == capacity


# ---------------------------------------------------------------------------
# get_usage() — Redis backend
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        FixedWindowRateLimiter,
        LeakyBucketLimiter,
        SlidingWindowRateLimiter,
        TokenBucketLimiter,
    ],
    ids=lambda c: c.__name__,
)
class TestGetUsageRedis:
    """Verify get_usage() works correctly with the Redis backend."""

    def test_get_usage_keys(self, cls, redis_client) -> None:
        """get_usage returns count, limit, remaining, limited."""
        lim = cls(capacity=5, fill_rate=1, backend="redis", redis_client=redis_client)
        usage = lim.get_usage("u1")
        assert "count" in usage
        assert "limit" in usage
        assert "remaining" in usage
        assert "limited" in usage

    def test_get_usage_after_exhaustion(self, cls, redis_client) -> None:
        """After consuming all capacity, limited=True."""
        lim = cls(capacity=3, fill_rate=1, backend="redis", redis_client=redis_client)
        for _ in range(3):
            lim.allow_request("u1")
        usage = lim.get_usage("u1")
        assert usage["limited"] is True

    def test_get_usage_limit_equals_capacity(self, cls, redis_client) -> None:
        """limit field equals configured capacity."""
        lim = cls(capacity=10, fill_rate=2, backend="redis", redis_client=redis_client)
        assert lim.get_usage("u1")["limit"] == 10
