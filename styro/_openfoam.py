import os
from pathlib import Path

import typer


def platform_path() -> Path:
    try:
        app_path = Path(os.environ["FOAM_USER_APPBIN"])
        lib_path = Path(os.environ["FOAM_USER_LIBBIN"])
    except KeyError as e:
        typer.echo(
            "🛑 Error: No OpenFOAM environment found. Please activate (source) the OpenFOAM environment first.",
            err=True,
        )
        raise typer.Exit(code=1) from e

    assert app_path.parent == lib_path.parent
    platform_path = app_path.parent

    assert app_path == platform_path / "bin"
    assert lib_path == platform_path / "lib"

    return platform_path


def openfoam_version() -> int:
    openfoam_version_str = os.environ["WM_PROJECT_VERSION"]
    if openfoam_version_str.startswith("v"):
        openfoam_version = int(openfoam_version_str[1:])
    else:
        openfoam_version = int(openfoam_version_str)

    return openfoam_version
