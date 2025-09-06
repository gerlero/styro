from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from ._subprocess import run

if TYPE_CHECKING:
    from pathlib import Path


async def _git(
    args: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        return await run(
            ["git", *args],
            cwd=cwd,
        )
    except FileNotFoundError:
        if shutil.which("git") is None:
            print(
                "🛑 Error: Git not found. styro needs Git to download packages.",
                file=sys.stderr,
            )
            sys.exit(1)
        raise


async def _get_default_branch(repo: Path) -> str:
    return (
        (
            await _git(
                ["rev-parse", "--abbrev-ref", "origin/HEAD"],
                cwd=repo,
            )
        )
        .stdout.strip()
        .split("/", maxsplit=1)[-1]
    )


async def _set_remote_url(repo: Path, url: str) -> None:
    await _git(
        ["remote", "set-url", "origin", url],
        cwd=repo,
    )


async def fetch(repo: Path, url: str, *, missing_ok: bool = True) -> str | None:
    try:
        await _set_remote_url(repo, url)
        branch = await _get_default_branch(repo)
        await _git(
            ["fetch", "origin"],
            cwd=repo,
        )
        return (
            await _git(
                ["rev-parse", f"origin/{branch}"],
                cwd=repo,
            )
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        shutil.rmtree(repo, ignore_errors=True)
        if missing_ok:
            return None
        return await clone(repo, url)


async def clone(repo: Path, url: str) -> str:
    try:
        branch = await _get_default_branch(repo)
        await _git(
            ["checkout", branch],
            cwd=repo,
        )
        await _git(
            ["reset", "--hard", f"origin/{branch}"],
            cwd=repo,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        shutil.rmtree(repo, ignore_errors=True)
        repo.mkdir(parents=True)
        await _git(
            ["clone", url, "."],
            cwd=repo,
        )
        branch = await _get_default_branch(repo)
    return (
        await _git(
            ["rev-parse", branch],
            cwd=repo,
        )
    ).stdout.strip()
