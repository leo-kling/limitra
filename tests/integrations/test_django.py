"""Confirm that @rate_limit works on Django sync and async views."""

import importlib
import json
from typing import Any

import pytest

try:
    import django as _django_mod
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={},
            INSTALLED_APPS=[],
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        )
        _django_mod.setup()

    from django.http import HttpRequest, HttpResponse, JsonResponse
    from django.test import RequestFactory

    from limitra import LimitraConfig, rate_limit, RateLimitExceeded
except ImportError as _exc:
    pytest.skip(f"django not installed — {_exc}", allow_module_level=True)

_factory = RequestFactory()
_has_asgiref = importlib.util.find_spec("asgiref") is not None
skip_no_async = pytest.mark.skipif(not _has_asgiref, reason="Django async views require asgiref")


def _request(ip: str = "127.0.0.1") -> "HttpRequest":
    """Return a GET request with the given remote address."""
    req = _factory.get("/")
    req.META["REMOTE_ADDR"] = ip
    return req


def _on_exceeded(exc: "RateLimitExceeded") -> "JsonResponse":
    """Return a 429 JSON response."""
    return JsonResponse({"error": "Too Many Requests", "retry_after": exc.retry_after}, status=429)


class TestDjangoSync:
    """Rate limiting on synchronous Django views."""

    def test_allows_within_limit(self) -> None:
        """Requests up to the limit all return 200."""
        @rate_limit(requests=3, window=3600, on_exceeded=_on_exceeded)
        def view(_request: "HttpRequest") -> "HttpResponse":
            """Sync test view."""
            return HttpResponse("ok")

        for _ in range(3):
            assert view(_request()).status_code == 200

    def test_blocks_on_limit_exceeded(self) -> None:
        """The request after the limit returns 429."""
        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded)
        def view(_request: "HttpRequest") -> "HttpResponse":
            """Sync test view."""
            return HttpResponse("ok")

        view(_request())
        view(_request())
        assert view(_request()).status_code == 429

    def test_429_body(self) -> None:
        """The 429 response body contains error and retry_after."""
        @rate_limit(requests=1, window=3600, on_exceeded=_on_exceeded)
        def view(_request: "HttpRequest") -> "HttpResponse":
            """Sync test view."""
            return HttpResponse("ok")

        view(_request())
        resp = view(_request())
        assert resp.status_code == 429
        assert json.loads(resp.content)["error"] == "Too Many Requests"

    def test_per_key_isolation(self) -> None:
        """Different IPs have independent rate limit counters."""
        def extract_ip(request: "HttpRequest") -> str:
            """Extract client IP from request."""
            return str(request.META.get("REMOTE_ADDR", "unknown"))

        @rate_limit(requests=1, window=3600, key=extract_ip, on_exceeded=_on_exceeded)
        def view(_request: "HttpRequest") -> "HttpResponse":
            """IP-keyed test view."""
            return HttpResponse("ok")

        assert view(_request("10.0.0.1")).status_code == 200
        assert view(_request("10.0.0.1")).status_code == 429
        assert view(_request("10.0.0.2")).status_code == 200


@skip_no_async
class TestDjangoAsync:
    """Rate limiting on asynchronous Django views."""

    async def test_allows_within_limit(self) -> None:
        """Requests up to the limit all return 200."""
        @rate_limit(requests=3, window=3600, on_exceeded=_on_exceeded)
        async def view(_request: "HttpRequest") -> "HttpResponse":
            """Async test view."""
            return HttpResponse("ok")

        for _ in range(3):
            assert (await view(_request())).status_code == 200

    async def test_blocks_on_limit_exceeded(self) -> None:
        """The request after the limit returns 429."""
        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded)
        async def view(_request: "HttpRequest") -> "HttpResponse":
            """Async test view."""
            return HttpResponse("ok")

        await view(_request())
        await view(_request())
        assert (await view(_request())).status_code == 429

    async def test_per_key_isolation(self) -> None:
        """Different IPs have independent counters in async views."""
        def extract_ip(request: "HttpRequest") -> str:
            """Extract client IP from request."""
            return str(request.META.get("REMOTE_ADDR", "unknown"))

        @rate_limit(requests=1, window=3600, key=extract_ip, on_exceeded=_on_exceeded)
        async def view(_request: "HttpRequest") -> "HttpResponse":
            """Async IP-keyed test view."""
            return HttpResponse("ok")

        assert (await view(_request("10.0.0.1"))).status_code == 200
        assert (await view(_request("10.0.0.1"))).status_code == 429
        assert (await view(_request("10.0.0.2"))).status_code == 200


class TestDjangoRedis:
    """Redis backend tests for Django views."""

    def test_sync_blocks_with_redis(self, redis_client: Any) -> None:
        """Sync view respects the limit using Redis backend."""
        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded, backend="redis", redis_client=redis_client)
        def view(_request: "HttpRequest") -> "HttpResponse":
            """Redis-backed sync test view."""
            return HttpResponse("ok")

        view(_request())
        view(_request())
        assert view(_request()).status_code == 429

    def test_configure_redis_url(self, redis_url: str) -> None:
        """LimitraConfig(redis_url=...) is picked up by the decorator."""
        LimitraConfig(redis_url=redis_url, default_backend="redis")

        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded)
        def view(_request: "HttpRequest") -> "HttpResponse":
            """View using global Redis config."""
            return HttpResponse("ok")

        view(_request())
        view(_request())
        assert view(_request()).status_code == 429

    async def test_async_blocks_with_redis(self, redis_client: Any) -> None:
        """Async view respects the limit using Redis backend."""
        @rate_limit(requests=2, window=3600, on_exceeded=_on_exceeded, backend="redis", redis_client=redis_client)
        async def view(_request: "HttpRequest") -> "HttpResponse":
            """Redis-backed async test view."""
            return HttpResponse("ok")

        await view(_request())
        await view(_request())
        assert (await view(_request())).status_code == 429
