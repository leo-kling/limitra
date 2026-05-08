"""Confirm that @rate_limit works on Flask sync and async routes."""

import importlib
from typing import Any

import pytest

try:
    from flask import Flask, jsonify
    from flask import request as flask_request
    from flask.testing import FlaskClient

    from limitra import LimitraConfig, rate_limit, RateLimitExceeded
except ImportError as _exc:
    pytest.skip(f"flask not installed — {_exc}", allow_module_level=True)

_has_asgiref = importlib.util.find_spec("asgiref") is not None
skip_no_async = pytest.mark.skipif(not _has_asgiref, reason="Flask async requires asgiref")


def _on_exceeded(exc: RateLimitExceeded) -> Any:
    """Return a 429 JSON response."""
    return jsonify({"error": "Too Many Requests", "retry_after": exc.retry_after}), 429


def _sync_client(
    requests: int, key: Any = None, redis_client: Any = None
) -> FlaskClient:
    """Return a Flask test client with a rate-limited sync route."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    kwargs: dict[str, Any] = {"requests": requests, "window": 3600, "on_exceeded": _on_exceeded}
    if key is not None:
        kwargs["key"] = key
    if redis_client is not None:
        kwargs["backend"] = "redis"
        kwargs["redis_client"] = redis_client

    @app.route("/test")
    @rate_limit(**kwargs)
    def view() -> Any:
        """Sync test route."""
        return "ok", 200

    return app.test_client()


def _async_client(requests: int) -> FlaskClient:
    """Return a Flask test client with a rate-limited async route."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/test")
    @rate_limit(requests=requests, window=3600, on_exceeded=_on_exceeded)
    async def view() -> Any:
        """Async test route."""
        return "ok", 200

    return app.test_client()


class TestFlaskSync:
    """Rate limiting on synchronous Flask routes."""

    def test_allows_within_limit(self) -> None:
        """Requests up to the limit all return 200."""
        client = _sync_client(3)
        for _ in range(3):
            assert client.get("/test").status_code == 200

    def test_blocks_on_limit_exceeded(self) -> None:
        """The request after the limit returns 429."""
        client = _sync_client(2)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429

    def test_429_body(self) -> None:
        """The 429 response body contains error and retry_after."""
        client = _sync_client(1)
        client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        assert resp.get_json()["error"] == "Too Many Requests"

    def test_per_key_isolation(self) -> None:
        """Different header values have independent rate limit counters."""
        def extract_user() -> str:
            """Extract user identifier from header."""
            return flask_request.headers.get("X-User-Id", "anonymous")

        client = _sync_client(1, key=extract_user)
        assert client.get("/test", headers={"X-User-Id": "alice"}).status_code == 200
        assert client.get("/test", headers={"X-User-Id": "alice"}).status_code == 429
        assert client.get("/test", headers={"X-User-Id": "bob"}).status_code == 200


@skip_no_async
class TestFlaskAsync:
    """Rate limiting on asynchronous Flask routes."""

    def test_allows_within_limit(self) -> None:
        """Requests up to the limit all return 200."""
        client = _async_client(3)
        for _ in range(3):
            assert client.get("/test").status_code == 200

    def test_blocks_on_limit_exceeded(self) -> None:
        """The request after the limit returns 429."""
        client = _async_client(2)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429


class TestFlaskRedis:
    """Redis backend tests for Flask routes."""

    def test_sync_blocks_with_redis(self, redis_client: Any) -> None:
        """Sync route respects the limit using Redis backend."""
        client = _sync_client(2, redis_client=redis_client)
        client.get("/test")
        client.get("/test")
        assert client.get("/test").status_code == 429

    def test_configure_redis_url(self, redis_url: str) -> None:
        """LimitraConfig(redis_url=...) is picked up by the decorator."""
        LimitraConfig(redis_url=redis_url, default_backend="redis")
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/test")
        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded)
        def view() -> Any:
            """Route using global Redis config."""
            return "ok"

        c = app.test_client()
        c.get("/test")
        c.get("/test")
        assert c.get("/test").status_code == 429
