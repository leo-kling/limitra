# Decorator

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

@rate_limit(
    requests=10,
    window=60,
    algorithm=None,
    key=None,
    scope="user",
    backend=None,
    on_exceeded=None,
    limits=None,
    block=True,
    exempt_when=None,
    fail_open=None,
)
def my_function():
    ...
```

## Parameter defaults

| Parameter | Default | Resolved value |
|---|---|---|
| `requests` | — | Required |
| `window` | — | Required |
| `algorithm` | `None` | Reads `default_algorithm` from the config store → always `"sliding_window"` unless changed via `LimitraConfig(default_algorithm=...)` |
| `key` | `None` | Global counter shared across all callers |
| `scope` | `"user"` | Used as-is |
| `backend` | `None` | `"memory"` if `LimitraConfig()` was never called — `"redis"` if `LimitraConfig(redis_url=...)` was called |
| `on_exceeded` | `None` | Raises `RateLimitExceeded` |
| `limits` | `None` | Uses `requests` / `window` instead |
| `block` | `True` | Blocks and raises (or calls `on_exceeded`) when limit is hit |
| `exempt_when` | `None` | No exemption — all callers are rate-limited |
| `fail_open` | `None` | `None` inherits from `LimitraConfig(fail_open=...)`. Pass `True` or `False` to override per-decorator |

!!! note
    `algorithm`, `backend`, and `fail_open` read from the config store when `None`. All other `None` defaults are resolved locally without consulting `LimitraConfig()`.

---

## `key` — who gets rate-limited

| Value | Behaviour |
|---|---|
| `None` | Single global counter for this function |
| `"arg_name"` | Use the value of that argument |
| `0`, `1`, … | Use the positional argument at that index |
| `callable` | Called as `key(*args, **kwargs)` → must return `str` |

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

# Global limit — all callers share one counter
@rate_limit(requests=1000, window=60)
def public_feed():
    return [...]

# Per-user limit — each user_id has its own counter
@rate_limit(requests=10, window=60, key="user_id")
def create_post(user_id: str, content: str):
    ...

# Custom extractor — use any logic to derive the key
@rate_limit(requests=50, window=60, key=lambda req, **_: req.client.host)
async def endpoint(req):
    ...
```

---

## `on_exceeded`

By default `RateLimitExceeded` is raised. Pass a callable to handle it differently — its return value becomes the return value of the decorated function.

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

## Dynamic rates

`requests` and `window` accept callables, evaluated on every call. This lets you apply different limits depending on the caller — for example, tiered plans.

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

def get_quota(user_id: str, **_) -> int:
    """Return the request quota based on the user's plan."""
    return 1000 if is_pro(user_id) else 100

@rate_limit(requests=get_quota, window=60, key="user_id")
def api_call(user_id: str):
    return {"data": "..."}
```

Both parameters can be dynamic at the same time:

```python
@rate_limit(
    requests=lambda user_id, **_: 1000 if is_pro(user_id) else 100,
    window=lambda user_id, **_: 3600 if is_pro(user_id) else 60,
    key="user_id",
)
def api_call(user_id: str):
    return {"data": "..."}
```

!!! note
    Dynamic rates are cached by `(requests_value, window_value)` — one limiter instance per unique pair. Using `limits=` disables dynamic evaluation.

---

## `limits` — multiple windows

Stack multiple rate limits on a single function. All must pass.

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

@rate_limit(limits=[
    (10, 1),      # max 10 per second
    (500, 3600),  # max 500 per hour
])
def api():
    return {"data": "..."}
```

---

## `block=False` — soft mode

The function always runs regardless of the limit. `on_exceeded` is called as a side effect only, without affecting the return value.

```python
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

def log_exceeded(exc: RateLimitExceeded):
    print(f"[WARN] Over limit: {exc.requests} req/{exc.window}s")

@rate_limit(requests=100, window=60, key="user_id", block=False, on_exceeded=log_exceeded)
def track_event(user_id: str, event: str):
    print(f"Tracking {event}")  # always executes

track_event("alice", "click")  # runs even when over limit
```

---

## `exempt_when`

Return `True` from the callable to skip all rate limiting for that call.

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

def is_internal(user_id: str, **_) -> bool:
    return user_id.startswith("svc-")

@rate_limit(requests=10, window=60, key="user_id", exempt_when=is_internal)
def api_call(user_id: str):
    return {"data": "..."}

api_call("svc-payments")  # bypasses rate limiting entirely
api_call("alice")         # rate-limited normally
```
