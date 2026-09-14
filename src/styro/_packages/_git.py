from __future__ import annotations

import json
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


from styro._packages._base import Package
from styro._packages._lock import lock
from styro._utils.git import clone, fetch, read_text
from styro._utils.status import Status


class GitPackage(Package):
    origin: str

    def __init__(self, package: str, /) -> None:
        name, origin = Package._parse_package_str(package)

        if origin is None:
            assert name is not None
            with lock as installed:
                origin = installed["packages"][name]["origin"]

        assert origin.startswith(("http://", "https://"))

        if name is None:
            name = origin.rsplit("/", 1)[-1].split(".", 1)[0].lower().replace("_", "-")

        super().__init__(name)
        self.origin = origin

    @override
    async def fetch(self) -> None:
        with Status(f"⏬ Downloading {self}"):
            self._fetched_sha = await fetch(
                self._pkg_path,
                self.origin,
                missing_ok=False,
                system_git=True,
            )
            assert self._fetched_sha is not None

            metadata = read_text(
                self._pkg_path,
                "metadata.json",
                revision=self._fetched_sha,
            )
            self._metadata = {} if metadata is None else json.loads(metadata)

            self._upgrade_available = self._fetched_sha != self.installed_sha()

    @override
    async def download(self) -> str:
        return await clone(
            self._pkg_path,
            self.origin,
            revision=self._fetched_sha,
            system_git=True,
        )

    @override
    def __str__(self) -> str:
        return f"{self.name} @ {self.origin}"
