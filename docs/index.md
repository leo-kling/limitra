# Limitra

Simple, framework-agnostic rate limiting for Python.

Works with any function — plain Python, FastAPI, Flask, Django, or anything else.

---

## Install

```bash
pip install limitra
```

Zero dependencies. For the Redis backend, add `redis` to your own project dependencies — Limitra detects it automatically.

## Quick start

```python
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

# 1. Once at startup — connects to Redis and sets global defaults
LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

# 2. Decorate any function — 10 requests per 60s per user_id
@rate_limit(requests=10, window=60, key="user_id")
def create_post(user_id: str, content: str):
    ...

# RateLimitExceeded is raised when the limit is hit
try:
    create_post("alice", "hello")
except RateLimitExceeded as e:
    print(f"Slow down, retry in {e.retry_after:.1f}s")
```

No Redis? Use the in-memory backend — no `LimitraConfig()` needed:

```python
from limitra import rate_limit

@rate_limit(requests=10, window=60, key="user_id", backend="memory")
def create_post(user_id: str, content: str):
    ...
```

---

## Features

- **4 algorithms** — sliding window, fixed window, token bucket, leaky bucket
- **2 backends** — in-memory or Redis (distributed, atomic Lua scripts)
- **Framework-agnostic** — works with FastAPI, Flask, Django, or plain Python — no integration code needed
- **Multi-rate limits** — stack multiple windows on one function
- **Soft mode** — run the function anyway, trigger a callback as a side effect
- **Fail open** — allow requests when Redis is unreachable
- **Exempt** — skip limiting for certain callers via a callable
