"""A community package manager for OpenFOAM."""

import asyncio
import sys
from typing import List

if sys.version_info >= (3, 9):
    from typing import Annotated
else:
    from typing_extensions import Annotated

import typer

from . import __version__, _Package
from ._self import check_for_new_version
from ._util import async_to_sync

app = typer.Typer(help=__doc__, add_completion=False)


@app.command()
@async_to_sync
async def install(packages: List[str], *, upgrade: bool = False) -> None:
    """Install OpenFOAM packages from the OpenFOAM Package Index."""
    with _Package.lock(write=True):
        pkgs = [_Package(pkg) for pkg in packages]

        if not upgrade or _Package("styro") not in pkgs:
            await check_for_new_version(verbose=True)

        await asyncio.gather(
            *(pkg.resolve() for pkg in pkgs if not pkg.is_installed() or upgrade),
        )

        await asyncio.gather(*(pkg.install() for pkg in pkgs))


@app.command()
@async_to_sync
async def uninstall(packages: List[str]) -> None:
    """Uninstall OpenFOAM packages."""
    with _Package.lock(write=True):
        for package in packages:
            _Package(package).uninstall()


@app.command()
def freeze() -> None:
    """List installed OpenFOAM packages."""
    with _Package.lock():
        for pkg in _Package.installed():
            typer.echo(pkg.name)


@async_to_sync
async def _version_callback(*, show: bool) -> None:
    if show:
        await check_for_new_version(verbose=True)
        typer.echo(f"styro {__version__}")
        raise typer.Exit


@app.callback()
def common(
    *,
    version: Annotated[
        bool,
        typer.Option(
            "--version", help="Show version and exit.", callback=_version_callback
        ),
    ] = False,
) -> None:
    pass


if __name__ == "__main__":
    app()
