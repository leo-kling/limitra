# Backends & Keys

---

## Memory

Default backend. State is stored in-process with thread-safe locking. No setup required.

```python
from limitra import rate_limit

@rate_limit(requests=10, window=60, key="user_id", backend="memory")
def create_post(user_id: str, content: str):
    ...

create_post("alice", "hello")  # counter lives in memory, local to this process
```

!!! warning
    Not shared between processes or restarts. Use Redis for distributed deployments.

---

## Redis

All four algorithms use Lua scripts for atomic execution — safe under concurrent multi-process access.

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-svc")

@rate_limit(requests=100, window=60, key="user_id")  # backend="redis" by default after LimitraConfig()
def api(user_id: str):
    return {"data": "..."}

api("alice")  # counter stored in Redis, shared across all processes
```

---

## Key format

Redis keys follow this pattern:

```
[prefix:][ project:]scope[:identifier][:suffix]
```

| `LimitraConfig()` | `@rate_limit()` | identifier | Resulting key |
|---|---|---|---|
| `project="svc"` | `key="user_id"` | `"alice"` | `svc:user:alice` |
| `prefix="rl", project="svc"` | `key="user_id"` | `"alice"` | `rl:svc:user:alice` |
| `prefix="rl"` | `suffix="v2"` | `"alice"` | `rl:user:alice:v2` |
| — | `key=None` | — | `global` |

### Multi-service isolation

When multiple services share the same Redis instance, use `project` to keep their keys separate:

```python
# user-service/main.py
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://shared:6379", project="user-svc")

@rate_limit(requests=100, window=60, key="user_id")
def get_user(user_id: str):
    ...

# product-service/main.py
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://shared:6379", project="product-svc")

@rate_limit(requests=100, window=60, key="user_id")
def get_product(user_id: str):
    ...

# get_user("alice")    → key: user-svc:user:alice
# get_product("alice") → key: product-svc:user:alice  (no collision)
```
