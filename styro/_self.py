from __future__ import annotations

import io
import platform
import sys
import tarfile
from pathlib import Path

import aiohttp

from . import __version__
from ._status import Status


def is_managed_installation() -> bool:
    return not getattr(sys, "frozen", False)


def print_upgrade_instruction() -> None:
    if is_managed_installation():
        print(
            "💡 Use your package manager (e.g. pip) to upgrade styro.",
            file=sys.stderr,
        )
    else:
        print(
            "💡 Run 'styro install --upgrade styro' to upgrade styro.",
            file=sys.stderr,
        )


async def check_for_new_version(
    *, timeout: int | None = None, verbose: bool = False
) -> bool:
    try:
        with Status("🔁 Checking for new version"):
            async with (
                aiohttp.ClientSession(
                    raise_for_status=True, timeout=timeout
                ) as session,
                session.get(
                    "https://api.github.com/repos/gerlero/styro/releases/latest",
                ) as response,
            ):
                contents = await response.json()
                latest_version = contents["tag_name"]
    except Exception:  # noqa: BLE001
        return False

    if (latest_version := latest_version.removeprefix("v")) != __version__:
        if verbose:
            print(
                f"⚠️ Warning: you are using styro {__version__}, but version {latest_version} is available.",
                file=sys.stderr,
            )
            print_upgrade_instruction()
        return True

    return False


async def selfupgrade() -> None:
    with Status("⏬ Downloading styro"):
        try:
            async with (
                aiohttp.ClientSession(raise_for_status=True) as session,
                session.get(
                    f"https://github.com/gerlero/styro/releases/latest/download/styro-{platform.system()}-{platform.machine()}.tar.gz"
                ) as response,
            ):
                contents = await response.read()
        except Exception as e:  # noqa: BLE001
            print(f"🛑 Error: Failed to download styro: {e}", file=sys.stderr)
            sys.exit(1)

    with Status("⏳ Upgrading styro"):
        try:
            with tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz") as tar:
                tar.extract("styro", path=Path(sys.executable).parent)
        except Exception as e:  # noqa: BLE001
            print(f"🛑 Error: Failed to upgrade styro: {e}", file=sys.stderr)
            sys.exit(1)
