from __future__ import annotations

import sys
from io import TextIOBase
from typing import TYPE_CHECKING, ClassVar, TextIO

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

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
        Status.interrupt()
        ret = self._wrapped.write(data)
        self._wrapped.flush()
        Status.resume()
        return ret

    def flush(self) -> None:
        self._wrapped.flush()


_stdout = sys.stdout
sys.stdout = _StreamWrapper(sys.stdout)
sys.stderr = _StreamWrapper(sys.stderr)


class Status:
    _statuses: ClassVar[list[Status]] = []
    _live: ClassVar[Live | None] = None
    _console: ClassVar[Console] = Console(file=_stdout)

    @staticmethod
    def interrupt() -> None:
        """Temporarily interrupt the live display for stream output."""
        if Status._live and Status._live.is_started:
            Status._live.stop()

    @staticmethod
    def resume() -> None:
        """Resume the live display after stream output."""
        if Status._live and not Status._live.is_started and Status._statuses:
            Status._live.start()

    @staticmethod
    def _get_current_display_text() -> str:
        """Generate the text to display based on current statuses."""
        if not Status._statuses:
            return ""
        
        lines = []
        for status in Status._statuses:
            if status.msg:
                lines.append(f"{status.title}\n{status.msg}")
            else:
                lines.append(status.title)
        
        return "\n".join(lines)

    def __init__(self, title: str) -> None:
        self.title = title
        self.msg = ""

    def __call__(self, msg: str) -> None:
        self.msg = msg
        if Status._live:
            Status._live.update(
                Spinner("dots", text=Status._get_current_display_text())
            )

    def __enter__(self) -> Self:
        Status._statuses.append(self)
        if len(Status._statuses) == 1:
            # Create and start the live display with a spinner
            Status._live = Live(
                Spinner("dots", text=Status._get_current_display_text()),
                console=Status._console,
                refresh_per_second=8,
                transient=True
            )
            try:
                Status._live.start()
            except Exception:
                # If we can't start live display, continue without it
                Status._live = None
        elif Status._live:
            Status._live.update(
                Spinner("dots", text=Status._get_current_display_text())
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        Status._statuses.remove(self)
        if not Status._statuses:
            if Status._live:
                Status._live.stop()
                Status._live = None
        elif Status._live:
            Status._live.update(
                Spinner("dots", text=Status._get_current_display_text())
            )