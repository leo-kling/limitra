<p align="center">
  <img src="https://limitra.pages.dev/logo.png" alt="Limitra" width="120" />
</p>

<h1 align="center">Limitra</h1>

<p align="center">
  <img src="https://github.com/leo-kling/limitra/actions/workflows/ci.yml/badge.svg" alt="CI" />
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13%20|%203.14-blue" alt="Python versions" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT license" />
</p>

<p align="center">Simple, framework-agnostic rate limiting for Python.</p>

---

## Install

```bash
pip install limitra
```

## Quick start

```python
from limitra import LimitraConfig, rate_limit

LimitraConfig(redis_url="redis://localhost:6379", project="my-service")

@rate_limit(requests=10, window=60, key="user_id")
def create_post(user_id: str, content: str):
    ...
```

→ Full documentation: **[limitra.leok.dev](https://limitra.leok.dev)**
