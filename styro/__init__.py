__version__ = "0.1.19"

import asyncio
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar, Dict, List, Optional, Set, Union

if sys.version_info >= (3, 9):
    from collections.abc import Generator
else:
    from typing import Generator

import aiohttp
import typer

from ._git import clone, fetch
from ._openfoam import openfoam_version, platform_path
from ._status import Status
from ._subprocess import run
from ._util import reentrantcontextmanager


@reentrantcontextmanager
def _lock() -> Generator[Dict[str, Any], None, None]:
    installed_path = platform_path() / "styro" / "installed.json"

    installed_path.parent.mkdir(parents=True, exist_ok=True)
    installed_path.touch(exist_ok=True)
    with installed_path.open("r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)

        if f.seek(0, os.SEEK_END) == 0:
            installed = {"version": 1, "packages": {}}
        else:
            f.seek(0)
            installed = json.load(f)
            assert isinstance(installed, dict)
            if installed.get("version") != 1:
                typer.echo(
                    "Error: installed.json file is of a newer version. Please upgrade styro.",
                    err=True,
                )
                raise typer.Exit(code=1)
        try:
            yield installed
        finally:
            f.seek(0)
            f.write(json.dumps(installed, indent=2))
            f.truncate()


lock = _lock()


class Package:
    _instances: ClassVar[Dict[str, "Package"]] = {}
    _install_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    name: str
    _metadata: Optional[Dict[str, Any]]
    _upgrade_available: bool = False
    _origin: Optional[Union[str, Path]]

    @staticmethod
    def installed() -> List["Package"]:
        with lock as installed:
            return [Package(name) for name in installed["packages"]]

    @staticmethod
    @lock
    async def _resolve_all(
        pkgs: Set["Package"],
        *,
        upgrade: bool = False,
    ) -> Set["Package"]:
        resolved: Set[Package] = set()
        return {
            pkg
            for pkgs in await asyncio.gather(
                *(pkg.resolve(upgrade=upgrade, _resolved=resolved) for pkg in pkgs),
            )
            for pkg in pkgs
        }

    @staticmethod
    @lock
    async def install_all(pkgs: Set["Package"], *, upgrade: bool = False) -> None:
        to_install = {
            pkg: asyncio.Event()
            for pkg in await Package._resolve_all(pkgs, upgrade=upgrade)
        }

        await asyncio.gather(
            *(
                pkg.install(_force_reinstall=True, _deps=to_install)
                for pkg in to_install
            ),
        )

    @staticmethod
    @lock
    async def uninstall_all(pkgs: Set["Package"]) -> None:
        dependents = set()
        for pkg in pkgs:
            dependents.update(pkg.installed_dependents())
        dependents -= pkgs
        if dependents:
            typer.echo(
                f"🛑 Error: Cannot uninstall {','.join([pkg.name for pkg in pkgs])}: required by {','.join([dep.name for dep in dependents])}",
                err=True,
            )
            raise typer.Exit(code=1)

        await asyncio.gather(
            *(pkg.uninstall(_force=True) for pkg in pkgs),
        )

    def __new__(cls, package: str) -> "Package":
        origin: Optional[Union[str, Path]] = None
        if package.startswith(("http://", "https://")):
            name = package.split("/")[-1].split(".")[0]
            origin = package
        elif package.startswith((".", "/", "~")):
            origin = Path(package).absolute()
            name = origin.name
        else:
            name = package
            with lock as installed:
                try:
                    origin = installed["packages"][package]["origin"]
                except KeyError:
                    origin = None
                else:
                    assert isinstance(origin, str)
                    if origin.startswith("file://"):
                        origin = Path(origin[7:])

        name = name.lower().replace("_", "-")

        if name in cls._instances:
            return cls._instances[name]

        from ._self import Styro

        instance = super().__new__(cls if name != "styro" else Styro)
        cls._instances[name] = instance
        instance.name = name
        instance._metadata = None
        instance._origin = origin
        return instance

    def _build_steps(self) -> List[str]:
        assert self._metadata is not None

        build = self._metadata.get("build", "wmake")

        if build == "wmake":
            build = ["wmake all -j"]
        elif isinstance(build, str):
            typer.echo(
                f"🛑 Error: Unsupported build system: {build}.",
                err=True,
            )
            raise typer.Exit(code=1)

        return build

    def _check_compatibility(self) -> None:
        assert self._metadata is not None

        distro_compatible = False
        specs = self._metadata.get("version", [])
        for spec in specs:
            try:
                if spec.startswith("=="):
                    version = int(spec[2:])
                    compatible = openfoam_version() == version
                elif spec.startswith("!="):
                    version = int(spec[2:])
                    compatible = openfoam_version() != version
                elif spec.startswith(">="):
                    version = int(spec[2:])
                    compatible = openfoam_version() >= version
                elif spec.startswith(">"):
                    version = int(spec[1:])
                    compatible = openfoam_version() > version
                elif spec.startswith("<="):
                    version = int(spec[2:])
                    compatible = openfoam_version() <= version
                elif spec.startswith("<"):
                    version = int(spec[1:])
                    compatible = openfoam_version() < version
                else:
                    typer.echo(
                        f"⚠️ Warning: {self.name}: ignoring invalid version specifier '{spec}'.",
                        err=True,
                    )
                    continue
            except ValueError:
                typer.echo(
                    f"⚠️ Warning: {self.name}: ignoring invalid version specifier '{spec}'.",
                    err=True,
                )
                continue

            if (openfoam_version() < 1000) == (version < 1000):  # noqa: PLR2004
                distro_compatible = True
                if not compatible:
                    typer.echo(
                        f"🛑 Error: OpenFOAM version is {openfoam_version()}, but {self.name} requires {spec}.",
                        err=True,
                    )
                    raise typer.Exit(code=1)

        if specs and not distro_compatible:
            typer.echo(
                f"🛑 Error: {self.name} is not compatible with this OpenFOAM distribution (requires {', '.join(specs)}).",
                err=True,
            )
            raise typer.Exit(code=1)

    def _installed_sha(self) -> Optional[str]:
        with lock as installed:
            try:
                return installed["packages"][self.name]["sha"]
            except KeyError:
                return None

    @lock
    async def _fetch(self) -> None:
        if self._metadata is None:
            if isinstance(self._origin, Path):
                try:
                    self._metadata = json.loads(
                        (self._origin / "metadata.json").read_text()
                    )
                except FileNotFoundError:
                    self._metadata = {}
                self._upgrade_available = True

            elif isinstance(self._origin, str):
                with Status(f"🔍 Fetching {self}"), TemporaryDirectory() as tmpdir:
                    sha = await clone(
                        Path(tmpdir) / self.name,
                        self._origin,
                    )
                    try:
                        self._metadata = json.loads(
                            (Path(tmpdir) / self.name / "metadata.json").read_text()
                        )
                    except FileNotFoundError:
                        self._metadata = {}
                    self._upgrade_available = sha != self._installed_sha()

            else:
                assert self._origin is None
                with Status(f"🔍 Fetching {self}"):
                    try:
                        async with aiohttp.ClientSession(
                            raise_for_status=True
                        ) as session, session.get(
                            f"https://raw.githubusercontent.com/exasim-project/opi/main/pkg/{self.name}/metadata.json"
                        ) as response:
                            self._metadata = await response.json(
                                content_type="text/plain"
                            )
                    except Exception as e:
                        typer.echo(
                            f"🛑 Error: Failed to fetch package '{self.name}': {e}",
                            err=True,
                        )
                        raise typer.Exit(code=1) from e

                new_sha = await fetch(self._pkg_path, self._metadata["repo"])
                if new_sha is not None:
                    self._upgrade_available = new_sha != self._installed_sha()
                else:
                    self._upgrade_available = False

            self._check_compatibility()
            self._build_steps()

    def dependencies(self) -> Set["Package"]:
        assert self._metadata is not None
        return {Package(name) for name in self._metadata.get("requires", [])}

    def installed_dependents(self) -> Set["Package"]:
        with lock as installed:
            return {
                Package(name)
                for name, data in installed["packages"].items()
                if self.name in data.get("requires", [])
            }

    @lock
    async def resolve(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _resolved: Optional[Set["Package"]] = None,
    ) -> Set["Package"]:
        if _resolved is None:
            _resolved = set()
        elif self in _resolved:
            return set()

        _resolved.add(self)

        if (
            self.is_installed()
            and not upgrade
            and not _force_reinstall
            and not isinstance(self._origin, Path)
        ):
            typer.echo(
                f"✋ Package '{self.name}' is already installed.",
            )
            return set()

        await self._fetch()

        if (
            self.is_installed()
            and not (self._upgrade_available and upgrade)
            and not isinstance(self._origin, Path)
        ):
            typer.echo(
                f"✋ Package '{self.name}' is already up-to-date.",
            )
            return set()

        ret = {self}

        dependencies = await asyncio.gather(
            *(
                dep.resolve(upgrade=True, _resolved=_resolved)
                for dep in self.dependencies()
            ),
            *(
                dep.resolve(_force_reinstall=True, _resolved=_resolved)
                for dep in self.installed_dependents()
            ),
        )
        for deps in dependencies:
            ret.update(deps)

        return ret

    def is_installed(self) -> bool:
        with lock as installed:
            return self.name in installed["packages"]

    @property
    def _pkg_path(self) -> Path:
        return platform_path() / "styro" / "pkg" / self.name

    async def install(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _deps: Union[bool, Dict["Package", asyncio.Event]] = True,
    ) -> None:
        with lock as installed:
            if _deps is True:
                await self.install_all({self}, upgrade=upgrade)
                return

            await self._fetch()
            assert self._metadata is not None

            if isinstance(self._origin, Path):
                if not self._origin.is_dir():
                    typer.echo(
                        f"🛑 Error: Package '{self.name}' source '{self._origin}' is not a directory.",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                shutil.rmtree(
                    self._pkg_path,
                    ignore_errors=True,
                )
                shutil.copytree(
                    self._origin,
                    self._pkg_path,
                )

            if isinstance(self._origin, Path):
                title = f"▶️ Copying {self.name}"
            elif (
                self.is_installed()
                and not _force_reinstall
                and not isinstance(self._origin, Path)
            ):
                if not upgrade:
                    typer.echo(
                        f"✋ Package '{self.name}' is already installed.",
                    )
                    return
                if not self._upgrade_available:
                    typer.echo(
                        f"✋ Package '{self.name}' is already up to date.",
                    )
                    return
                title = f"⏩ Updating {self.name}"
            else:
                title = f"⏬ Downloading {self.name}"

            with Status(title):
                if isinstance(self._origin, Path):
                    shutil.rmtree(
                        self._pkg_path,
                        ignore_errors=True,
                    )
                    shutil.copytree(
                        self._origin,
                        self._pkg_path,
                    )
                    sha = None
                else:
                    origin = (
                        self._origin
                        if isinstance(self._origin, str)
                        else self._metadata["repo"]
                    )
                    sha = await clone(self._pkg_path, origin)

            if self.is_installed():
                await self.uninstall(_force=True, _keep_pkg=True)

            assert not self.is_installed()

            if isinstance(_deps, dict):
                dependencies = self.dependencies()
                await asyncio.gather(
                    *(
                        event.wait()
                        for pkg, event in _deps.items()
                        if pkg in dependencies
                    )
                )

            async with self._install_lock:
                with Status(f"⏳ Installing {self.name}") as status:
                    installed_apps = {
                        app
                        for p in installed["packages"]
                        for app in installed["packages"][p].get("apps", [])
                    }
                    installed_libs = {
                        lib
                        for p in installed["packages"]
                        for lib in installed["packages"][p].get("libs", [])
                    }

                    try:
                        current_apps = {
                            f: f.stat().st_mtime
                            for f in (platform_path() / "bin").iterdir()
                            if f.is_file()
                        }
                    except FileNotFoundError:
                        current_apps = {}
                    try:
                        current_libs = {
                            f: f.stat().st_mtime
                            for f in (platform_path() / "lib").iterdir()
                            if f.is_file()
                        }
                    except FileNotFoundError:
                        current_libs = {}

                    if self.dependencies():
                        env = os.environ.copy()
                        env["OPI_DEPENDENCIES"] = str(self._pkg_path.parent)
                    else:
                        env = None

                    for cmd in self._build_steps():
                        try:
                            await run(
                                ["/bin/bash", "-c", cmd],
                                cwd=self._pkg_path,
                                env=env,
                                status=status,
                            )
                        except subprocess.CalledProcessError as e:
                            typer.echo(
                                f"🛑 Error: failed to build package '{self.name}'\n{e.stderr}",
                                err=True,
                            )

                            try:
                                new_apps = sorted(
                                    f
                                    for f in (platform_path() / "bin").iterdir()
                                    if f.is_file()
                                    and f not in installed_apps
                                    and (
                                        f not in current_apps
                                        or f.stat().st_mtime > current_apps[f]
                                    )
                                )
                            except FileNotFoundError:
                                new_apps = []

                            try:
                                new_libs = sorted(
                                    f
                                    for f in (platform_path() / "lib").iterdir()
                                    if f.is_file()
                                    and f not in installed_libs
                                    and (
                                        f not in current_libs
                                        or f.stat().st_mtime > current_libs[f]
                                    )
                                )
                            except FileNotFoundError:
                                new_libs = []

                            for app in new_apps:
                                with contextlib.suppress(FileNotFoundError):
                                    app.unlink()

                            for lib in new_libs:
                                with contextlib.suppress(FileNotFoundError):
                                    lib.unlink()

                            shutil.rmtree(self._pkg_path, ignore_errors=True)

                            raise typer.Exit(code=1) from e

                        try:
                            new_apps = sorted(
                                f
                                for f in (platform_path() / "bin").iterdir()
                                if f.is_file() and f not in current_apps
                            )
                        except FileNotFoundError:
                            new_apps = []

                        try:
                            new_libs = sorted(
                                f
                                for f in (platform_path() / "lib").iterdir()
                                if f.is_file() and f not in current_libs
                            )
                        except FileNotFoundError:
                            new_libs = []

                        installed["packages"][self.name] = {
                            "apps": [app.name for app in new_apps],
                            "libs": [lib.name for lib in new_libs],
                        }
                        if sha is not None:
                            installed["packages"][self.name]["sha"] = sha
                        if self.dependencies():
                            installed["packages"][self.name]["requires"] = [
                                dep.name for dep in self.dependencies()
                            ]
                        if isinstance(self._origin, Path):
                            installed["packages"][self.name]["origin"] = (
                                self._origin.as_uri()
                            )
                        elif isinstance(self._origin, str):
                            installed["packages"][self.name]["origin"] = self._origin

                typer.echo(f"✅ Package '{self.name}' installed successfully.")

                if new_libs:
                    typer.echo("⚙️ New libraries:")
                    for lib in new_libs:
                        typer.echo(f"  {lib.name}")

                if new_apps:
                    typer.echo("🖥️ New applications:")
                    for app in new_apps:
                        typer.echo(f"  {app.name}")

            if isinstance(_deps, dict):
                _deps[self].set()

    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        if not _force:
            assert not _keep_pkg
            await self.uninstall_all({self})

        with lock as installed:
            if not self.is_installed():
                typer.echo(
                    f"⚠️ Warning: skipping package '{self.name}' as it is not installed.",
                    err=True,
                )
                return

            if not _force and self.installed_dependents():
                typer.echo(
                    f"🛑 Error: Cannot uninstall {self.name}: required by {','.join([dep.name for dep in self.installed_dependents()])}",
                    err=True,
                )
                raise typer.Exit(code=1)

            typer.echo(f"⏳ Uninstalling {self.name}")

            for app in installed["packages"][self.name]["apps"]:
                with contextlib.suppress(FileNotFoundError):
                    (platform_path() / "bin" / app).unlink()

            for lib in installed["packages"][self.name]["libs"]:
                with contextlib.suppress(FileNotFoundError):
                    (platform_path() / "lib" / lib).unlink()

            if not _keep_pkg:
                shutil.rmtree(
                    self._pkg_path,
                    ignore_errors=True,
                )

            del installed["packages"][self.name]

        typer.echo(f"🗑️ Package '{self.name}' uninstalled successfully.")

    def __repr__(self) -> str:
        return f"Package({self.name!r})"

    def __str__(self) -> str:
        if isinstance(self._origin, Path):
            return f"{self.name} @ {self._origin.as_uri()}"
        if isinstance(self._origin, str):
            return f"{self.name} @ {self._origin}"
        return self.name
