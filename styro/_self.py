import asyncio
import io
import platform
import sys
import tarfile
from pathlib import Path
from typing import Dict, Optional, Set, Union

import aiohttp
import typer

from . import Package, __version__
from ._status import Status


def is_managed_installation() -> bool:
    return not getattr(sys, "frozen", False)


def print_upgrade_instruction() -> None:
    if is_managed_installation():
        typer.echo(
            "💡 Use your package manager (e.g. pip) to upgrade styro.",
            err=True,
        )
    else:
        typer.echo(
            "💡 Run 'styro install --upgrade styro' to upgrade styro.",
            err=True,
        )


async def check_for_new_version(*, verbose: bool = True) -> bool:
    try:
        with Status("🔁 Checking for new version"):
            async with aiohttp.ClientSession(
                raise_for_status=True
            ) as session, session.get(
                "https://api.github.com/repos/gerlero/styro/releases/latest",
            ) as response:
                contents = await response.json()
                latest_version = contents["tag_name"]
    except Exception:  # noqa: BLE001
        return False

    if latest_version.startswith("v"):
        latest_version = latest_version[1:]

    if latest_version != __version__:
        if verbose:
            typer.echo(
                f"⚠️ Warning: you are using styro {__version__}, but version {latest_version} is available.",
                err=True,
            )
            print_upgrade_instruction()
        return True

    return False


class Styro(Package):
    def is_installed(self) -> bool:
        return True

    async def resolve(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _resolved: Optional[Set["Package"]] = None,
    ) -> Set["Package"]:
        if not upgrade and not _force_reinstall:
            typer.echo(
                "✋ Package 'styro' is already installed.",
            )
            return set()

        typer.echo("🔍 Resolving styro..")

        if self._metadata is not None:
            self._metadata = {}

        if not _force_reinstall and not await check_for_new_version(verbose=False):
            typer.echo(
                "✋ Package 'styro' is already up-to-date.",
            )
            return set()

        if is_managed_installation():
            typer.echo(
                "🛑 Error: This is a managed installation of styro.",
                err=True,
            )
            print_upgrade_instruction()
            raise typer.Exit(code=1)

        return {self}

    async def install(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _deps: Union[bool, Dict[Package, asyncio.Event]] = True,
    ) -> None:
        if not upgrade and not _force_reinstall:
            typer.echo(
                "✋ Package 'styro' is already installed.",
            )
            return

        if is_managed_installation():
            typer.echo(
                "🛑 Error: This is a managed installation of styro.",
                err=True,
            )
            print_upgrade_instruction()
            raise typer.Exit(code=1)

        if not _force_reinstall and not await check_for_new_version(verbose=False):
            typer.echo(
                "✋ Package 'styro' is already up-to-date.",
            )
            return

        with Status("⏬ Downloading styro"):
            try:
                async with aiohttp.ClientSession(
                    raise_for_status=True
                ) as session, session.get(
                    f"https://github.com/gerlero/styro/releases/latest/download/styro-{platform.system()}-{platform.machine()}.tar.gz"
                ) as response:
                    contents = await response.read()
            except Exception as e:
                typer.echo(f"🛑 Error: Failed to download styro: {e}", err=True)
                raise typer.Exit(code=1) from e
        with Status("⏳ Upgrading styro"):
            try:
                with tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz") as tar:
                    tar.extract("styro", path=Path(sys.executable).parent)
            except Exception as e:
                typer.echo(f"🛑 Error: Failed to upgrade styro: {e}", err=True)
                raise typer.Exit(code=1) from e
        typer.echo("✅ Package 'styro' upgraded successfully.")

    def dependencies(self) -> Set[Package]:
        return set()

    def installed_dependents(self) -> Set[Package]:
        return {self}

    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        typer.echo(
            "🛑 Error: styro cannot be uninstalled this way.",
            err=True,
        )
        if is_managed_installation():
            typer.echo(
                "💡 Use your package manager (e.g. pip) to uninstall styro.",
                err=True,
            )
        else:
            typer.echo(
                "💡 Delete the 'styro' binary in $FOAM_USER_APPBIN to uninstall.",
                err=True,
            )
        raise typer.Exit(code=1)
