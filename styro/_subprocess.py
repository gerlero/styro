import shlex
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

if sys.version_info >= (3, 9):
    pass
else:
    pass

import typer


def run(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    lines: int = 4,
) -> subprocess.CompletedProcess:
    with subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as proc:
        if sys.version_info >= (3, 8):
            display_cmd = shlex.join(cmd)
        else:
            display_cmd = " ".join(shlex.quote(arg) for arg in cmd)

        typer.echo(f"==> \033[1m{display_cmd[:64]}\033[0m")

        out: Deque[str] = deque(maxlen=lines)
        stdout = ""
        assert proc.stdout is not None
        for line in proc.stdout:
            stdout += line

            for _ in range(len(out)):
                typer.echo("\033[1A\x1b[2K", nl=False)

            out.append(line.rstrip())

            for ln in out:
                typer.echo(f"\033[90m{ln[:64]}\033[0m")

        for _ in range(len(out) + 1):
            typer.echo("\033[1A\x1b[2K", nl=False)

        assert proc.stderr is not None
        stderr = proc.stderr.read().strip()

        proc.wait()

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=proc.returncode, cmd=cmd, output=stdout, stderr=stderr
            )

        return subprocess.CompletedProcess(
            args=cmd, returncode=proc.returncode, stdout=stdout, stderr=stderr
        )
