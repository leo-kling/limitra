# Django

```bash
pip install limitra redis django
```

Limitra has no Django-specific code. Use `@rate_limit` directly on your views — write a key extractor that reads from `HttpRequest` and an `on_exceeded` handler returning a Django response.

## Basic example

```python
from django.http import HttpRequest, HttpResponse, JsonResponse
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

LimitraConfig(redis_url="redis://localhost:6379", project="django-app")

def on_exceeded(exc: RateLimitExceeded) -> JsonResponse:
    return JsonResponse(
        {"error": "Too Many Requests", "retry_after": exc.retry_after},
        status=429,
    )

def from_ip(request: HttpRequest) -> str:
    return str(request.META.get("REMOTE_ADDR", "unknown"))

@rate_limit(requests=100, window=60, key=from_ip, on_exceeded=on_exceeded)
def api_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")
```

## Per-user limit via header

```python
def from_header(request: HttpRequest) -> str:
    return request.META.get("HTTP_X_USER_ID", "anonymous")

@rate_limit(requests=100, window=60, key=from_header, on_exceeded=on_exceeded)
def api_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")
```

!!! note
    Django passes the `HttpRequest` as the first positional argument to views. The key callable receives it the same way — declare `request: HttpRequest` in its signature.

## Async views

```python
@rate_limit(requests=100, window=60, key=from_ip, on_exceeded=on_exceeded)
async def async_api_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")
```

Async views work identically (requires `asgiref`).
