"""Core limitra tests — decorator API, key generation, memory-backend algorithms."""

from typing import Any

import pytest

from limitra import (
    LIMITERS,
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    RateLimitExceeded,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
    LimitraConfig,
    rate_limit,
)

from .shared import ALGO_CLASSES, run_concurrent_requests

# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


class TestKeyGeneration:
    """Verify the key format produced by get_key()."""

    def test_default(self) -> None:
        """Default key: scope:identifier."""
        lim = SlidingWindowRateLimiter(capacity=10, fill_rate=1)
        assert lim.get_key("u1") == "user:u1"

    def test_project(self) -> None:
        """Project prefix is prepended before scope."""
        lim = SlidingWindowRateLimiter(capacity=10, fill_rate=1, project="svc")
        assert lim.get_key("u1") == "svc:user:u1"

    def test_prefix_and_project(self) -> None:
        """Both prefix and project appear in order."""
        lim = SlidingWindowRateLimiter(
            capacity=10, fill_rate=1, prefix="rl", project="svc"
        )
        assert lim.get_key("u1") == "rl:svc:user:u1"

    def test_suffix(self) -> None:
        """Suffix is appended after identifier."""
        lim = SlidingWindowRateLimiter(
            capacity=10, fill_rate=1, prefix="rl", suffix="v2"
        )
        assert lim.get_key("u1") == "rl:user:u1:v2"

    def test_all_parts(self) -> None:
        """All parts appear in the correct order."""
        lim = SlidingWindowRateLimiter(
            capacity=10, fill_rate=1, prefix="rl", project="svc", suffix="v2"
        )
        assert lim.get_key("u1") == "rl:svc:user:u1:v2"

    def test_global_scope_no_identifier(self) -> None:
        """Global scope omits the identifier."""
        lim = SlidingWindowRateLimiter(
            capacity=10, fill_rate=1, scope="global", project="svc"
        )
        assert lim.get_key(None) == "svc:global"

    def test_custom_scope(self) -> None:
        """Custom scope label is used instead of 'user'."""
        lim = SlidingWindowRateLimiter(capacity=10, fill_rate=1, scope="org")
        assert lim.get_key("acme") == "org:acme"


# ---------------------------------------------------------------------------
# Decorator — key extraction
# ---------------------------------------------------------------------------


class TestDecoratorKeys:
    """Verify the various key= modes of @rate_limit."""

    def test_global_no_key(self) -> None:
        """key=None creates a single shared counter."""

        @rate_limit(requests=2, window=3600)
        def fn() -> None:
            pass

        fn()
        fn()
        with pytest.raises(RateLimitExceeded):
            fn()

    def test_key_by_arg_name(self) -> None:
        """key='arg_name' extracts by argument name."""

        @rate_limit(requests=2, window=3600, key="user_id")
        def fn(user_id: Any, data: Any = None) -> Any:
            return user_id, data

        fn("alice")
        fn("alice")
        with pytest.raises(RateLimitExceeded):
            fn("alice")
        fn("bob")  # separate bucket

    def test_key_by_positional_index(self) -> None:
        """key=0 extracts the first positional argument."""

        @rate_limit(requests=2, window=3600, key=0)
        def fn(uid: Any) -> Any:
            return uid

        fn("alice")
        fn("alice")
        with pytest.raises(RateLimitExceeded):
            fn("alice")

    def test_key_by_callable(self) -> None:
        """key=callable is called with the function's args/kwargs."""

        @rate_limit(requests=2, window=3600, key=lambda uid, **_: uid)
        def fn(uid: Any, payload: Any = None) -> Any:
            return uid, payload

        fn("alice")
        fn("alice")
        with pytest.raises(RateLimitExceeded):
            fn("alice")

    def test_key_as_kwarg(self) -> None:
        """key='uid' resolves correctly when passed as a keyword argument."""

        @rate_limit(requests=2, window=3600, key="uid")
        def fn(uid: Any) -> Any:
            return uid

        fn(uid="x")
        fn(uid="x")
        with pytest.raises(RateLimitExceeded):
            fn(uid="x")

    def test_on_exceeded_callback_return_value(self) -> None:
        """on_exceeded return value becomes the decorated function's return value."""

        @rate_limit(requests=1, window=3600, on_exceeded=lambda e: "blocked")
        def fn() -> str:
            return "ok"

        assert fn() == "ok"
        assert fn() == "blocked"

    def test_on_exceeded_receives_exception(self) -> None:
        """on_exceeded receives a RateLimitExceeded with the correct fields."""
        captured = []

        @rate_limit(
            requests=1,
            window=3600,
            on_exceeded=lambda e: captured.append(e) or "blocked",  # type: ignore[func-returns-value]
        )
        def fn() -> str:
            return "ok"

        fn()
        fn()
        assert len(captured) == 1
        assert isinstance(captured[0], RateLimitExceeded)
        assert captured[0].requests == 1
        assert captured[0].window == 3600


# ---------------------------------------------------------------------------
# Async decorator
# ---------------------------------------------------------------------------


async def test_async_decorator() -> None:
    """@rate_limit works on async functions."""

    @rate_limit(requests=2, window=3600)
    async def afn() -> str:
        return "ok"

    assert await afn() == "ok"
    assert await afn() == "ok"
    with pytest.raises(RateLimitExceeded):
        await afn()


# ---------------------------------------------------------------------------
# RateLimitExceeded fields
# ---------------------------------------------------------------------------


class TestException:
    """Verify RateLimitExceeded attributes and string representation."""

    def test_fields(self) -> None:
        """requests, window, retry_after are set correctly."""
        exc = RateLimitExceeded(requests=10, window=60.0, retry_after=3.5)
        assert exc.requests == 10
        assert exc.window == 60.0
        assert exc.retry_after == 3.5
        assert "10" in str(exc)
        assert "60" in str(exc)
        assert "3.5" in str(exc)

    def test_zero_retry_after_not_in_message(self) -> None:
        """Retry-After is omitted from the message when retry_after=0."""
        exc = RateLimitExceeded(requests=5, window=30.0)
        assert "Retry" not in str(exc)


# ---------------------------------------------------------------------------
# All 4 algorithms — memory backend smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALGO_CLASSES, ids=lambda c: c.__name__)
class TestAlgorithmMemory:
    """Memory backend smoke tests for every algorithm."""

    def test_allows_within_limit(self, cls) -> None:
        """Requests up to capacity are all allowed."""
        lim = cls(capacity=5, fill_rate=1)
        assert all(lim.allow_request(f"u{i}") for i in range(5))
        lim2 = cls(capacity=5, fill_rate=1)
        results = [lim2.allow_request("u1") for _ in range(5)]
        assert all(results)

    def test_blocks_over_limit(self, cls) -> None:
        """Requests beyond capacity are blocked."""
        lim = cls(capacity=3, fill_rate=1)
        for _ in range(3):
            lim.allow_request("u1")
        assert lim.allow_request("u1") is False

    def test_reset_restores_access(self, cls) -> None:
        """reset() clears the counter and allows requests again."""
        lim = cls(capacity=1, fill_rate=1)
        assert lim.allow_request("u1") is True
        assert lim.allow_request("u1") is False
        lim.reset("u1")
        assert lim.allow_request("u1") is True

    def test_independent_per_identifier(self, cls) -> None:
        """Different identifiers have separate counters."""
        lim = cls(capacity=1, fill_rate=1)
        assert lim.allow_request("alice") is True
        assert lim.allow_request("alice") is False
        assert lim.allow_request("bob") is True

    def test_global_scope(self, cls) -> None:
        """Global scope shares a single counter across all identifiers."""
        lim = cls(capacity=2, fill_rate=1, scope="global")
        assert lim.allow_request(None) is True
        assert lim.allow_request(None) is True
        assert lim.allow_request(None) is False

    def test_get_config(self, cls) -> None:
        """get_config returns the expected keys and values."""
        lim = cls(capacity=10, fill_rate=2, project="svc", prefix="rl", suffix="v1")
        cfg = lim.get_config()
        assert cfg["capacity"] == 10
        assert cfg["project"] == "svc"
        assert cfg["prefix"] == "rl"
        assert cfg["suffix"] == "v1"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Concurrent correctness under the memory backend."""

    def test_concurrent_shared_bucket(self) -> None:
        """Exactly capacity requests are allowed under concurrent load."""
        capacity = 50
        lim = SlidingWindowRateLimiter(capacity=capacity, fill_rate=0.01)
        assert run_concurrent_requests(lim, "shared", 100) == capacity


# ---------------------------------------------------------------------------
# LimitraConfig() + decorator
# ---------------------------------------------------------------------------


class TestConfigure:
    """Verify that LimitraConfig() defaults are applied to @rate_limit."""

    def test_sets_defaults_for_decorator(self) -> None:
        """LimitraConfig() project/prefix/backend are picked up by the decorator."""
        LimitraConfig(project="test-svc", prefix="rl", default_backend="memory")

        @rate_limit(requests=2, window=3600, key="uid")
        def fn(uid: Any) -> Any:
            return uid

        fn("x")
        fn("x")
        with pytest.raises(RateLimitExceeded):
            fn("x")

    def test_per_decorator_project_overrides_global(self) -> None:
        """A project= on @rate_limit overrides the global LimitraConfig() project."""
        LimitraConfig(project="global-proj", default_backend="memory")

        @rate_limit(requests=2, window=3600, key="uid", project="local-proj")
        def fn(uid: Any) -> Any:
            return uid

        fn("x")
        fn("x")
        with pytest.raises(RateLimitExceeded):
            fn("x")


# ---------------------------------------------------------------------------
# LIMITERS registry
# ---------------------------------------------------------------------------


class TestRegistry:
    """Verify the LIMITERS dict contents."""

    def test_all_algorithms_present(self) -> None:
        """LIMITERS contains exactly the 4 supported algorithms."""
        assert set(LIMITERS) == {
            "token_bucket",
            "leaky_bucket",
            "fixed_window",
            "sliding_window",
        }

    def test_instances_have_required_methods(self) -> None:
        """Every algorithm class exposes allow_request, reset, and get_config."""
        for cls in LIMITERS.values():
            inst = cls(capacity=10, fill_rate=1)
            assert callable(inst.allow_request)
            assert callable(inst.reset)
            assert callable(inst.get_config)


# ---------------------------------------------------------------------------
# Multi-rate limits
# ---------------------------------------------------------------------------


class TestMultiRate:
    """Verify the limits= parameter applies multiple rate limits."""

    def test_all_limits_must_pass(self) -> None:
        """When limits= is given, ALL limits are enforced."""

        @rate_limit(limits=[(3, 3600), (1, 60)])
        def fn() -> str:
            return "ok"

        assert fn() == "ok"
        with pytest.raises(RateLimitExceeded):
            fn()

    def test_most_restrictive_limit_blocks(self) -> None:
        """The tightest limit triggers first."""

        @rate_limit(limits=[(100, 3600), (2, 60)])
        def fn() -> str:
            return "ok"

        fn()
        fn()
        with pytest.raises(RateLimitExceeded):
            fn()

    def test_single_limit_in_list(self) -> None:
        """limits= with one entry behaves like requests/window."""

        @rate_limit(limits=[(2, 3600)])
        def fn() -> str:
            return "ok"

        fn()
        fn()
        with pytest.raises(RateLimitExceeded):
            fn()

    def test_on_exceeded_called_with_multi_rate(self) -> None:
        """on_exceeded is called when any limit in limits= is exceeded."""
        blocked = []

        @rate_limit(  # type: ignore[func-returns-value]
            limits=[(1, 60)], on_exceeded=lambda e: blocked.append(e) or "blocked"
        )
        def fn() -> str:
            return "ok"

        assert fn() == "ok"
        assert fn() == "blocked"
        assert len(blocked) == 1


# ---------------------------------------------------------------------------
# block=False (soft mode)
# ---------------------------------------------------------------------------


class TestBlockFalse:
    """Verify block=False lets the function run even when limited."""

    def test_function_always_runs(self) -> None:
        """With block=False, the function still executes even when limited."""
        call_count = [0]

        @rate_limit(requests=1, window=3600, block=False)
        def fn() -> str:
            call_count[0] += 1
            return "ok"

        fn()
        fn()
        fn()
        assert call_count[0] == 3

    def test_on_exceeded_called_as_side_effect(self) -> None:
        """on_exceeded is called when limited but the function return value is used."""
        side_effects: list[RateLimitExceeded] = []

        @rate_limit(
            requests=1,
            window=3600,
            block=False,
            on_exceeded=side_effects.append,
        )
        def fn() -> str:
            return "real_value"

        assert fn() == "real_value"
        assert fn() == "real_value"
        assert len(side_effects) == 1

    def test_no_raise_when_block_false(self) -> None:
        """block=False never raises RateLimitExceeded even without on_exceeded."""

        @rate_limit(requests=1, window=3600, block=False)
        def fn() -> str:
            return "ok"

        fn()
        fn()


# ---------------------------------------------------------------------------
# exempt_when
# ---------------------------------------------------------------------------


class TestExemptWhen:
    """Verify exempt_when bypasses rate limiting."""

    def test_exempt_bypasses_limit(self) -> None:
        """When exempt_when returns True, the function always runs."""

        @rate_limit(requests=1, window=3600, exempt_when=lambda *a, **kw: True)
        def fn() -> str:
            return "ok"

        for _ in range(5):
            assert fn() == "ok"

    def test_non_exempt_still_limited(self) -> None:
        """When exempt_when returns False, limiting applies normally."""

        @rate_limit(requests=1, window=3600, exempt_when=lambda *a, **kw: False)
        def fn() -> str:
            return "ok"

        fn()
        with pytest.raises(RateLimitExceeded):
            fn()

    def test_exempt_when_receives_args(self) -> None:
        """exempt_when is called with the decorated function's args."""
        seen = []

        @rate_limit(
            requests=1,
            window=3600,
            exempt_when=lambda flag, *a, **kw: seen.append(flag) or flag,  # type: ignore[func-returns-value]
        )
        def fn(_flag: Any) -> str:
            return "ok"

        fn(True)
        fn(True)
        assert True in seen

    def test_selective_exemption(self) -> None:
        """Only calls where exempt_when returns True are exempt."""

        @rate_limit(requests=1, window=3600, key=0, exempt_when=lambda uid, *a, **kw: uid == "admin")
        def fn(uid: Any) -> Any:
            return uid

        fn("admin")
        fn("admin")
        fn("user")
        with pytest.raises(RateLimitExceeded):
            fn("user")


# ---------------------------------------------------------------------------
# fail_open
# ---------------------------------------------------------------------------


class TestFailOpen:
    """Verify fail_open=True allows requests on backend errors."""

    def test_fail_open_false_default(self) -> None:
        """fail_open defaults to False."""
        lim = SlidingWindowRateLimiter(capacity=5, fill_rate=1)
        assert lim.fail_open is False

    def test_fail_open_stored_on_limiter(self) -> None:
        """fail_open=True is stored on the limiter."""
        lim = FixedWindowRateLimiter(capacity=5, fill_rate=1, fail_open=True)
        assert lim.fail_open is True

    def test_fail_open_via_LimitraConfig(self) -> None:  # pylint: disable=invalid-name
        """LimitraConfig(fail_open=True) propagates to limiters built by @rate_limit."""
        LimitraConfig(fail_open=True, default_backend="memory")

        @rate_limit(requests=2, window=3600)
        def fn() -> str:
            return "ok"

        fn()
        fn()

    def test_fail_open_stored_on_all_algorithms(self) -> None:
        """fail_open=True is accepted and stored by every algorithm."""
        for cls in ALGO_CLASSES:
            lim = cls(capacity=5, fill_rate=1, fail_open=True)
            assert lim.fail_open is True


# ---------------------------------------------------------------------------
# get_usage() — memory backend
# ---------------------------------------------------------------------------


_USAGE_ALGO_CLASSES = [
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
]


@pytest.mark.parametrize("cls", _USAGE_ALGO_CLASSES, ids=lambda c: c.__name__)
class TestGetUsageMemory:
    """Verify get_usage() returns the expected schema for all algorithms."""

    def test_get_usage_keys(self, cls) -> None:
        """get_usage returns count, limit, remaining, limited."""
        lim = cls(capacity=5, fill_rate=1)
        usage = lim.get_usage("u1")
        assert "count" in usage
        assert "limit" in usage
        assert "remaining" in usage
        assert "limited" in usage

    def test_get_usage_initial_state(self, cls) -> None:
        """Before any requests, count=0, remaining=limit, limited=False."""
        lim = cls(capacity=5, fill_rate=1)
        usage = lim.get_usage("fresh_user")
        assert usage["limit"] == 5
        assert usage["limited"] is False

    def test_get_usage_after_requests(self, cls) -> None:
        """After consuming all capacity, limited=True."""
        lim = cls(capacity=3, fill_rate=1)
        for _ in range(3):
            lim.allow_request("u1")
        usage = lim.get_usage("u1")
        assert usage["limited"] is True

    def test_get_usage_limit_equals_capacity(self, cls) -> None:
        """limit field always equals the configured capacity."""
        lim = cls(capacity=10, fill_rate=2)
        assert lim.get_usage("u1")["limit"] == 10

    def test_get_usage_remaining_non_negative(self, cls) -> None:
        """remaining is never negative even after exceeding capacity."""
        lim = cls(capacity=2, fill_rate=1)
        for _ in range(5):
            lim.allow_request("u1")
        usage = lim.get_usage("u1")
        assert usage["remaining"] >= 0
