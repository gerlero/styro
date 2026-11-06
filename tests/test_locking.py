from __future__ import annotations

import asyncio
import fcntl
import importlib
import json
import multiprocessing
import os
import sys
from collections.abc import Generator
from contextlib import ContextDecorator
from pathlib import Path
from typing import Any

from styro._utils.context import _ContextDecorator, reentrantcontextmanager


def _set_openfoam_environment(platform: Path) -> None:
    os.environ["FOAM_USER_APPBIN"] = str(platform / "bin")
    os.environ["FOAM_USER_LIBBIN"] = str(platform / "lib")


def _hold_empty_registry(platform: Path, ready: Any, release: Any) -> None:
    _set_openfoam_environment(platform)
    lock_module = importlib.import_module("styro._packages._lock")

    with lock_module.lock:
        ready.set()
        if not release.wait(timeout=10):
            raise TimeoutError


def _add_registry_entry(platform: Path, name: str, opened: Any | None = None) -> None:
    _set_openfoam_environment(platform)
    lock_module = importlib.import_module("styro._packages._lock")

    if opened is not None:
        flock = lock_module.fcntl.flock
        signaled = False

        def signaling_flock(file: Any, operation: int) -> None:
            nonlocal signaled
            if operation & fcntl.LOCK_EX and not signaled:
                signaled = True
                opened.set()
            flock(file, operation)

        fcntl_module: Any = lock_module.fcntl
        fcntl_module.flock = signaling_flock

    with lock_module.lock as installed:
        if not installed:
            installed.update({"version": 1, "packages": {}})
        installed["packages"][name] = {}


def test_async_decorator_holds_context_until_coroutine_finishes() -> None:
    active = False

    @reentrantcontextmanager
    def make_guard() -> Generator[None, None, None]:
        nonlocal active
        active = True
        try:
            yield
        finally:
            active = False

    guard = make_guard()

    @guard
    async def operation() -> None:
        assert active
        await asyncio.sleep(0)
        assert active

    asyncio.run(operation())
    assert not active


def test_context_decorator_backport_is_only_used_before_python_315() -> None:
    if sys.version_info >= (3, 15):
        assert _ContextDecorator.__call__ is ContextDecorator.__call__
    else:
        assert _ContextDecorator.__call__ is not ContextDecorator.__call__


def test_registry_lock_keeps_one_inode_across_empty_state(tmp_path: Path) -> None:
    platform = tmp_path / "platform"
    (platform / "bin").mkdir(parents=True)
    (platform / "lib").mkdir()

    context = multiprocessing.get_context("spawn")
    holder_ready = context.Event()
    release_holder = context.Event()
    waiter_opened = context.Event()

    holder = context.Process(
        target=_hold_empty_registry,
        args=(platform, holder_ready, release_holder),
    )
    holder.start()
    assert holder_ready.wait(timeout=10)

    waiter = context.Process(
        target=_add_registry_entry,
        args=(platform, "waiter", waiter_opened),
    )
    waiter.start()
    assert waiter_opened.wait(timeout=10)

    release_holder.set()
    holder.join(timeout=10)
    assert holder.exitcode == 0

    follower = context.Process(
        target=_add_registry_entry,
        args=(platform, "follower"),
    )
    follower.start()

    waiter.join(timeout=10)
    follower.join(timeout=10)
    assert waiter.exitcode == 0
    assert follower.exitcode == 0

    installed_path = platform / "styro" / "installed.json"
    installed = json.loads(installed_path.read_text())
    assert set(installed["packages"]) == {"waiter", "follower"}
