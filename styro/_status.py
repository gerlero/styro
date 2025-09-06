from __future__ import annotations

import asyncio
import sys
import time
from io import TextIOBase
from typing import TYPE_CHECKING, ClassVar, TextIO

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

if TYPE_CHECKING:
    from types import TracebackType


class _StreamWrapper(TextIOBase):
    def __init__(self, stream: TextIO, /) -> None:
        self._wrapped = stream

    def write(self, data: str, /) -> int:
        Status.clear()
        ret = self._wrapped.write(data)
        self._wrapped.flush()
        Status.display()
        return ret

    def flush(self) -> None:
        self._wrapped.flush()


_stdout = sys.stdout
sys.stdout = _StreamWrapper(sys.stdout)
sys.stderr = _StreamWrapper(sys.stderr)


class Status:
    _statuses: ClassVar[list[Status]] = []
    _printed_lines: ClassVar[int] = 0
    _animation_task: ClassVar[asyncio.Task | None] = None

    @staticmethod
    def clear() -> None:
        if Status._printed_lines > 0:
            _stdout.write(f"\033[{Status._printed_lines}A\033[J")
            _stdout.flush()
        Status._printed_lines = 0

    @staticmethod
    def display() -> None:
        Status.clear()
        for status in Status._statuses:
            # Use Rich's spinner-style animation instead of simple dots
            spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            spinner_idx = int(time.time() * 8) % len(spinner_chars)
            spinner = spinner_chars[spinner_idx]
            
            if status.msg:
                text = f"{spinner} {status.title}\n{status.msg}"
            else:
                text = f"{spinner} {status.title}"
            
            _stdout.write(text + "\n")
            Status._printed_lines += text.count("\n") + 1

    @staticmethod
    async def _animate() -> None:
        interval = 0.125  # 8 FPS to match spinner speed
        last_time = time.perf_counter()

        while True:
            elapsed = time.perf_counter() - last_time

            if elapsed >= interval:
                last_time = time.perf_counter()
                Status.display()

            await asyncio.sleep(0.05)

    def __init__(self, title: str) -> None:
        self.title = title
        self.msg = ""

    def __call__(self, msg: str) -> None:
        self.msg = msg
        Status.display()

    def __enter__(self) -> Self:
        Status._statuses.append(self)
        if len(Status._statuses) == 1:
            # Only start animation if we're in an async context
            try:
                Status._animation_task = asyncio.create_task(Status._animate())
            except RuntimeError:
                # No event loop running, skip animation
                Status._animation_task = None
        Status.display()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        Status._statuses.remove(self)
        if not Status._statuses:
            task = Status._animation_task
            if task is not None:
                task.cancel()  # ty: ignore[possibly-unbound-attribute]
            Status._animation_task = None
        Status.display()
