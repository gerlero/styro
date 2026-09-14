from __future__ import annotations

import asyncio
import io
import platform
import sys
import tarfile
from pathlib import Path

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


import aiohttp

from styro import __version__
from styro._packages._base import Package
from styro._utils.status import Status


def _is_managed_installation() -> bool:
    return not getattr(sys, "frozen", False)


class Styro(Package):
    def __init__(self, package, /) -> None:
        assert package.lower() == "styro"
        super().__init__("styro")

    @override
    def is_installed(self) -> bool:
        return True

    async def check_for_new_version(
        self, *, timeout: int | None = None, verbose: bool = False
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
                self.print_upgrade_instruction()
            return True

        return False

    def print_upgrade_instruction(self) -> None:
        if _is_managed_installation():
            print(
                "💡 Use your package manager (e.g. pip) to upgrade styro.",
                file=sys.stderr,
            )
        else:
            print(
                "💡 Run 'styro install --upgrade styro' to upgrade styro.",
                file=sys.stderr,
            )

    @override
    async def resolve(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _resolved: set[Package] | None = None,
    ) -> set[Package]:
        if not upgrade and not _force_reinstall:
            return set()

        self._upgrade_available = await self.check_for_new_version(verbose=False)

        if not _force_reinstall and not self._upgrade_available:
            return set()

        if _is_managed_installation():
            print(
                "🛑 Error: this is a managed installation of styro.",
                file=sys.stderr,
            )
            self.print_upgrade_instruction()
            sys.exit(1)

        return {self}

    @override
    async def install(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _deps: bool | dict[Package, asyncio.Event] = True,
    ) -> None:
        if not upgrade and not _force_reinstall:
            print(
                "✋ Package 'styro' is already installed.",
            )
            return

        if _is_managed_installation():
            print(
                "🛑 Error: this is a managed installation of styro.",
                file=sys.stderr,
            )
            self.print_upgrade_instruction()
            sys.exit(1)

        self._upgrade_available = await self.check_for_new_version(verbose=False)

        if not _force_reinstall and not self._upgrade_available:
            print(
                "✋ Package 'styro' is already up-to-date.",
            )
            return

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
            executable = Path(sys.executable)
            old_executable = executable.rename(executable.with_suffix(".old"))
            try:
                with tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz") as tar:
                    tar.extract("styro", path=executable.parent)
            except Exception as e:  # noqa: BLE001
                old_executable.rename(executable)
                print(f"🛑 Error: Failed to upgrade styro: {e}", file=sys.stderr)
                sys.exit(1)
            old_executable.unlink()

        print("✅ Package 'styro' upgraded successfully.")

    @override
    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        print(
            "🛑 Error: styro cannot be uninstalled this way.",
            file=sys.stderr,
        )
        if _is_managed_installation():
            print(
                "💡 Use your package manager (e.g. pip) to uninstall styro.",
                file=sys.stderr,
            )
        else:
            print(
                "💡 Delete the 'styro' binary in $FOAM_USER_APPBIN to uninstall.",
                file=sys.stderr,
            )
        sys.exit(1)
