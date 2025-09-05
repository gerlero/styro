import asyncio
import sys
import time
from io import TextIOBase
from types import TracebackType
from typing import ClassVar, List, Optional, TextIO, Type


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
    _statuses: ClassVar[List["Status"]] = []
    _printed_lines: ClassVar[int] = 0
    _dots: ClassVar[int] = 3
    _animation_task: ClassVar[Optional[asyncio.Task]] = None

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
            text = f"{status.title}{'.' * Status._dots}\n{status.msg}"
            _stdout.write(text)
            Status._printed_lines += text.count("\n")

    @staticmethod
    async def _animate() -> None:
        interval = 1
        last_time = time.perf_counter()

        while True:
            elapsed = time.perf_counter() - last_time

            if elapsed >= interval:
                frames_advanced = int(elapsed)
                Status._dots = (Status._dots + frames_advanced) % 6
                last_time += frames_advanced * interval
                Status.display()

            await asyncio.sleep(0.05)

    def __init__(self, title: str) -> None:
        self.title = title
        self.msg = ""

    def __call__(self, msg: str) -> None:
        self.msg = msg
        Status.display()

    def __enter__(self) -> "Status":
        Status._statuses.append(self)
        if len(Status._statuses) == 1:
            Status._animation_task = asyncio.create_task(Status._animate())
        Status.display()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        Status._statuses.remove(self)
        if not Status._statuses:
            task = Status._animation_task
            assert task is not None
            task.cancel()  # ty: ignore[possibly-unbound-attribute]
            Status._animation_task = None
        Status.display()
