from __future__ import annotations

import os
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ._util import get_changed_files

if TYPE_CHECKING:
    from collections.abc import Generator


def platform_path() -> Path:
    try:
        app_path = Path(os.environ["FOAM_USER_APPBIN"])
        lib_path = Path(os.environ["FOAM_USER_LIBBIN"])
    except KeyError:
        print(
            "🛑 Error: No OpenFOAM environment found. Please activate (source) the OpenFOAM environment first.",
            file=sys.stderr,
        )
        sys.exit(1)

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


@contextmanager
def get_changed_binaries() -> Generator[set[Path], None, None]:
    ret: set[Path] = set()
    changed_binaries = None
    changed_libraries = None

    try:
        # Use ExitStack to manage multiple contexts cleanly
        with ExitStack() as stack:
            changed_binaries = stack.enter_context(
                get_changed_files(platform_path() / "bin")
            )
            changed_libraries = stack.enter_context(
                get_changed_files(platform_path() / "lib")
            )

            yield ret

        # After ExitStack exits normally, contexts are populated
    finally:
        # Update result with detected changes (works for both normal and exception cases)
        if changed_binaries is not None and changed_libraries is not None:
            ret.update(changed_binaries)
            ret.update(changed_libraries)
