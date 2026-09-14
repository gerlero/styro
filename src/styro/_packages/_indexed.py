from __future__ import annotations

import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import aiohttp

from styro._packages._base import Package
from styro._utils.git import clone, fetch
from styro._utils.status import Status


class IndexedPackage(Package):
    @override
    async def fetch(self) -> None:
        with Status(f"🔍 Fetching {self}"):
            try:
                async with (
                    aiohttp.ClientSession(raise_for_status=True) as session,
                    session.get(
                        f"https://raw.githubusercontent.com/exasim-project/opi/main/pkg/{self.name}/metadata.json"
                    ) as response,
                ):
                    self._metadata = await response.json(content_type="text/plain")
            except Exception as e:  # noqa: BLE001
                print(
                    f"🛑 Error: Failed to fetch package '{self.name}': {e}",
                    file=sys.stderr,
                )
                sys.exit(1)

        assert self._metadata is not None

        self._fetched_sha = await fetch(self._pkg_path, self._metadata["repo"])
        if self._fetched_sha is None:
            self._upgrade_available = True
        else:
            self._upgrade_available = self._fetched_sha != self.installed_sha()

    @override
    async def download(self) -> str:
        assert self._metadata is not None
        if self.is_installed():
            title = f"⏩ Updating {self.name}"
        else:
            title = f"⏬ Downloading {self.name}"
        with Status(title):
            return await clone(
                self._pkg_path,
                self._metadata["repo"],
                revision=self._fetched_sha,
            )
