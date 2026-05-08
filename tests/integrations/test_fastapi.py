"""Confirm that @rate_limit works on FastAPI sync and async routes."""

from typing import Any

import pytest

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from limitra import LimitraConfig, rate_limit, RateLimitExceeded
except ImportError as _exc:
    pytest.skip(f"fastapi or httpx not installed — {_exc}", allow_module_level=True)


def _on_exceeded(exc: RateLimitExceeded) -> JSONResponse:
    """Return a 429 JSON response."""
    return JSONResponse({"error": "Too Many Requests", "retry_after": exc.retry_after}, status_code=429)


def _client(requests: int, *, sync: bool, key: Any = None, redis_client: Any = None) -> "TestClient":
    """Create a FastAPI test client with a rate-limited endpoint."""
    app = FastAPI()
    kwargs: dict[str, Any] = {"requests": requests, "window": 3600, "on_exceeded": _on_exceeded}
    if key is not None:
        kwargs["key"] = key
    if redis_client is not None:
        kwargs["backend"] = "redis"
        kwargs["redis_client"] = redis_client

    if sync:
        @app.get("/test")
        @rate_limit(**kwargs)
        def endpoint(_request: Request) -> dict[str, bool]:
            """Sync test endpoint."""
            return {"ok": True}
    else:
        @app.get("/test")
        @rate_limit(**kwargs)
        async def async_endpoint(_request: Request) -> dict[str, bool]:
            """Async test endpoint."""
            return {"ok": True}

    return TestClient(app)


class TestFastAPISync:
    """Rate limiting on synchronous FastAPI routes."""

    def test_allows_within_limit(self) -> None:
        """Requests up to the limit all return 200."""
        client = _client(3, sync=True)
        for _ in range(3):
            assert client.get("/test").status_code == 200

    def test_blocks_on_limit_exceeded(self) -> None:
        """The request after the limit returns 429."""
        client = _client(2, sync=True)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429

    def test_429_has_retry_after(self) -> None:
        """The 429 response body contains retry_after."""
        client = _client(1, sync=True)
        client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        assert resp.json()["retry_after"] >= 0

    def test_per_key_isolation(self) -> None:
        """Different header values have independent rate limit counters."""
        def extract_user(request: Request) -> str:
            """Extract user identifier from header."""
            return request.headers.get("X-User-Id", "anonymous")

        app = FastAPI()

        @app.get("/test")
        @rate_limit(requests=1, window=3600, key=extract_user, on_exceeded=_on_exceeded)
        def endpoint(request: Request) -> dict[str, bool]:  # pylint: disable=unused-argument
            """Header-keyed test endpoint."""
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/test", headers={"X-User-Id": "alice"}).status_code == 200
        assert client.get("/test", headers={"X-User-Id": "alice"}).status_code == 429
        assert client.get("/test", headers={"X-User-Id": "bob"}).status_code == 200


class TestFastAPIAsync:
    """Rate limiting on asynchronous FastAPI routes."""

    def test_allows_within_limit(self) -> None:
        """Requests up to the limit all return 200."""
        client = _client(3, sync=False)
        for _ in range(3):
            assert client.get("/test").status_code == 200

    def test_blocks_on_limit_exceeded(self) -> None:
        """The request after the limit returns 429."""
        client = _client(2, sync=False)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429

    def test_successful_response_body(self) -> None:
        """Successful response body matches the endpoint's return value."""
        client = _client(5, sync=False)
        assert client.get("/test").json() == {"ok": True}


class TestFastAPIRedis:
    """Redis backend tests for FastAPI routes."""

    def test_sync_blocks_with_redis(self, redis_client: Any) -> None:
        """Sync endpoint respects the limit using Redis backend."""
        client = _client(2, sync=True, redis_client=redis_client)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429

    def test_async_blocks_with_redis(self, redis_client: Any) -> None:
        """Async endpoint respects the limit using Redis backend."""
        client = _client(2, sync=False, redis_client=redis_client)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429

    def test_configure_redis_url(self, redis_url: str) -> None:
        """LimitraConfig(redis_url=...) is picked up by the decorator."""
        LimitraConfig(redis_url=redis_url, default_backend="redis")
        app = FastAPI()

        @app.get("/test")
        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded)
        async def endpoint(_request: Request) -> dict[str, bool]:
            """Endpoint using global Redis config."""
            return {"ok": True}

        c = TestClient(app)
        c.get("/test")
        c.get("/test")
        assert c.get("/test").status_code == 429
