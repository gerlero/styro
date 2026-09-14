from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Literal, overload

import aioshutil
from dulwich import porcelain
from dulwich.errors import NotGitRepository
from dulwich.objects import Blob
from dulwich.refs import HEADREF
from dulwich.repo import Repo

from styro._utils.subprocess import run


def _set_remote_url(repo: Repo, url: str) -> None:
    config = repo.get_config()
    config.set((b"remote", b"origin"), b"url", url.encode())
    config.write_to_path()


async def _fetch_existing(repo: Repo, url: str, *, system_git: bool = False) -> str:
    _set_remote_url(repo, url)
    if system_git:
        await run(["git", "fetch", "origin"], cwd=Path(repo.path))
        refs = repo.get_refs()
    with open(os.devnull, "wb") as devnull:  # noqa: ASYNC230
        refs = (
            await asyncio.to_thread(
                porcelain.fetch, repo, "origin", errstream=devnull, quiet=True
            )
        ).refs

    head = refs[HEADREF]
    assert head is not None
    return head.decode("ascii")


async def _fresh_clone(
    path: Path, url: str, revision: str | None = None, system_git: bool = False
) -> str:
    await aioshutil.rmtree(path, ignore_errors=True)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if system_git:
            await run(["git", "clone", url, str(path)], cwd=path.parent)
            repo = Repo(path)
        else:
            with open(os.devnull, "wb") as devnull:  # noqa: ASYNC230
                repo = await asyncio.to_thread(
                    porcelain.clone, url, path, errstream=devnull
                )

        if revision is None:
            return repo.head().decode("ascii")

        porcelain.reset(repo, "hard", revision)
        return revision
    except Exception:
        await aioshutil.rmtree(path, ignore_errors=True)
        raise


@overload
async def fetch(
    path: Path, url: str, *, missing_ok: Literal[True] = ..., system_git: bool = ...
) -> str | None: ...


@overload
async def fetch(
    path: Path, url: str, *, missing_ok: Literal[False] = ..., system_git: bool = ...
) -> str: ...


async def fetch(
    path: Path, url: str, *, missing_ok: bool = True, system_git: bool = False
) -> str | None:
    try:
        repo = Repo(path)
    except (FileNotFoundError, NotGitRepository):
        if missing_ok:
            return None
        return await _fresh_clone(path, url, system_git=system_git)

    return await _fetch_existing(repo, url, system_git=system_git)


async def clone(
    path: Path, url: str, revision: str | None, system_git: bool = False
) -> str:
    try:
        repo = Repo(path)
    except (FileNotFoundError, NotGitRepository):
        return await _fresh_clone(path, url, revision, system_git=system_git)

    if revision is None:
        revision = await _fetch_existing(repo, url, system_git=system_git)
    else:
        _set_remote_url(repo, url)

    porcelain.reset(repo, "hard", revision)
    return revision


def read_text(path: Path, subpath: str, *, revision: str | None = None) -> str | None:
    try:
        obj = porcelain.get_object_by_path(
            path,
            subpath,
            committish=revision,
        )
    except KeyError:
        return None

    if not isinstance(obj, Blob):
        return None

    return obj.data.decode()
