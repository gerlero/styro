import asyncio
import sys
import time
from types import TracebackType
from typing import ClassVar, List, Optional, TextIO, Type


class _Stream:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, data: str) -> None:
        Status.clear()
        self._stream.write(data)
        Status.display()

    def flush(self) -> None:
        self._stream.flush()


class _StderrMonitor:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, data: str) -> None:
        # Mark that stderr has been written to, disabling Status clearing
        Status._stderr_written = True
        self._stream.write(data)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


_stdout = sys.stdout
_stderr = sys.stderr
sys.stdout = _Stream(sys.stdout)
sys.stderr = _StderrMonitor(sys.stderr)


class Status:
    _statuses: ClassVar[List["Status"]] = []
    _printed_lines: ClassVar[int] = 0
    _dots: ClassVar[int] = 3
    _animation_task: ClassVar[Optional[asyncio.Task]] = None
    _stderr_written: ClassVar[bool] = False

    @staticmethod
    def clear() -> None:
        sys.stdout.flush()
        # Don't clear if stderr has been written to, as it would clear stderr content
        if Status._printed_lines > 0 and not Status._stderr_written:
            _stdout.write(f"\033[{Status._printed_lines}A\033[J")
        Status._printed_lines = 0

    @staticmethod
    def display() -> None:
        Status.clear()
        for status in Status._statuses:
            text = str(status)
            # If stderr has been written to, ensure we start on a new line
            if Status._stderr_written and Status._printed_lines == 0:
                _stdout.write("\n")
                Status._printed_lines += 1
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

    def __str__(self) -> str:
        return f"{self.title}{'.' * Status._dots}\n{self.msg}"
