# FastAPI

```bash
pip install limitra redis fastapi
```

Limitra has no FastAPI-specific code. Use `@rate_limit` directly on your routes — write a key extractor and an `on_exceeded` handler using FastAPI's own types.

## Basic example

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

app = FastAPI()
LimitraConfig(redis_url="redis://localhost:6379", project="api")

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
    ...

@app.get("/items")
@rate_limit(requests=100, window=60, key=extract_ip, on_exceeded=on_exceeded)
async def list_items(request: Request):
    ...
```

## Per-user limit via header

```python
def extract_user(request: Request) -> str:
    return request.headers.get("X-User-Id", "anonymous")

@app.get("/items")
@rate_limit(requests=100, window=60, key=extract_user, on_exceeded=on_exceeded)
async def list_items(request: Request):
    ...
```

!!! note
    FastAPI injects route parameters by name. The `key` callable receives the same keyword arguments as the endpoint — declare `request: Request` in the endpoint signature so it is available to the key extractor.

## Sync routes

```python
@app.get("/items")
@rate_limit(requests=100, window=60, key=extract_ip, on_exceeded=on_exceeded)
def list_items(request: Request):
    ...
```

Both sync and async routes work identically.
