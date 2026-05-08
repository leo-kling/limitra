# Flask

```bash
pip install limitra redis flask
```

Limitra has no Flask-specific code. Use `@rate_limit` directly on your routes — write a key extractor using Flask's request context and an `on_exceeded` handler returning a Flask response tuple.

## Basic example

```python
from flask import Flask, jsonify, request as flask_request
from limitra import LimitraConfig, rate_limit, RateLimitExceeded

app = Flask(__name__)
LimitraConfig(redis_url="redis://localhost:6379", project="flask-app")

def on_exceeded(exc: RateLimitExceeded):
    return jsonify({"error": "Too Many Requests", "retry_after": exc.retry_after}), 429

def from_ip() -> str:
    return flask_request.remote_addr or "unknown"

@app.route("/api/data")
@rate_limit(requests=100, window=60, key=from_ip, on_exceeded=on_exceeded)
def get_data():
    ...

@app.route("/api/login", methods=["POST"])
@rate_limit(requests=5, window=60, key=from_ip, on_exceeded=on_exceeded)
def login():
    ...
```

## Per-user limit via header

```python
def from_header() -> str:
    return flask_request.headers.get("X-User-Id", "anonymous")

@app.route("/api/data")
@rate_limit(requests=100, window=60, key=from_header, on_exceeded=on_exceeded)
def get_data():
    ...
```

!!! note
    Flask's request context is thread-local — the key callable takes no arguments and reads from `flask_request` directly, unlike FastAPI where the request is passed as a function parameter.

## Async routes

```python
@app.route("/api/data")
@rate_limit(requests=100, window=60, key=from_ip, on_exceeded=on_exceeded)
async def get_data():
    ...
```

Async routes (Flask 2.0+) work identically.
