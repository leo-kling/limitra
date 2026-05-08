"""Shared constants and helpers for the limitra test suite."""

import threading
from typing import Union

from limitra import (
    FixedWindowRateLimiter,
    LeakyBucketLimiter,
    SlidingWindowRateLimiter,
    TokenBucketLimiter,
)
from limitra.base import BaseRateLimiter

AlgoClass = Union[
    type[TokenBucketLimiter],
    type[LeakyBucketLimiter],
    type[FixedWindowRateLimiter],
    type[SlidingWindowRateLimiter],
]

ALGO_CLASSES: list[AlgoClass] = [
    TokenBucketLimiter,
    LeakyBucketLimiter,
    FixedWindowRateLimiter,
    SlidingWindowRateLimiter,
]


def run_concurrent_requests(
    limiter: BaseRateLimiter, identifier: str, workers: int
) -> int:
    """Spawn workers concurrent allow_request calls; return the number allowed."""
    allowed = []
    lock = threading.Lock()

    def worker() -> None:
        """Single worker thread."""
        result = limiter.allow_request(identifier)
        with lock:
            allowed.append(result)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return sum(allowed)
