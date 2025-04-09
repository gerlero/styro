import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ._subprocess import run


async def _get_default_branch(repo: Path) -> str:
    return (
        (
            await run(
                ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
                cwd=repo,
            )
        )
        .stdout.strip()
        .split("/", maxsplit=1)[-1]
    )


async def _set_remote_url(repo: Path, url: str) -> None:
    await run(
        ["git", "remote", "set-url", "origin", url],
        cwd=repo,
    )


async def fetch(repo: Path, url: str, *, missing_ok: bool = True) -> Optional[str]:
    try:
        await _set_remote_url(repo, url)
        branch = await _get_default_branch(repo)
        await run(
            ["git", "fetch", "origin"],
            cwd=repo,
        )
        return (
            await run(
                ["git", "rev-parse", f"origin/{branch}"],
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
        await run(
            ["git", "checkout", branch],
            cwd=repo,
        )
        await run(
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=repo,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        shutil.rmtree(repo, ignore_errors=True)
        repo.mkdir(parents=True)
        await run(
            ["git", "clone", url, "."],
            cwd=repo,
        )
        branch = await _get_default_branch(repo)
    return (
        await run(
            ["git", "rev-parse", branch],
            cwd=repo,
        )
    ).stdout.strip()
