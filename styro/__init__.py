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
from typing import Any, ClassVar, Dict, List, Optional

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
    _build_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    name: str
    _metadata: Optional[Dict[str, Any]]
    _lock: asyncio.Lock
    to_install: bool

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

    def __new__(cls, name: str) -> "_Package":
        name = name.lower().replace("_", "-")

        if name in cls._instances:
            return cls._instances[name]

        instance = super().__new__(cls if name != "styro" else _Styro)
        cls._instances[name] = instance
        instance.name = name
        instance._metadata = None
        instance._lock = asyncio.Lock()
        instance.to_install = False
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

    def _resolved_dependencies(self) -> List["_Package"]:
        assert self._metadata is not None
        return [_Package(name) for name in self._metadata.get("requires", [])]

    def _installed_dependents(self) -> List["_Package"]:
        assert self._installed is not None
        return [
            _Package(name)
            for name, data in self._installed["packages"].items()
            if self.name in data.get("requires", [])
        ]

    async def resolve(self, *, force_reinstall: bool = False) -> None:
        assert self._installed is not None
        async with self._lock:
            if self._metadata is not None and (self.to_install or not force_reinstall):
                return

            if self._metadata is None:
                typer.echo(f"🔍 Resolving {self.name}...")

                try:
                    try:
                        async with aiohttp.ClientSession(
                            raise_for_status=True
                        ) as session, session.get(
                            f"https://raw.githubusercontent.com/exasim-project/opi/main/pkg/{self.name}/metadata.json"
                        ) as response:
                            self._metadata = await response.json(
                                content_type="text/plain"
                            )
                    except aiohttp.ClientError as e:
                        if response.status == 404:  # noqa: PLR2004
                            typer.echo(
                                f"🛑 Error: Package '{self.name}' not found in the OpenFOAM Package Index (OPI).\nSee https://github.com/exasim-project/opi for more information.",
                                err=True,
                            )

                            raise typer.Exit(code=1) from e
                        raise
                except Exception as e:
                    typer.echo(
                        f"🛑 Error: Failed to resolve package '{self.name}': {e}",
                        err=True,
                    )
                    raise typer.Exit(code=1) from e

                self._check_compatibility()
                self._build_steps()

                if self.is_installed() and not force_reinstall:
                    sha = await fetch(self._pkg_path, self._metadata["repo"])
                    if (
                        sha is not None
                        and sha == self._installed["packages"][self.name]["sha"]
                    ):
                        return

            self.to_install = True

        await asyncio.gather(
            *(dep.resolve() for dep in self._resolved_dependencies()),
            *(
                dep.resolve(force_reinstall=True)
                for dep in self._installed_dependents()
            ),
        )

    def is_installed(self) -> bool:
        assert self._installed is not None
        if self.name == "styro":
            return True
        return self.name in self._installed["packages"]

    @property
    def _pkg_path(self) -> Path:
        return _platform_path() / "styro" / "pkg" / self.name

    async def install(self) -> None:
        assert self._installed is not None
        async with self._lock:
            if not self.to_install:
                if self._metadata is not None:
                    typer.echo(f"✋ Package '{self.name}' is already up-to-date.")
                else:
                    typer.echo(f"✋ Package '{self.name}' is already installed.")
                return

        assert self._metadata is not None

        await asyncio.gather(
            *(dep.install() for dep in self._resolved_dependencies()),
        )

        if self.is_installed():
            typer.echo(f"⏩ Updating {self.name}...")
        else:
            typer.echo(f"⏬ Downloading {self.name}...")

        sha = await clone(self._pkg_path, self._metadata["repo"])

        async with self._lock:
            if self.is_installed():
                self.uninstall(keep_pkg=True)

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

            if self._resolved_dependencies():
                assert all(dep.is_installed() for dep in self._resolved_dependencies())
                env = os.environ.copy()
                env["OPI_DEPENDENCIES"] = str(self._pkg_path.parent)
            else:
                env = None

            for cmd in self._build_steps():
                try:
                    async with self._build_lock:
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
                                f not in current_apps
                                or f.stat().st_mtime > current_apps[f]
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
            if self._resolved_dependencies():
                self._installed["packages"][self.name]["requires"] = [
                    dep.name for dep in self._resolved_dependencies()
                ]

            self.to_install = False

            typer.echo(f"✅ Package '{self.name}' installed successfully.")

            if new_libs:
                typer.echo("⚙️ New libraries:")
                for lib in new_libs:
                    typer.echo(f"  {lib.name}")

            if new_apps:
                typer.echo("🖥️ New applications:")
                for app in new_apps:
                    typer.echo(f"  {app.name}")

        await asyncio.gather(
            *(dep.install() for dep in self._installed_dependents() if dep.to_install),
        )

    def uninstall(self, *, keep_pkg: bool = False) -> None:
        assert self._installed is not None
        if self.name not in self._installed["packages"]:
            typer.echo(
                f"⚠️ Warning: skipping package '{self.name}' as it is not installed.",
                err=True,
            )
            return

        typer.echo(f"⏳ Uninstalling {self.name}...")

        for app in self._installed["packages"][self.name]["apps"]:
            with contextlib.suppress(FileNotFoundError):
                (_platform_path() / "bin" / app).unlink()

        for lib in self._installed["packages"][self.name]["libs"]:
            with contextlib.suppress(FileNotFoundError):
                (_platform_path() / "lib" / lib).unlink()

        if not keep_pkg:
            shutil.rmtree(
                self._pkg_path,
                ignore_errors=True,
            )

        del self._installed["packages"][self.name]

        typer.echo(f"🗑️ Package '{self.name}' uninstalled successfully.")


class _Styro(_Package):
    def is_installed(self) -> bool:
        return True

    async def resolve(self, *, force_reinstall: bool = False) -> None:
        assert not force_reinstall
        async with self._lock:
            if self._metadata is not None:
                return

            typer.echo("🔍 Resolving styro..")

            self._metadata = {}

            if not await check_for_new_version(verbose=False):
                return

            if is_managed_installation():
                typer.echo(
                    "🛑 Error: This is a managed installation of styro.",
                    err=True,
                )
                print_upgrade_instruction()
                raise typer.Exit(code=1)

            self.to_install = True

    async def install(self) -> None:
        async with self._lock:
            if not self.to_install:
                if self._metadata is not None:
                    typer.echo("✋ Package 'styro' is already up-to-date.")
                else:
                    typer.echo("✋ Package 'styro' is already installed.")
                return

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
            return

    def _resolved_dependencies(self) -> List[_Package]:
        raise NotImplementedError

    def _installed_dependents(self) -> List[_Package]:
        raise NotImplementedError

    def uninstall(self, *, keep_pkg: bool = False) -> None:  # noqa: ARG002
        typer.echo(
            "🛑 Error: styro cannot be uninstalled using styro.",
            err=True,
        )
        if is_managed_installation():
            typer.echo(
                "Use your package manager (e.g. pip) to uninstall styro.",
                err=True,
            )
        else:
            typer.echo(
                "Delete the styro binary in $FOAM_USER_APPBIN to uninstall.",
                err=True,
            )
        raise typer.Exit(code=1)
