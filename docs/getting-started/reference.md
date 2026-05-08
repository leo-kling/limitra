# Reference

Complete parameter reference for all public APIs.

---

## `LimitraConfig()`

Call once at startup to set global defaults.

```python
from limitra import LimitraConfig

LimitraConfig(
    redis_url=None,
    redis_client=None,
    redis_db=0,
    project=None,
    prefix=None,
    suffix=None,
    default_algorithm="sliding_window",
    default_backend="redis",
    fail_open=False,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `redis_url` | `str` | `None` | Connection URL passed to `redis.from_url()` — e.g. `"redis://localhost:6379"`, `"rediss://..."` for TLS |
| `redis_client` | `Redis` | `None` | Pre-built Redis client. Alternative to `redis_url` |
| `redis_db` | `int` | `0` | Redis database index. Only used with `redis_url` |
| `project` | `str` | `None` | Namespace prefix for all keys. Use to isolate services sharing the same Redis |
| `prefix` | `str` | `None` | Key prefix added before `project` |
| `suffix` | `str` | `None` | Key suffix added after the identifier |
| `default_algorithm` | `str` | `"sliding_window"` | Algorithm used when `@rate_limit` omits `algorithm=` |
| `default_backend` | `str` | `"redis"` | Backend used when `@rate_limit` omits `backend=` |
| `fail_open` | `bool` | `False` | When `True`, allow requests if Redis raises an error instead of propagating it |

---

## `@rate_limit()`

```python
from limitra import rate_limit

@rate_limit(
    requests=0,
    window=0,
    algorithm=None,
    key=None,
    scope="user",
    backend=None,
    redis_client=None,
    project=None,
    prefix=None,
    suffix=None,
    on_exceeded=None,
    limits=None,
    block=True,
    exempt_when=None,
    fail_open=None,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `requests` | `int` | — | Maximum calls allowed within the window |
| `window` | `float` | — | Time window in seconds |
| `algorithm` | `str` | `None` | Algorithm to use. `None` reads `default_algorithm` from the config store — always `"sliding_window"` unless changed via `LimitraConfig(default_algorithm=...)` |
| `key` | `str \| int \| callable` | `None` | How to identify the caller — see [key values](#key-values) below |
| `scope` | `str` | `"user"` | Label stored in the key (e.g. `"ip"`, `"team"`) |
| `backend` | `str` | `None` | `"redis"` or `"memory"`. `None` resolves to `"memory"` if `LimitraConfig()` was never called, or `"redis"` if `LimitraConfig(redis_url=...)` was called (since `LimitraConfig()`'s own default for this parameter is `"redis"`) |
| `redis_client` | `Redis` | `None` | Override the global Redis client for this limiter only |
| `project` | `str` | `None` | Override the global project namespace for this limiter only |
| `prefix` | `str` | `None` | Override the global key prefix for this limiter only |
| `suffix` | `str` | `None` | Override the global key suffix for this limiter only |
| `on_exceeded` | `callable` | `None` | Called as `on_exceeded(exc)` instead of raising. Its return value is returned from the decorated function |
| `limits` | `list[(int, float)]` | `None` | List of `(requests, window)` tuples. All must pass. Takes precedence over `requests`/`window` |
| `block` | `bool` | `True` | When `False`, the function always runs. `on_exceeded` is called as a side effect only |
| `exempt_when` | `callable` | `None` | Called with the same args as the decorated function. When it returns `True`, rate limiting is skipped entirely |
| `fail_open` | `bool \| None` | `None` | Allow requests on backend errors. `None` inherits from `LimitraConfig(fail_open=...)`. Pass `True` or `False` to override per-decorator |

### Key values

| Value | Behaviour |
|---|---|
| `None` | Single global counter for this function |
| `"arg_name"` | Value of the named argument |
| `0`, `1`, … | Value of the positional argument at that index |
| `callable` | Called as `key(*args, **kwargs)` — must return a `str` |

---

## Limiter classes

All four classes share the same constructor signature.

```python
from limitra import (
    SlidingWindowRateLimiter,
    FixedWindowRateLimiter,
    TokenBucketLimiter,
    LeakyBucketLimiter,
)

limiter = SlidingWindowRateLimiter(
    capacity=100,
    fill_rate=1/60,
    scope="user",
    backend="redis",
    redis_client=None,
    project=None,
    prefix=None,
    suffix=None,
    fail_open=False,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `capacity` | `int` | — | Maximum number of requests allowed per window |
| `fill_rate` | `float` | — | For sliding/fixed window: `1 / window`. For token/leaky bucket: `requests / window` |
| `scope` | `str` | `"user"` | Label used in the storage key |
| `backend` | `str` | `"memory"` | `"redis"` or `"memory"` |
| `redis_client` | `Redis` | `None` | Required when `backend="redis"` |
| `project` | `str` | `None` | Namespace prefix for the key |
| `prefix` | `str` | `None` | Key prefix |
| `suffix` | `str` | `None` | Key suffix |
| `fail_open` | `bool` | `False` | Allow requests on Redis errors |

### Methods

| Method | Returns | Description |
|---|---|---|
| `allow_request(identifier)` | `bool` | `True` if the request is allowed and counted, `False` if the limit is exceeded |
| `get_status(identifier)` | `dict` | Algorithm-specific status — counts, capacity, available slots |
| `get_usage(identifier)` | `dict` | Normalised usage: `count`, `limit`, `remaining`, `limited` |
| `get_wait_time(identifier)` | `float` | Seconds until the next request would be allowed (token/leaky bucket only) |
| `reset(identifier)` | `None` | Clear counters for the given identifier |
| `get_key(identifier)` | `str` | Return the full storage key without reading any data |

---

## `RateLimitExceeded`

```python
from limitra import RateLimitExceeded
```

| Attribute | Type | Description |
|---|---|---|
| `requests` | `int` | The limit that was exceeded |
| `window` | `float` | The time window in seconds |
| `retry_after` | `float` | Seconds to wait before retrying (may be `0.0`) |
| `remaining` | `int` | Remaining requests — always `0` when the exception is raised |
