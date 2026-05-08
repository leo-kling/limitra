# Error Handling

By default, `RateLimitExceeded` is raised when a limit is hit. Limitra gives you several ways to handle or suppress that error.

---

## `RateLimitExceeded`

| Attribute | Type | Description |
|---|---|---|
| `requests` | `int` | The limit that was exceeded |
| `window` | `float` | The time window in seconds |
| `retry_after` | `float` | Seconds to wait before retrying (may be `0.0`) |
| `remaining` | `int` | Remaining requests — always `0` when the exception is raised |

```python
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

@rate_limit(requests=5, window=60, key="user_id")
def create_post(user_id: str, content: str):
    ...

try:
    create_post("alice", "hello")
except RateLimitExceeded as e:
    print(f"Limit: {e.requests} requests per {e.window}s")
    print(f"Retry after: {e.retry_after:.2f}s")
```

---

## `on_exceeded` — custom handler

Pass a callable to `on_exceeded` to intercept the exception instead of raising it. Its return value becomes the return value of the decorated function.

```python
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

def my_handler(exc: RateLimitExceeded) -> dict:
    return {"error": "rate limited", "retry_after": exc.retry_after}

@rate_limit(requests=5, window=60, on_exceeded=my_handler)
def api_call():
    return {"data": "..."}

result = api_call()  # returns {"error": "rate limited", ...} instead of raising
```

---

## Framework integration examples

Limitra is framework-agnostic — write your own `on_exceeded` handler using your framework's response types.

=== "FastAPI"

    ```python
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from limitra import LimitraConfig, rate_limit, RateLimitExceeded

    app = FastAPI()
    LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

    def on_exceeded(exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            {"error": "Too Many Requests", "retry_after": exc.retry_after},
            status_code=429,
        )

    def extract_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @app.post("/login")
    @rate_limit(requests=5, window=60, key=extract_ip, on_exceeded=on_exceeded)
    async def login(request: Request):
        return {"status": "ok"}
    ```

=== "Flask"

    ```python
    from flask import Flask, jsonify, request as flask_request
    from limitra import LimitraConfig, rate_limit, RateLimitExceeded

    app = Flask(__name__)
    LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

    def on_exceeded(exc: RateLimitExceeded):
        return jsonify({"error": "Too Many Requests", "retry_after": exc.retry_after}), 429

    def from_ip() -> str:
        return flask_request.remote_addr or "unknown"

    @app.route("/api/login", methods=["POST"])
    @rate_limit(requests=5, window=60, key=from_ip, on_exceeded=on_exceeded)
    def login():
        return {"status": "ok"}
    ```

=== "Django"

    ```python
    from django.http import HttpRequest, HttpResponse, JsonResponse
    from limitra import LimitraConfig, rate_limit, RateLimitExceeded

    LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

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

---

## `block=False` — soft mode

When `block=False`, the decorated function **always runs**. `on_exceeded` is called as a side effect when the limit would have been exceeded, but does not affect the function's return value.

Useful for logging, metrics, or gradual rollouts where you want to observe without enforcing.

```python
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

def log_exceeded(exc: RateLimitExceeded):
    print(f"[WARN] Rate limit would have been exceeded: {exc.requests} req/{exc.window}s")

@rate_limit(requests=100, window=60, key="user_id", block=False, on_exceeded=log_exceeded)
def track_event(user_id: str, event: str):
    print(f"Tracking {event} for {user_id}")  # always executes

track_event("alice", "page_view")  # runs even when over limit, logs a warning
```

---

## `fail_open` — Redis errors

By default, if Redis raises an error (connection refused, timeout...), the exception propagates. Set `fail_open=True` to allow requests through instead:

```python
from limitra import LimitraConfig, rate_limit

# Option A — globally for all limiters
LimitraConfig(redis_url="redis://localhost:6379", project="my-service", fail_open=True)

@rate_limit(requests=100, window=60)
def my_endpoint():
    return {"data": "..."}

# Option B — per decorator only
LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

@rate_limit(requests=100, window=60, fail_open=True)
def my_other_endpoint():
    return {"data": "..."}
```

!!! tip
    Use `fail_open=True` in production when Redis availability should not block your API. The rate limiter silently becomes a no-op during Redis outages.
