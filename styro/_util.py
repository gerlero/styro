from __future__ import annotations

import sys
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import TracebackType

R = TypeVar("R")
S = TypeVar("S")


class _ReentrantContextManager(Generic[R]):
    def __init__(self, func: Callable[[], Generator[R, None, None]]) -> None:
        self._func = func
        self._lock_depth = 0
        self._gen: Generator[R, None, None] | None = None
        self._value: R | None = None

    def __enter__(self) -> R:
        if self._lock_depth == 0:
            self._gen = self._func()
            self._value = next(self._gen)
        self._lock_depth += 1
        return cast("R", self._value)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
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


def path_from_uri(uri: str, /) -> Path:
    assert uri.startswith("file://")
    if sys.version_info >= (3, 13):
        return Path.from_uri(uri)
    return Path(unquote(urlparse(uri).path))


@contextmanager
def get_changed_files(path: Path, /) -> Generator[set[Path], None, None]:
    before = {file: file.stat().st_mtime for file in path.rglob("*") if file.is_file()}
    ret: set[Path] = set()
    try:
        yield ret
    finally:
        after_files = {file for file in path.rglob("*") if file.is_file()}
        before_files = set(before.keys())

        # Add newly created files (files that exist now but didn't before)
        new_files = after_files - before_files
        ret.update(new_files)

        # Add modified files (files that existed before but have different timestamps)
        for file in after_files & before_files:
            if file.stat().st_mtime != before[file]:
                ret.add(file)
