import asyncio
import sys
from functools import wraps
from typing import Any, TypeVar

if sys.version_info >= (3, 9):
    from collections.abc import Callable, Coroutine
else:
    from typing import Callable, Coroutine

R = TypeVar("R")


def async_to_sync(coro: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., R]:
    """
    Decorator to convert an asynchronous function to a synchronous one.
    """

    @wraps(coro)
    def wrapper(*args: Any, **kwargs: Any) -> R:  # noqa: ANN401
        return asyncio.run(coro(*args, **kwargs))

    return wrapper
