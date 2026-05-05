from __future__ import annotations
import asyncio
import functools
import logging
from typing import Callable, Type

logger = logging.getLogger(__name__)


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Async exponential-backoff retry decorator."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "%s attempt %d/%d failed (%s), retrying in %.1fs",
                        fn.__name__, attempt, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
