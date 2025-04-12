"""A community package manager for OpenFOAM."""

import sys
from typing import List

if sys.version_info >= (3, 9):
    from typing import Annotated
else:
    from typing_extensions import Annotated

import typer

from . import __version__
from ._packages import Package
from ._self import check_for_new_version
from ._util import async_to_sync

app = typer.Typer(help=__doc__, add_completion=False)


@app.command()
@async_to_sync
async def install(packages: List[str], *, upgrade: bool = False) -> None:
    """Install OpenFOAM packages from the OpenFOAM Package Index."""
    pkgs = {Package(pkg) for pkg in packages}

    if not upgrade or Package("styro") not in pkgs:
        await check_for_new_version(verbose=True)

    await Package.install_all(pkgs, upgrade=upgrade)


@app.command()
@async_to_sync
async def uninstall(packages: List[str]) -> None:
    """Uninstall OpenFOAM packages."""
    pkgs = {Package(pkg) for pkg in packages}

    await Package.uninstall_all(pkgs)


@app.command()
@async_to_sync
async def freeze() -> None:
    """List installed OpenFOAM packages."""
    for pkg in Package.all_installed():
        typer.echo(pkg)


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
