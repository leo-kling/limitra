"""limitra — simple, framework-agnostic rate limiting for Python."""

from ._config import LimitraConfig
from ._decorator import rate_limit
from .algorithms import (
    LIMITERS,
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
)
from .base import BaseRateLimiter
from .exceptions import RateLimitExceeded

from ._version import __version__

__all__ = [
    "LimitraConfig",
    "rate_limit",
    "RateLimitExceeded",
    "BaseRateLimiter",
    "TokenBucketLimiter",
    "LeakyBucketLimiter",
    "FixedWindowRateLimiter",
    "SlidingWindowRateLimiter",
    "LIMITERS",
]
