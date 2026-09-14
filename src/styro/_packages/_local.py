from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import aioshutil

from styro._packages._base import Package
from styro._packages._lock import lock
from styro._utils.paths import path_from_uri


class LocalPackage(Package):
    origin: Path

    def __init__(self, package: str, /) -> None:
        name, origin = Package._parse_package_str(package)

        if origin is None:
            assert name is not None
            with lock as installed:
                origin = installed["packages"][name]["origin"]

        if origin.startswith("file://"):
            path = path_from_uri(origin)
        else:
            path = Path(origin).absolute()

        if name is None:
            name = path.name.lower().replace("_", "-")

        super().__init__(name)
        self.origin = path

    @override
    async def fetch(self) -> None:
        try:
            self._metadata = json.loads((self.origin / "metadata.json").read_text())
        except FileNotFoundError:
            self._metadata = {}
        self._upgrade_available = True

    @override
    async def download(self) -> None:
        assert self._metadata is not None
        await aioshutil.rmtree(self._pkg_path, ignore_errors=True)
        self._pkg_path.parent.mkdir(parents=True, exist_ok=True)
        await aioshutil.copytree(self.origin, self._pkg_path, symlinks=True)

    @override
    def __str__(self) -> str:
        return f"{self.name} @ {self.origin.as_uri()}"
