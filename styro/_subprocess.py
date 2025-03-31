import asyncio
import shlex
import subprocess
import sys
from collections import deque
from io import StringIO
from pathlib import Path
from typing import Deque, Dict, List, Optional, TextIO, Tuple

_cmds: Dict[int, Tuple[str, Deque[str]]] = {}
_displayed_lines = 0


class _Stream:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, data: str) -> None:
        _clear_status()
        self._stream.write(data)
        _display_status()

    def flush(self) -> None:
        self._stream.flush()


_stdout = sys.stdout
sys.stdout = _Stream(sys.stdout)
sys.stderr = _Stream(sys.stderr)


def _cmd_join(cmd: List[str]) -> str:
    if sys.version_info < (3, 8):
        return " ".join(shlex.quote(arg) for arg in cmd)
    return shlex.join(cmd)


def _clear_status() -> None:
    global _displayed_lines  # noqa: PLW0603

    if _displayed_lines:
        _stdout.write(f"\033[{_displayed_lines}A\033[J")

    _displayed_lines = 0


def _display_status() -> None:
    global _displayed_lines  # noqa: PLW0603

    _clear_status()

    for cmd, lines in _cmds.values():
        _stdout.write(f"==> \033[1m{cmd}\033[0m\n")
        _displayed_lines += 1

        for line in lines:
            _stdout.write(f"\033[90m{line[:64]}\033[0m\n")
            _displayed_lines += 1


async def run(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    lines: Deque[str] = deque(maxlen=4)
    _cmds[id(lines)] = (
        f"({cwd.name}) {_cmd_join(cmd)}" if cwd else _cmd_join(cmd),
        lines,
    )
    _display_status()

    output = StringIO()
    error = StringIO()

    async def process_stdout() -> None:
        while True:
            assert proc.stdout is not None
            line = (await proc.stdout.readline()).decode()
            if not line:
                break
            output.write(line)
            lines.append(line.strip())
            _display_status()

    async def process_stderr() -> None:
        while True:
            assert proc.stderr is not None
            line = (await proc.stderr.readline()).decode()
            if not line:
                break
            error.write(line)
            lines.append(line.strip())
            _display_status()

    await asyncio.gather(
        process_stdout(),
        process_stderr(),
    )

    await proc.wait()
    assert proc.returncode is not None

    del _cmds[id(lines)]
    _display_status()

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=proc.returncode,
            cmd=cmd,
            output=output.getvalue(),
            stderr=error.getvalue(),
        )

    return subprocess.CompletedProcess(
        cmd,
        returncode=proc.returncode,
        stdout=output.getvalue(),
        stderr=error.getvalue(),
    )
