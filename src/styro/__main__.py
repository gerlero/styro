"""Package manager for OpenFOAM."""

from __future__ import annotations

import cyclopts

from styro import __version__
from styro._packages import Package
from styro._self import check_for_new_version


async def _version_callback() -> str:
    await check_for_new_version(verbose=True, timeout=3)
    return f"styro {__version__}"


app = cyclopts.App(help=__doc__, version=_version_callback)


@app.command
async def install(packages: set[Package], /, *, upgrade: bool = False) -> None:
    """Install OpenFOAM packages."""
    if not upgrade or Package("styro") not in packages:
        await check_for_new_version(verbose=True, timeout=3)

    await Package.install_all(packages, upgrade=upgrade)


@app.command
async def uninstall(packages: set[Package], /) -> None:
    """Uninstall OpenFOAM packages."""
    await Package.uninstall_all(packages)


@app.command
async def freeze() -> None:
    """List installed OpenFOAM packages."""
    for pkg in Package.all_installed():
        print(pkg)


if __name__ == "__main__":
    app()
