from __future__ import annotations

import sys
from contextlib import AbstractContextManager, ContextDecorator
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar, cast

if sys.version_info < (3, 15):
    import inspect

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import TracebackType

P = ParamSpec("P")
R = TypeVar("R")
S = TypeVar("S")


class _ContextDecorator(ContextDecorator):
    """Backport of https://github.com/python/cpython/issues/125862."""

    if sys.version_info < (3, 15):

        def __call__(self, func: Callable[P, S]) -> Callable[P, S]:
            if inspect.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                    with cast("AbstractContextManager[Any]", self._recreate_cm()):
                        return await func(*args, **kwargs)

                return cast("Callable[P, S]", async_wrapper)

            return super().__call__(func)


class _ReentrantContextManager(AbstractContextManager[R], _ContextDecorator):
    def __init__(self, func: Callable[[], Generator[R, None, None]], /) -> None:
        self._func = func
        self._lock_depth = 0
        self._gen: Generator[R, None, None] | None = None
        self._value: R

    @override
    def __enter__(self) -> R:
        if self._lock_depth == 0:
            self._gen = self._func()
            self._value = next(self._gen)
        self._lock_depth += 1
        return self._value

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._lock_depth -= 1
        if self._lock_depth == 0:
            assert self._gen is not None
            try:
                next(self._gen)
            except StopIteration:
                self._gen.close()
                self._gen = None
                del self._value
            else:
                msg = "Generator did not terminate properly"
                raise RuntimeError(msg)


def reentrantcontextmanager(
    func: Callable[P, Generator[R, None, None]],
    /,
) -> Callable[P, _ReentrantContextManager[R]]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> _ReentrantContextManager[R]:
        return _ReentrantContextManager(lambda: func(*args, **kwargs))

    return wrapper
