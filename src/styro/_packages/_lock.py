from __future__ import annotations

import fcntl
import json
import sys
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from styro._openfoam import platform_path
from styro._utils.context import reentrantcontextmanager

if TYPE_CHECKING:
    from collections.abc import Generator


@reentrantcontextmanager
def _lock() -> Generator[dict[str, Any], None, None]:
    installed_path = platform_path() / "styro" / "installed.json"

    installed_path.parent.mkdir(parents=True, exist_ok=True)
    installed_path.touch(exist_ok=True)
    with installed_path.open("r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)

        try:
            f.seek(0)
            installed = json.load(f)
        except json.JSONDecodeError:
            installed = {}
        else:
            assert isinstance(installed, dict)
            if installed.get("version") != 1:
                from styro._packages._base import Package

                print(
                    "🛑 Error: installed.json file is of a newer version. Please upgrade styro.",
                    file=sys.stderr,
                )
                Package("styro").print_upgrade_instruction()
                sys.exit(1)
        installed_copy = deepcopy(installed)
        try:
            yield installed
        finally:
            if installed:
                if installed != installed_copy:
                    f.seek(0)
                    f.write(json.dumps(installed, indent=2))
                    f.truncate()
            else:
                installed_path.unlink()


lock = _lock()
