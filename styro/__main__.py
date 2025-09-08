"""Package manager for OpenFOAM."""

from __future__ import annotations

import cyclopts

from . import __version__
from ._packages import Package
from ._self import check_for_new_version


async def _version_callback() -> str:
    await check_for_new_version(verbose=True)
    return f"styro {__version__}"


app = cyclopts.App(help=__doc__, version=_version_callback)  # ty: ignore[unknown-argument]


@app.command
async def install(packages: list[str], /, *, upgrade: bool = False) -> None:
    """Install OpenFOAM packages."""
    pkgs = {Package(pkg) for pkg in packages}

    if not upgrade or Package("styro") not in pkgs:
        await check_for_new_version(verbose=True)

    await Package.install_all(pkgs, upgrade=upgrade)


@app.command
async def uninstall(packages: list[str], /) -> None:
    """Uninstall OpenFOAM packages."""
    pkgs = {Package(pkg) for pkg in packages}

    await Package.uninstall_all(pkgs)


@app.command
async def freeze() -> None:
    """List installed OpenFOAM packages."""
    for pkg in Package.all_installed():
        print(pkg)


if __name__ == "__main__":
    app()
