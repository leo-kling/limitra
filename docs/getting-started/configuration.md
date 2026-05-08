# Configuration

## How it works

Limitra uses two levels of configuration:

| | `LimitraConfig()` | `@rate_limit()` |
|---|---|---|
| **When** | Once at app startup | On each function to protect |
| **What** | Redis connection, namespace, defaults | The rule: how many requests, which window |
| **Scope** | Global — applies to all limiters | Local — this function only |

In practice: `LimitraConfig()` connects Limitra to Redis and sets global defaults. `@rate_limit()` defines the rule on a specific function and inherits everything set by `LimitraConfig()`.

---

## Full example

```python
# main.py (or app.py, startup.py...)
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

# 1. Global setup — call once at startup
LimitraConfig(
    redis_url="redis://localhost:6379",
    project="my-service",   # isolates Redis keys for this service
)

# 2. Decorate each function to protect
@rate_limit(requests=10, window=60, key="user_id")
def create_post(user_id: str, content: str):
    ...

@rate_limit(requests=1000, window=60)
def public_feed():
    ...
```

---

## Without Redis — memory backend

If you don't need Redis (local development, single-process app), `LimitraConfig()` is not required. The memory backend is used by default:

```python
from limitra import rate_limit

@rate_limit(requests=10, window=60, key="user_id", backend="memory")
def create_post(user_id: str, content: str):
    ...
```

!!! warning
    The memory backend is not shared between processes or restarts. For production apps with multiple workers, use Redis.

---

## `LimitraConfig()` parameters

### Redis connection

```python
# Option A — URL
LimitraConfig(redis_url="redis://localhost:6379")
LimitraConfig(redis_url="rediss://user:pass@host:6380/0")  # TLS

# Option B — pre-built client (useful with connection pooling)
import redis
client = redis.Redis(host="localhost", port=6379, db=0)
LimitraConfig(redis_client=client)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `redis_url` | `str` | `None` | Connection URL passed to `redis.from_url()` |
| `redis_client` | `Redis` | `None` | Pre-built Redis client |
| `redis_db` | `int` | `0` | Redis database index (only used with `redis_url`) |

### Key namespace

```python
LimitraConfig(
    redis_url="redis://shared:6379",
    project="user-svc",   # → keys: user-svc:user:alice
    prefix="rl",          # → keys: rl:user-svc:user:alice
    suffix="v2",          # → keys: rl:user-svc:user:alice:v2
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project` | `str` | `None` | Namespace prefix — recommended to isolate microservices sharing the same Redis |
| `prefix` | `str` | `None` | Key prefix added before `project` |
| `suffix` | `str` | `None` | Key suffix added after the identifier |

### Defaults

These values are used by `@rate_limit()` when the corresponding parameters are not specified.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `default_algorithm` | `str` | `"sliding_window"` | Default algorithm |
| `default_backend` | `str` | `"redis"` | Default backend after `LimitraConfig()` is called |
| `fail_open` | `bool` | `False` | When `True`, allow requests if Redis is unreachable instead of raising an error |

---

## Overriding `LimitraConfig()` per function

Any `@rate_limit()` parameter overrides the global setting for that function only:

```python
LimitraConfig(redis_url="redis://localhost:6379", project="my-svc")

# Uses all globals — project "my-svc", redis backend
@rate_limit(requests=100, window=60)
def normal_endpoint():
    ...

# Overrides the backend for this function only
@rate_limit(requests=100, window=60, backend="memory")
def local_only_endpoint():
    ...

# Overrides the project for this function only
@rate_limit(requests=5, window=60, project="billing")
def billing_endpoint():
    ...
```
