from __future__ import annotations

import asyncio
import shlex
import subprocess
from collections import deque
from io import StringIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

if TYPE_CHECKING:
    from ._status import Status


async def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    status: Status | None = None,
) -> subprocess.CompletedProcess:
    proc = await asyncio.create_subprocess_exec(  # ty: ignore[missing-argument]
        *cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    if status is not None:
        cmdstr = f"==> \033[1m{shlex.join(cmd)}\033[0m\n"
        lines: deque[str] = deque(maxlen=4)

    output = StringIO()
    error = StringIO()

    async def process_stdout() -> None:
        assert proc.stdout is not None
        while line := (await proc.stdout.readline()).decode():
            output.write(line)
            if status is not None:
                lines.append(f"\033[90m{line.strip()[:64]}\033[0m")
                status(cmdstr + "\n".join(lines) + "\n")

    async def process_stderr() -> None:
        assert proc.stderr is not None
        while line := (await proc.stderr.readline()).decode():
            error.write(line)
            if status is not None:
                lines.append(f"\033[33m{line.strip()[:64]}\033[0m")
                status(cmdstr + "\n".join(lines) + "\n")

    await asyncio.gather(
        process_stdout(),
        process_stderr(),
    )

    await proc.wait()
    assert proc.returncode is not None

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
