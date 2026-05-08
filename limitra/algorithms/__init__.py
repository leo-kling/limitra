"""Rate-limiting algorithm implementations."""

from typing import Any, Dict

from .fixed_window import FixedWindowRateLimiter
from .leaky_bucket import LeakyBucketLimiter
from .sliding_window import SlidingWindowRateLimiter
from .token_bucket import TokenBucketLimiter

LIMITERS: Dict[str, Any] = {
    "token_bucket": TokenBucketLimiter,
    "leaky_bucket": LeakyBucketLimiter,
    "fixed_window": FixedWindowRateLimiter,
    "sliding_window": SlidingWindowRateLimiter,
}

__all__ = [
    "FixedWindowRateLimiter",
    "LeakyBucketLimiter",
    "SlidingWindowRateLimiter",
    "TokenBucketLimiter",
    "LIMITERS",
]
