__version__ = "0.1.14"

import asyncio
import contextlib
import fcntl
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Set

if sys.version_info >= (3, 9):
    from collections.abc import Generator
else:
    from typing import Generator

import aiohttp
import typer

from ._git import clone, fetch
from ._self import (
    check_for_new_version,
    is_managed_installation,
    print_upgrade_instruction,
)
from ._subprocess import run


def _platform_path() -> Path:
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


def _openfoam_version() -> int:
    openfoam_version_str = os.environ["WM_PROJECT_VERSION"]
    if openfoam_version_str.startswith("v"):
        openfoam_version = int(openfoam_version_str[1:])
    else:
        openfoam_version = int(openfoam_version_str)

    return openfoam_version


class _Package:
    _installed: ClassVar[Optional[Dict[str, Any]]] = None
    _instances: ClassVar[Dict[str, "_Package"]] = {}

    name: str
    _metadata: Optional[Dict[str, Any]]

    @staticmethod
    @contextlib.contextmanager
    def lock(*, write: bool = False) -> Generator[None, None, None]:
        assert _Package._installed is None

        installed_path = _platform_path() / "styro" / "installed.json"

        installed_path.parent.mkdir(parents=True, exist_ok=True)
        installed_path.touch(exist_ok=True)
        with installed_path.open("r+" if write else "r") as f:
            fcntl.flock(f, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
            if f.seek(0, os.SEEK_END) == 0:
                _Package._installed = {"version": 1, "packages": {}}
            else:
                f.seek(0)
                _Package._installed = json.load(f)

            if _Package._installed.get("version") != 1:
                typer.echo(
                    "Error: installed.json file is of a newer version. Please upgrade styro.",
                    err=True,
                )
                raise typer.Exit(code=1)

            try:
                yield
            finally:
                if write:
                    f.seek(0)
                    json.dump(_Package._installed, f, indent=4)
                    f.truncate()

                _Package._installed = None

    @staticmethod
    def installed() -> List["_Package"]:
        assert _Package._installed is not None
        return [_Package(name) for name in _Package._installed["packages"]]

    @staticmethod
    async def _resolve_all(
        pkgs: Set["_Package"],
    ) -> Set["_Package"]:
        resolved: Set[_Package] = set()
        return {
            pkg
            for pkgs in await asyncio.gather(
                *(pkg.resolve(_resolved=resolved) for pkg in pkgs),
            )
            for pkg in pkgs
        }

    @staticmethod
    def _sort_for_install(pkgs: Set["_Package"]) -> List["_Package"]:
        unsorted = set(pkgs)
        sorted_: List[_Package] = []

        while unsorted:
            for pkg in list(unsorted):
                if all(dep not in pkgs or dep in sorted_ for dep in pkg.dependencies()):
                    sorted_.append(pkg)
                    unsorted.remove(pkg)

        assert len(sorted_) == len(pkgs)
        return sorted_

    @staticmethod
    async def install_all(pkgs: Set["_Package"]) -> None:
        to_install = _Package._sort_for_install(await _Package._resolve_all(pkgs))

        await asyncio.gather(
            *(
                pkg.uninstall(_force=True, _keep_pkg=True)
                for pkg in to_install
                if pkg.is_installed()
            ),
        )

        for pkg in to_install:
            await pkg.install(_deps=False)

    @staticmethod
    async def uninstall_all(pkgs: Set["_Package"]) -> None:
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

    def __new__(cls, name: str) -> "_Package":
        name = name.lower().replace("_", "-")

        if name in cls._instances:
            return cls._instances[name]

        instance = super().__new__(cls if name != "styro" else _Styro)
        cls._instances[name] = instance
        instance.name = name
        instance._metadata = None
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

        distro_compatibility = False
        openfoam_version = _openfoam_version()
        specs = self._metadata.get("version", [])
        for spec in specs:
            try:
                if spec.startswith("=="):
                    version = int(spec[2:])
                    compatible = openfoam_version == version
                elif spec.startswith("!="):
                    version = int(spec[2:])
                    compatible = openfoam_version != version
                elif spec.startswith(">="):
                    version = int(spec[2:])
                    compatible = openfoam_version >= version
                elif spec.startswith(">"):
                    version = int(spec[1:])
                    compatible = openfoam_version > version
                elif spec.startswith("<="):
                    version = int(spec[2:])
                    compatible = openfoam_version <= version
                elif spec.startswith("<"):
                    version = int(spec[1:])
                    compatible = openfoam_version < version
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

            if (openfoam_version < 1000) == (version < 1000):  # noqa: PLR2004
                distro_compatibility = True
                if not compatible:
                    typer.echo(
                        f"🛑 Error: OpenFOAM version is {openfoam_version}, but {self.name} requires {spec}.",
                        err=True,
                    )

        if not distro_compatibility:
            typer.echo(
                f"🛑 Error: {self.name} is not compatible with this OpenFOAM distribution (requires {specs}).",
                err=True,
            )

    def dependencies(self) -> Set["_Package"]:
        assert self._metadata is not None
        return {_Package(name) for name in self._metadata.get("requires", [])}

    def installed_dependents(self) -> Set["_Package"]:
        assert self._installed is not None
        return {
            _Package(name)
            for name, data in self._installed["packages"].items()
            if self.name in data.get("requires", [])
        }

    async def resolve(
        self,
        *,
        _force_reinstall: bool = False,
        _resolved: Optional[Set["_Package"]] = None,
    ) -> Set["_Package"]:
        assert self._installed is not None
        if _resolved is None:
            _resolved = set()
        elif self in _resolved:
            return set()

        _resolved.add(self)

        typer.echo(f"🔍 Resolving {self.name}...")

        if self._metadata is None:
            try:
                async with aiohttp.ClientSession(
                    raise_for_status=True
                ) as session, session.get(
                    f"https://raw.githubusercontent.com/exasim-project/opi/main/pkg/{self.name}/metadata.json"
                ) as response:
                    self._metadata = await response.json(content_type="text/plain")
            except Exception as e:
                typer.echo(
                    f"🛑 Error: Failed to resolve package '{self.name}': {e}",
                    err=True,
                )
                raise typer.Exit(code=1) from e

            self._check_compatibility()
            self._build_steps()

            if self.is_installed() and not _force_reinstall:
                sha = await fetch(self._pkg_path, self._metadata["repo"])
                if (
                    sha is not None
                    and sha == self._installed["packages"][self.name]["sha"]
                ):
                    typer.echo(f"✋ Package '{self.name}' is already up-to-date.")
                    return set()

        ret = {self}

        dependencies = await asyncio.gather(
            *(dep.resolve(_resolved=_resolved) for dep in self.dependencies()),
            *(
                dep.resolve(_force_reinstall=True, _resolved=_resolved)
                for dep in self.installed_dependents()
            ),
        )
        for deps in dependencies:
            ret.update(deps)

        return ret

    def is_installed(self) -> bool:
        assert self._installed is not None
        return self.name in self._installed["packages"]

    @property
    def _pkg_path(self) -> Path:
        return _platform_path() / "styro" / "pkg" / self.name

    async def install(self, *, _deps: bool = True) -> None:
        assert self._installed is not None

        if _deps:
            await self.install_all({self})
            return

        assert self._metadata is not None

        if self.is_installed():
            typer.echo(f"⏩ Updating {self.name}...")
        else:
            typer.echo(f"⏬ Downloading {self.name}...")

        sha = await clone(self._pkg_path, self._metadata["repo"])

        assert not self.is_installed()

        typer.echo(f"⏳ Installing {self.name}...")

        installed_apps = {
            app
            for p in self._installed["packages"]
            for app in self._installed["packages"][p].get("apps", [])
        }
        installed_libs = {
            lib
            for p in self._installed["packages"]
            for lib in self._installed["packages"][p].get("libs", [])
        }

        try:
            current_apps = {
                f: f.stat().st_mtime
                for f in (_platform_path() / "bin").iterdir()
                if f.is_file()
            }
        except FileNotFoundError:
            current_apps = {}
        try:
            current_libs = {
                f: f.stat().st_mtime
                for f in (_platform_path() / "lib").iterdir()
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
                )
            except subprocess.CalledProcessError as e:
                typer.echo(
                    f"Error: failed to build package '{self.name}'\n{e.stderr}",
                    err=True,
                )

                try:
                    new_apps = sorted(
                        f
                        for f in (_platform_path() / "bin").iterdir()
                        if f.is_file()
                        and f not in installed_apps
                        and (
                            f not in current_apps or f.stat().st_mtime > current_apps[f]
                        )
                    )
                except FileNotFoundError:
                    new_apps = []

                try:
                    new_libs = sorted(
                        f
                        for f in (_platform_path() / "lib").iterdir()
                        if f.is_file()
                        and f not in installed_libs
                        and (
                            f not in current_libs or f.stat().st_mtime > current_libs[f]
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
                    for f in (_platform_path() / "bin").iterdir()
                    if f.is_file() and f not in current_apps
                )
            except FileNotFoundError:
                new_apps = []

            try:
                new_libs = sorted(
                    f
                    for f in (_platform_path() / "lib").iterdir()
                    if f.is_file() and f not in current_libs
                )
            except FileNotFoundError:
                new_libs = []

            self._installed["packages"][self.name] = {
                "sha": sha,
                "apps": [app.name for app in new_apps],
                "libs": [lib.name for lib in new_libs],
            }
            if self.dependencies():
                self._installed["packages"][self.name]["requires"] = [
                    dep.name for dep in self.dependencies()
                ]

            typer.echo(f"✅ Package '{self.name}' installed successfully.")

            if new_libs:
                typer.echo("⚙️ New libraries:")
                for lib in new_libs:
                    typer.echo(f"  {lib.name}")

            if new_apps:
                typer.echo("🖥️ New applications:")
                for app in new_apps:
                    typer.echo(f"  {app.name}")

    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        if not _force:
            assert not _keep_pkg
            await self.uninstall_all({self})

        assert self._installed is not None
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

        typer.echo(f"⏳ Uninstalling {self.name}...")

        for app in self._installed["packages"][self.name]["apps"]:
            with contextlib.suppress(FileNotFoundError):
                (_platform_path() / "bin" / app).unlink()

        for lib in self._installed["packages"][self.name]["libs"]:
            with contextlib.suppress(FileNotFoundError):
                (_platform_path() / "lib" / lib).unlink()

        if not _keep_pkg:
            shutil.rmtree(
                self._pkg_path,
                ignore_errors=True,
            )

        del self._installed["packages"][self.name]

        typer.echo(f"🗑️ Package '{self.name}' uninstalled successfully.")

    def __repr__(self) -> str:
        return f"Package({self.name!r})"

    def __str__(self) -> str:
        return self.name


class _Styro(_Package):
    def is_installed(self) -> bool:
        return True

    async def resolve(
        self,
        *,
        _force_reinstall: bool = False,
        _resolved: Optional[Set["_Package"]] = None,
    ) -> Set["_Package"]:
        typer.echo("🔍 Resolving styro..")

        if self._metadata is not None:
            self._metadata = {}

        if not await check_for_new_version(verbose=False):
            return set()

        if is_managed_installation():
            typer.echo(
                "🛑 Error: This is a managed installation of styro.",
                err=True,
            )
            print_upgrade_instruction()
            raise typer.Exit(code=1)

        return {self}

    async def install(self, *, _deps: bool = True) -> None:
        assert not is_managed_installation()

        typer.echo("⏬ Downloading styro...")
        try:
            async with aiohttp.ClientSession(
                raise_for_status=True
            ) as session, session.get(
                f"https://github.com/gerlero/styro/releases/latest/download/styro-{platform.system()}-{platform.machine()}.tar.gz"
            ) as response:
                contents = await response.read()
        except Exception as e:
            typer.echo(f"🛑 Error: Failed to download styro: {e}", err=True)
            raise typer.Exit(code=1) from e
        typer.echo("⏳ Upgrading styro...")
        try:
            with tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz") as tar:
                tar.extract("styro", path=Path(sys.executable).parent)
        except Exception as e:
            typer.echo(f"🛑 Error: Failed to upgrade styro: {e}", err=True)
            raise typer.Exit(code=1) from e
        typer.echo("✅ Package 'styro' upgraded successfully.")

    def dependencies(self) -> Set[_Package]:
        return set()

    def installed_dependents(self) -> Set[_Package]:
        return {self}

    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        typer.echo(
            "🛑 Error: styro cannot be uninstalled this way.",
            err=True,
        )
        if is_managed_installation():
            typer.echo(
                "💡 Use your package manager (e.g. pip) to uninstall styro.",
                err=True,
            )
        else:
            typer.echo(
                "💡 Delete the 'styro' binary in $FOAM_USER_APPBIN to uninstall.",
                err=True,
            )
        raise typer.Exit(code=1)
