import asyncio
import sys
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from types import TracebackType
from typing import Any, Generic, Optional, Set, Type, TypeVar, cast
from urllib.parse import unquote, urlparse

if sys.version_info >= (3, 9):
    from collections.abc import Callable, Coroutine, Generator
else:
    from typing import Callable, Coroutine, Generator

R = TypeVar("R")
S = TypeVar("S")


def async_to_sync(coro: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., R]:
    """
    Decorator to convert an asynchronous function to a synchronous one.
    """

    @wraps(coro)
    def wrapper(*args: Any, **kwargs: Any) -> R:  # noqa: ANN401
        return asyncio.run(coro(*args, **kwargs))

    return wrapper


class _ReentrantContextManager(Generic[R]):
    def __init__(self, func: Callable[[], Generator[R, None, None]]) -> None:
        self._func = func
        self._lock_depth = 0
        self._gen: Optional[Generator[R, None, None]] = None
        self._value: Optional[R] = None

    def __enter__(self) -> R:
        if self._lock_depth == 0:
            self._gen = self._func()
            self._value = next(self._gen)
        self._lock_depth += 1
        return cast("R", self._value)

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self._lock_depth -= 1
        if self._lock_depth == 0:
            assert self._gen is not None
            try:
                next(self._gen)
            except StopIteration:
                self._gen.close()
                self._gen = None
                self._value = None
            else:
                msg = "Generator did not terminate properly"
                raise RuntimeError(msg)

    def __call__(self, func: Callable[..., S]) -> Callable[..., S]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> S:  # noqa: ANN401
            with self:
                return func(*args, **kwargs)

        return wrapper


def reentrantcontextmanager(
    func: Callable[..., Generator[R, None, None]],
) -> Callable[..., _ReentrantContextManager[R]]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> _ReentrantContextManager:  # noqa: ANN401
        return _ReentrantContextManager(lambda: func(*args, **kwargs))

    return wrapper


def path_from_uri(uri: str) -> Path:
    assert uri.startswith("file://")
    if sys.version_info >= (3, 13):
        return Path.from_uri(uri)
    return Path(unquote(urlparse(uri).path))


@contextmanager
def get_changed_files(path: Path) -> Generator[Set[Path], None, None]:
    before = {file: file.stat().st_mtime for file in path.rglob("*") if file.is_file()}
    ret: Set[Path] = set()
    try:
        yield ret
    finally:
        for file in path.rglob("*"):
            if file.is_file() and file.stat().st_mtime != before.get(file):
                ret.add(file)
