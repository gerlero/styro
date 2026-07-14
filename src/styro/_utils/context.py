from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

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


class _ReentrantContextManager(AbstractContextManager[R]):
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

    def __call__(self, func: Callable[P, S]) -> Callable[P, S]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> S:
            with self:
                return func(*args, **kwargs)

        return wrapper


def reentrantcontextmanager(
    func: Callable[P, Generator[R, None, None]],
    /,
) -> Callable[P, _ReentrantContextManager[R]]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> _ReentrantContextManager[R]:
        return _ReentrantContextManager(lambda: func(*args, **kwargs))

    return wrapper
