from __future__ import annotations

import asyncio
import os
import shutil
from typing import TYPE_CHECKING

from dulwich import porcelain
from dulwich.errors import NotGitRepository
from dulwich.objects import Blob
from dulwich.refs import HEADREF
from dulwich.repo import Repo

if TYPE_CHECKING:
    from pathlib import Path


def _set_remote_url(repo: Repo, url: str) -> None:
    config = repo.get_config()
    config.set((b"remote", b"origin"), b"url", url.encode())
    config.write_to_path()


def _fetch_existing(repo: Repo, url: str) -> str:
    _set_remote_url(repo, url)
    with open(os.devnull, "wb") as devnull:
        result = porcelain.fetch(repo, "origin", errstream=devnull, quiet=True)

    head = result.refs[HEADREF]
    assert head is not None
    return head.decode("ascii")


def _fresh_clone(path: Path, url: str, revision: str | None = None) -> str:
    shutil.rmtree(path, ignore_errors=True)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(os.devnull, "wb") as devnull:
            repo = porcelain.clone(url, path, errstream=devnull)

        if revision is None:
            return repo.head().decode("ascii")

        porcelain.reset(repo, "hard", revision)
        return revision
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise


def _fetch(path: Path, url: str, *, missing_ok: bool = True) -> str | None:
    try:
        repo = Repo(path)
    except (FileNotFoundError, NotGitRepository):
        if missing_ok:
            return None
        return _fresh_clone(path, url)

    return _fetch_existing(repo, url)


def _clone(path: Path, url: str, revision: str | None) -> str:
    try:
        repo = Repo(path)
    except (FileNotFoundError, NotGitRepository):
        return _fresh_clone(path, url, revision)

    if revision is None:
        revision = _fetch_existing(repo, url)
    else:
        _set_remote_url(repo, url)

    porcelain.reset(repo, "hard", revision)
    return revision


async def fetch(path: Path, url: str, *, missing_ok: bool = True) -> str | None:
    return await asyncio.to_thread(
        _fetch,
        path,
        url,
        missing_ok=missing_ok,
    )


async def clone(path: Path, url: str, *, revision: str | None = None) -> str:
    return await asyncio.to_thread(_clone, path, url, revision)


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
