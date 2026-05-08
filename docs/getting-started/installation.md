# Installation

**Python 3.10+** is required.

```bash
pip install limitra
```

Limitra has zero runtime dependencies. The memory backend works out of the box.

## Redis backend

Limitra does not ship `redis` as a dependency — if you're using Redis for rate limiting, you're most likely already using it elsewhere in your project.

Add it to your project's own dependencies:

```bash
pip install redis        # or: poetry add redis, uv add redis, etc.
```

Limitra detects it automatically. Any `redis>=4.0` version works.

!!! note
    If `redis` is not installed and you configure a Redis backend, Limitra raises `ImportError` with a clear message at startup.

## Local Redis for development

```bash
docker run -p 6379:6379 redis:alpine
```
