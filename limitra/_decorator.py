"""The @rate_limit decorator — works with any sync or async Python function."""

import functools
from inspect import iscoroutinefunction, signature
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union, cast


from ._config import get_config
from .algorithms import LIMITERS
from .base import BaseRateLimiter
from .exceptions import RateLimitExceeded

# Window-based algorithms derive fill_rate as 1/window; others use requests/window.
_WINDOW_BASED = {"sliding_window", "fixed_window"}

F = TypeVar("F", bound=Callable[..., Any])


def _build_limiter(
    requests: int,
    window: float,
    algorithm: Optional[str],
    scope: str,
    backend: Optional[str],
    redis_client: Optional[Any],
    project: Optional[str],
    prefix: Optional[str],
    suffix: Optional[str],
    fail_open: Optional[bool] = None,
) -> BaseRateLimiter:
    """Instantiate the appropriate limiter class with resolved configuration."""
    config = get_config()
    algorithm = algorithm or config.default_algorithm
    backend = backend or config.default_backend
    redis_client = redis_client if redis_client is not None else config.redis_client
    project = project if project is not None else config.project
    prefix = prefix if prefix is not None else config.prefix
    suffix = suffix if suffix is not None else config.suffix
    resolved_fail_open: bool = config.fail_open if fail_open is None else fail_open

    if backend == "redis" and redis_client is None:
        raise ValueError(
            "Redis backend requires a client. "
            "Call limitra.LimitraConfig(redis_url='redis://...') first."
        )

    limiter_cls = LIMITERS.get(algorithm)
    if limiter_cls is None:
        raise ValueError(f"Unknown algorithm '{algorithm}'. Options: {list(LIMITERS)}")

    fill_rate = (1 / window) if algorithm in _WINDOW_BASED else (requests / window)

    kwargs: Dict[str, Any] = {
        "capacity": requests,
        "fill_rate": fill_rate,
        "scope": scope,
        "backend": backend,
        "project": project,
        "prefix": prefix,
        "suffix": suffix,
        "fail_open": resolved_fail_open,
    }
    if backend == "redis":
        kwargs["redis_client"] = redis_client

    return limiter_cls(**kwargs)  # type: ignore[no-any-return]


def _extract_identifier(
    key: Union[str, int, Callable[..., str], None],
    func: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Optional[str]:
    """Extract the rate-limit identifier from the decorated function's arguments."""
    if key is None:
        return None
    if callable(key):
        return str(key(*args, **kwargs))
    if isinstance(key, int):
        return str(args[key])
    if isinstance(key, str):
        if key in kwargs:
            return str(kwargs[key])
        params = list(signature(func).parameters.keys())
        if key in params:
            idx = params.index(key)
            if idx < len(args):
                return str(args[idx])
        raise ValueError(f"rate_limit key='{key}' not found in function arguments")
    raise TypeError(f"rate_limit key must be str, int, or callable — got {type(key)}")


def rate_limit(
    requests: Union[int, Callable[..., int]] = 0,
    window: Union[float, Callable[..., float]] = 0,
    algorithm: Optional[str] = None,
    key: Union[str, int, Callable[..., str], None] = None,
    scope: str = "user",
    backend: Optional[str] = None,
    redis_client: Optional[Any] = None,
    project: Optional[str] = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    on_exceeded: Optional[Callable[..., Any]] = None,
    limits: Optional[List[Tuple[int, float]]] = None,
    block: bool = True,
    exempt_when: Optional[Callable[..., bool]] = None,
    fail_open: Optional[bool] = None,
) -> Callable[[F], F]:
    """Decorator that rate-limits any Python function (sync or async).

    Args:
        requests: Maximum calls allowed within the window. Accepts a callable
                  evaluated per-request as ``requests(*args, **kwargs) → int``
                  for dynamic per-caller limits (e.g. tiered plans).
        window:   Time window in seconds. Accepts a callable evaluated
                  per-request as ``window(*args, **kwargs) → float``.
        algorithm: One of "sliding_window" (default), "token_bucket",
                   "leaky_bucket", "fixed_window".
        key:      How to extract the per-caller identifier from the function args:
                    - None        → single global counter for this function
                    - "arg_name"  → use the named argument's value
                    - 0, 1, ...   → use positional argument by index
                    - callable    → called as key(*args, **kwargs), return a str
        scope:    Label stored in the Redis key (e.g. "user", "ip", "team").
        backend:  "redis" or "memory". Falls back to LimitraConfig() default.
        redis_client: Override the global Redis client for this limiter only.
        project:  Override the global project namespace for this limiter only.
        prefix:   Override the global key prefix for this limiter only.
        suffix:   Override the global key suffix for this limiter only.
        on_exceeded: Optional callable(exc: RateLimitExceeded) — called instead of
                     raising when the limit is hit.
        limits:   List of (requests, window) tuples. When given, ALL limits must
                  pass. Takes precedence over requests/window.
        block:    When False, the decorated function always runs. If over limit,
                  on_exceeded is called as a side effect only.
        exempt_when: Optional callable(*args, **kwargs) → bool. When it returns
                     True, the request bypasses rate limiting entirely.
        fail_open: When True, allow requests on backend errors instead of
                   falling back to memory.

    Raises:
        RateLimitExceeded: When the limit is hit and on_exceeded is not set.
    """
    actual_scope = "global" if key is None else scope
    _is_dynamic = (callable(requests) or callable(window)) and limits is None

    def decorator(func: F) -> F:
        """Wrap func with rate-limiting logic."""
        _static_limiters: Optional[List[BaseRateLimiter]] = None
        _dynamic_cache: Dict[Tuple[int, float], BaseRateLimiter] = {}

        def _build_static() -> List[BaseRateLimiter]:
            nonlocal _static_limiters
            if _static_limiters is not None:
                return _static_limiters
            result: List[BaseRateLimiter] = []
            if limits is not None:
                use_suffix = len(limits) > 1
                for req, win in limits:
                    lim_scope = (
                        f"{actual_scope}_{int(win)}" if use_suffix else actual_scope
                    )
                    result.append(
                        _build_limiter(
                            requests=req,
                            window=win,
                            algorithm=algorithm,
                            scope=lim_scope,
                            backend=backend,
                            redis_client=redis_client,
                            project=project,
                            prefix=prefix,
                            suffix=suffix,
                            fail_open=fail_open,
                        )
                    )
            else:
                result = [
                    _build_limiter(
                        requests=int(requests),  # type: ignore[arg-type]
                        window=float(window),  # type: ignore[arg-type]
                        algorithm=algorithm,
                        scope=actual_scope,
                        backend=backend,
                        redis_client=redis_client,
                        project=project,
                        prefix=prefix,
                        suffix=suffix,
                        fail_open=fail_open,
                    )
                ]
            _static_limiters = result
            return result

        def _get_dynamic(req: int, win: float) -> BaseRateLimiter:
            cache_key = (req, win)
            if cache_key not in _dynamic_cache:
                _dynamic_cache[cache_key] = _build_limiter(
                    requests=req,
                    window=win,
                    algorithm=algorithm,
                    scope=actual_scope,
                    backend=backend,
                    redis_client=redis_client,
                    project=project,
                    prefix=prefix,
                    suffix=suffix,
                    fail_open=fail_open,
                )
            return _dynamic_cache[cache_key]

        def _check(
            identifier: Optional[str],
            args: Tuple[Any, ...],
            kwargs_inner: Dict[str, Any],
        ) -> Optional[Any]:
            if exempt_when is not None and exempt_when(*args, **kwargs_inner):
                return None

            lims: List[BaseRateLimiter]
            pairs: List[Tuple[int, float]]

            if _is_dynamic:
                actual_req = (
                    int(requests(*args, **kwargs_inner))
                    if callable(requests)
                    else requests
                )
                actual_win = (
                    float(window(*args, **kwargs_inner)) if callable(window) else window
                )
                lims = [_get_dynamic(actual_req, actual_win)]
                pairs = [(actual_req, actual_win)]
            else:
                lims = _build_static()
                pairs = (
                    list(limits)
                    if limits is not None
                    else [(int(requests), float(window))]  # type: ignore[arg-type]
                )

            for i, limiter in enumerate(lims):
                if not limiter.allow_request(identifier):
                    req, win = pairs[i]
                    wait = limiter.get_wait_time(identifier)
                    exc = RateLimitExceeded(requests=req, window=win, retry_after=wait)
                    if not block:
                        if on_exceeded is not None:
                            on_exceeded(exc)
                        return None
                    if on_exceeded is not None:
                        return on_exceeded(exc)
                    raise exc
            return None

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Async rate-limited wrapper."""
            identifier = _extract_identifier(key, func, args, kwargs)
            result = _check(identifier, args, kwargs)
            if result is not None:
                return result
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Sync rate-limited wrapper."""
            identifier = _extract_identifier(key, func, args, kwargs)
            result = _check(identifier, args, kwargs)
            if result is not None:
                return result
            return func(*args, **kwargs)

        wrapper = async_wrapper if iscoroutinefunction(func) else sync_wrapper
        return cast(F, wrapper)

    return decorator
