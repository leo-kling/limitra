"""Exceptions raised by limitra rate limiters."""


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded and no on_exceeded handler is set."""

    def __init__(self, requests: int, window: float, retry_after: float = 0.0):
        self.requests = requests
        self.window = window
        self.retry_after = retry_after
        self.remaining = 0
        msg = f"Rate limit exceeded: {requests} requests per {window}s"
        if retry_after:
            msg += f". Retry after {retry_after:.2f}s"
        super().__init__(msg)
