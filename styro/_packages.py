from __future__ import annotations

__version__ = "0.1.19"

import asyncio
import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import aiohttp

from ._git import clone, fetch
from ._openfoam import get_changed_binaries, openfoam_version, platform_path
from ._self import (
    check_for_new_version,
    is_managed_installation,
    print_upgrade_instruction,
    selfupgrade,
)
from ._status import Status
from ._subprocess import run
from ._util import path_from_uri, reentrantcontextmanager

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
                print(
                    "🛑 Error: installed.json file is of a newer version. Please upgrade styro.",
                    file=sys.stderr,
                )
                print_upgrade_instruction()
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


class Package:
    __install_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    __name_regex: ClassVar[re.Pattern] = re.compile(
        r"^(?!.*--)[a-z0-9]+(-[a-z0-9]+)*$",
    )

    @staticmethod
    def _check_for_duplicate_names(pkgs: set[Package]) -> None:
        duplicate_names = {
            pkg.name for pkg in pkgs if len([p for p in pkgs if p.name == pkg.name]) > 1
        }
        if duplicate_names:
            print(
                f"🛑 Error: duplicate/conflicting package names: {', '.join(duplicate_names)}",
                file=sys.stderr,
            )
            sys.exit(1)

    @staticmethod
    def all_installed_binaries() -> set[Path]:
        with lock as installed:
            return {
                Path(platform_path() / "bin" / app)
                for pkg in installed.get("packages", {}).values()
                for app in pkg.get("apps", [])
            }.union(
                {
                    Path(platform_path() / "lib" / lib)
                    for pkg in installed.get("packages", {}).values()
                    for lib in pkg.get("libs", [])
                }
            )

    @staticmethod
    def parse_package(
        package: str,
    ) -> tuple[str, None] | tuple[None, str] | tuple[str, str]:
        name = package.lower().replace("_", "-")
        if Package.__name_regex.match(name):
            return name, None
        if "@" in package:
            name, origin = package.split("@", 1)
            name = name.rstrip().lower().replace("_", "-")
            origin = origin.lstrip()
            if Package.__name_regex.match(name):
                return name, origin
            print(
                f"🛑 Error: Invalid package name: {name}",
                file=sys.stderr,
            )
            sys.exit(1)
        return None, package

    @staticmethod
    def all_installed() -> set[Package]:
        with lock as installed:
            return {Package(name) for name in installed.get("packages", {})}

    @staticmethod
    async def _detect_cycles(pkgs: set[Package], *, upgrade: bool = False) -> None:
        """
        Detect cycles in the dependency graph before installation.

        Uses depth-first search with three states:
        - unvisited (white): package not yet visited
        - visiting (gray): package currently being processed
        - visited (black): package and all its dependencies processed

        Raises SystemExit if a cycle is detected.
        """

        class State(Enum):
            UNVISITED = 0
            VISITING = 1
            VISITED = 2

        states: dict[Package, State] = {}
        path: list[Package] = []

        async def visit(
            pkg: Package,
            *,
            pkg_upgrade: bool = False,
            pkg_force_reinstall: bool = False,
        ) -> None:
            if states.get(pkg, State.UNVISITED) == State.VISITED:
                return

            if states.get(pkg, State.UNVISITED) == State.VISITING:
                # Found a cycle - construct the cycle path
                cycle_start_idx = path.index(pkg)
                cycle = [*path[cycle_start_idx:], pkg]
                cycle_names = " -> ".join(p.name for p in cycle)

                print(
                    f"❌ Dependency cycle detected: {cycle_names}",
                    file=sys.stderr,
                )
                sys.exit(1)

            states[pkg] = State.VISITING
            path.append(pkg)

            # Follow the same logic as resolve() method
            # Early return if package is already installed and no upgrade/force reinstall
            if (
                pkg.installed_sha() is not None
                and not pkg_upgrade
                and not pkg_force_reinstall
            ):
                path.pop()
                states[pkg] = State.VISITED
                return

            # Check if we need to fetch metadata to get dependencies
            if pkg._metadata is None:
                with contextlib.suppress(Exception):
                    await pkg.fetch()

            # Check again after potential fetch
            if (
                pkg._metadata is not None
                and pkg.installed_sha() is not None
                and not pkg._upgrade_available
                and not pkg_force_reinstall
            ):
                path.pop()
                states[pkg] = State.VISITED
                return

            # Only visit dependencies if the package actually needs resolution
            # This mirrors the resolve() method logic exactly
            if pkg._metadata is not None:
                # Visit requested dependencies (with upgrade=True)
                for dep in pkg.requested_dependencies():
                    await visit(dep, pkg_upgrade=True, pkg_force_reinstall=False)

                # Visit installed dependents (reverse dependencies) with force_reinstall=True
                for dependent in pkg.installed_dependents():
                    await visit(dependent, pkg_upgrade=False, pkg_force_reinstall=True)

            path.pop()
            states[pkg] = State.VISITED

        # Start DFS from all root packages with the provided upgrade setting
        for pkg in pkgs:
            if states.get(pkg, State.UNVISITED) == State.UNVISITED:
                await visit(pkg, pkg_upgrade=upgrade, pkg_force_reinstall=False)

    @staticmethod
    @lock
    async def resolve_all(
        pkgs: set[Package],
        *,
        upgrade: bool = False,
    ) -> set[Package]:
        Package._check_for_duplicate_names(pkgs)

        # Detect cycles before attempting resolution
        await Package._detect_cycles(pkgs, upgrade=upgrade)

        resolved: set[Package] = set()
        return {
            pkg
            for pkgs in await asyncio.gather(
                *(pkg.resolve(upgrade=upgrade, _resolved=resolved) for pkg in pkgs),
            )
            for pkg in pkgs
        }

    @staticmethod
    @lock
    async def install_all(pkgs: set[Package], *, upgrade: bool = False) -> None:
        to_install = {
            pkg: asyncio.Event()
            for pkg in await Package.resolve_all(pkgs, upgrade=upgrade)
        }

        not_to_install = pkgs.difference(to_install)

        Package._check_for_duplicate_names(set(to_install).union(not_to_install))

        await asyncio.gather(
            *(pkg.install(upgrade=upgrade, _deps=False) for pkg in not_to_install),
            *(
                pkg.install(_force_reinstall=True, _deps=to_install)
                for pkg in to_install
            ),
        )

    @staticmethod
    @lock
    async def uninstall_all(pkgs: set[Package]) -> None:
        dependents = set()
        for pkg in pkgs:
            dependents.update(pkg.installed_dependents())
        dependents -= pkgs
        if dependents:
            print(
                f"🛑 Error: Cannot uninstall {','.join([pkg.name for pkg in pkgs])}: required by {','.join([dep.name for dep in dependents])}",
                file=sys.stderr,
            )
            sys.exit(1)

        await asyncio.gather(
            *(pkg.uninstall(_force=True) for pkg in pkgs),
        )

    def __new__(cls, package: str) -> Self:
        if cls is not Package:
            return super().__new__(cls)

        name, origin = Package.parse_package(package)

        with lock as installed:
            if name is not None and origin is None:
                with contextlib.suppress(KeyError):
                    origin = installed["packages"][name]["origin"]

            if origin is not None:
                if origin.startswith(("http://", "https://")):
                    return super().__new__(_GitPackage)
                return super().__new__(_LocalPackage)
            if name == "styro":
                return super().__new__(_Styro)
            return super().__new__(_IndexedPackage)

    def __init__(self, name: str) -> None:
        if not Package.__name_regex.match(name):
            print(
                f"🛑 Error: Invalid package name: {name}",
                file=sys.stderr,
            )
            sys.exit(1)
        if name == "styro" and not isinstance(self, _Styro):
            print(
                "🛑 Error: 'styro' not allowed as a package name.",
                file=sys.stderr,
            )
            sys.exit(1)
        self.name = name
        self.origin: str | Path | None = None
        self._metadata: dict[str, Any] | None = None
        self._upgrade_available = False

    def _build_steps(self) -> list[str]:
        assert self._metadata is not None

        build = self._metadata.get("build", "wmake")

        if build == "wmake":
            build = ["wmake all -j"]
        elif isinstance(build, str):
            print(
                f"🛑 Error: Unsupported build system: {build}.",
                file=sys.stderr,
            )
            sys.exit(1)

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
                    print(
                        f"⚠️ Warning: {self.name}: ignoring invalid version specifier '{spec}'.",
                        file=sys.stderr,
                    )
                    continue
            except ValueError:
                print(
                    f"⚠️ Warning: {self.name}: ignoring invalid version specifier '{spec}'.",
                    file=sys.stderr,
                )
                continue

            if (openfoam_version() < 1000) == (version < 1000):  # noqa: PLR2004
                distro_compatible = True
                if not compatible:
                    print(
                        f"🛑 Error: OpenFOAM version is {openfoam_version()}, but {self.name} requires {spec}.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

        if specs and not distro_compatible:
            print(
                f"🛑 Error: {self.name} is not compatible with this OpenFOAM distribution (requires {', '.join(specs)}).",
                file=sys.stderr,
            )
            sys.exit(1)

    async def fetch(self) -> None:
        raise NotImplementedError

    async def resolve(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _resolved: set[Package] | None = None,
    ) -> set[Package]:
        if _resolved is None:
            _resolved = set()
        elif self in _resolved:
            return set()

        _resolved.add(self)

        if self.installed_sha() is not None and not upgrade and not _force_reinstall:
            return set()

        if self._metadata is None:
            await self.fetch()
            assert self._metadata is not None
            self._check_compatibility()
            self._build_steps()

        if (
            self.installed_sha() is not None
            and not self._upgrade_available
            and not _force_reinstall
        ):
            return set()

        ret = {self}

        dependencies = await asyncio.gather(
            *(
                dep.resolve(upgrade=True, _resolved=_resolved)
                for dep in self.requested_dependencies()
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
        return self in self.all_installed()

    def installed_binaries(self) -> set[Path]:
        with lock as installed:
            if not self.is_installed():
                return set()
            try:
                return {
                    Path(platform_path() / "bin" / app)
                    for app in installed["packages"][self.name].get("apps", [])
                }.union(
                    {
                        Path(platform_path() / "lib" / app)
                        for app in installed["packages"][self.name].get("libs", [])
                    }
                )
            except KeyError:
                return set()

    def installed_sha(self) -> str | None:
        with lock as installed:
            if not self.is_installed():
                return None
            try:
                return installed["packages"][self.name]["sha"]
            except KeyError:
                return None

    def requested_dependencies(self) -> set[Package]:
        assert self._metadata is not None
        return {Package(name) for name in self._metadata.get("requires", [])}

    def installed_dependents(self) -> set[Package]:
        with lock as installed:
            return {
                Package(name)
                for name, data in installed.get("packages", {}).items()
                if self.name in data.get("requires", [])
            }

    @property
    def _pkg_path(self) -> Path:
        return platform_path() / "styro" / "pkg" / self.name

    async def download(self) -> str | None:
        raise NotImplementedError

    async def install(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _deps: bool | dict[Package, asyncio.Event] = True,
    ) -> None:
        with lock as installed:
            if _deps is True:
                await self.install_all({self}, upgrade=upgrade)
                return

            if (
                self.is_installed()
                and not isinstance(self, _LocalPackage)
                and not upgrade
                and not _force_reinstall
            ):
                print(
                    f"✋ Package '{self.name}' is already installed.",
                )
                return

            if self._metadata is None:
                await self.fetch()
                assert self._metadata is not None
                self._check_compatibility()

            if (
                self.is_installed()
                and not isinstance(self, _LocalPackage)
                and not self._upgrade_available
                and not _force_reinstall
            ):
                print(
                    f"✋ Package '{self.name}' is already up-to-date.",
                )
                return

            sha = await self.download()

            if Package(self.name).is_installed():
                await Package(self.name).uninstall(_force=True, _keep_pkg=True)

            assert not self.is_installed()

            if isinstance(_deps, dict):
                dependencies = self.requested_dependencies()
                await asyncio.gather(
                    *(
                        event.wait()
                        for pkg, event in _deps.items()
                        if pkg in dependencies
                    )
                )

            async with self.__install_lock:
                with Status(f"⏳ Installing {self.name}") as status:
                    if self.requested_dependencies():
                        env = os.environ.copy()
                        env["OPI_DEPENDENCIES"] = str(self._pkg_path.parent)
                    else:
                        env = None

                    try:
                        with get_changed_binaries() as installed_binaries:
                            for cmd in self._build_steps():
                                await run(
                                    ["/bin/bash", "-c", cmd],
                                    cwd=self._pkg_path,
                                    env=env,
                                    status=status,
                                )
                    except subprocess.CalledProcessError as e:
                        print(
                            f"🛑 Error: failed to build package '{self.name}'\n{e.stderr}",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    finally:
                        all_installed_binaries = self.all_installed_binaries()
                        for path in list(installed_binaries):
                            if path in all_installed_binaries:
                                print(
                                    f"⚠️ Warning: {self.name} modified {path}, which was installed by another package!",
                                    file=sys.stderr,
                                )
                                installed_binaries.remove(path)

                    if not installed:
                        installed["version"] = 1
                        installed["packages"] = {}

                    installed["packages"][self.name] = {}

                    if sha is not None:
                        installed["packages"][self.name]["sha"] = sha

                    libs = sorted(
                        str(path.relative_to(platform_path() / "lib"))
                        for path in installed_binaries
                        if path.is_relative_to(platform_path() / "lib")
                    )
                    if libs:
                        installed["packages"][self.name]["libs"] = libs

                    apps = sorted(
                        str(path.relative_to(platform_path() / "bin"))
                        for path in installed_binaries
                        if path.is_relative_to(platform_path() / "bin")
                    )
                    if apps:
                        installed["packages"][self.name]["apps"] = apps

                    if self.requested_dependencies():
                        installed["packages"][self.name]["requires"] = sorted(
                            dep.name for dep in self.requested_dependencies()
                        )

                    if isinstance(self.origin, Path):
                        installed["packages"][self.name]["origin"] = (
                            self.origin.as_uri()
                        )
                    elif isinstance(self.origin, str):
                        installed["packages"][self.name]["origin"] = self.origin

                    assert self.installed_binaries() == installed_binaries

                assert self.is_installed()
                assert self.installed_sha() == sha

                self._upgrade_available = False

                print(f"✅ Package '{self.name}' installed successfully.")

                if libs:
                    print("⚙️ New libraries:")
                    for lib in libs:
                        print(f"  {lib}")

                if apps:
                    print("🖥️ New applications:")
                    for app in apps:
                        print(f"  {app}")

            if isinstance(_deps, dict):
                _deps[self].set()

    async def uninstall(
        self,
        *,
        _force: bool = False,
        _keep_pkg: bool = False,
    ) -> None:
        if not _force:
            assert not _keep_pkg
            await self.uninstall_all({self})

        with lock as installed:
            if not self.is_installed():
                print(
                    f"⚠️ Warning: skipping package '{self.name}' as it is not installed.",
                    file=sys.stderr,
                )
                return

            with Status(f"⏳ Uninstalling {self.name}"):
                for path in self.installed_binaries():
                    with contextlib.suppress(FileNotFoundError):
                        path.unlink()

                if not _keep_pkg:
                    shutil.rmtree(
                        self._pkg_path,
                        ignore_errors=True,
                    )

                with contextlib.suppress(KeyError):
                    del installed["packages"][self.name]

        assert not self.is_installed()

        print(f"🗑️ Package '{self.name}' uninstalled successfully.")

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Package):
            return NotImplemented
        return self.name == other.name and self.origin == other.origin

    def __hash__(self) -> int:
        return hash((self.name, self.origin))


class _IndexedPackage(Package):
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

        new_sha = await fetch(self._pkg_path, self._metadata["repo"])
        if new_sha is None:
            self._upgrade_available = True
        else:
            self._upgrade_available = new_sha != self.installed_sha()

    async def download(self) -> str:
        assert self._metadata is not None
        if self.is_installed():
            title = f"⏩ Updating {self.name}"
        else:
            title = f"⏬ Downloading {self.name}"
        with Status(title):
            return await clone(self._pkg_path, self._metadata["repo"])


class _GitPackage(Package):
    def __init__(self, package: str) -> None:
        name, origin = Package.parse_package(package)

        if origin is None:
            assert name is not None
            with lock as installed:
                origin = installed["packages"][name]["origin"]

        assert origin.startswith(("http://", "https://"))

        if name is None:
            name = origin.rsplit("/", 1)[-1].split(".", 1)[0]

        super().__init__(name)
        self.origin = origin

    async def fetch(self) -> None:
        with Status(f"⏬ Downloading {self}"):
            assert isinstance(self.origin, str)
            new_sha = await fetch(self._pkg_path, self.origin, missing_ok=False)
        assert new_sha is not None
        branch = (
            await run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self._pkg_path,
            )
        ).stdout.strip()
        await run(["git", "checkout", new_sha], cwd=self._pkg_path)
        try:
            self._metadata = json.loads((self._pkg_path / "metadata.json").read_text())
        except FileNotFoundError:
            self._metadata = {}
        finally:
            await run(["git", "checkout", branch], cwd=self._pkg_path)
        self._upgrade_available = new_sha != self.installed_sha()

    async def download(self) -> str:
        assert isinstance(self.origin, str)
        return await clone(self._pkg_path, self.origin)

    def __str__(self) -> str:
        return f"{self.name} @ {self.origin}"


class _LocalPackage(Package):
    def __init__(self, package: str) -> None:
        name, origin = Package.parse_package(package)

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

    async def fetch(self) -> None:
        try:
            assert isinstance(self.origin, Path)
            self._metadata = json.loads((self.origin / "metadata.json").read_text())
        except FileNotFoundError:
            self._metadata = {}
        self._upgrade_available = True

    async def download(self) -> None:
        assert self._metadata is not None
        assert isinstance(self.origin, Path)
        shutil.rmtree(self._pkg_path, ignore_errors=True)
        self._pkg_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.origin,
            self._pkg_path,
        )

    def __str__(self) -> str:
        assert isinstance(self.origin, Path)
        return f"{self.name} @ {self.origin.as_uri()}"


class _Styro(Package):
    def __init__(self, package: str) -> None:
        assert package.lower() == "styro"
        super().__init__("styro")

    def is_installed(self) -> bool:
        return True

    async def resolve(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _resolved: set[Package] | None = None,
    ) -> set[Package]:
        if not upgrade and not _force_reinstall:
            return set()

        self._upgrade_available = await check_for_new_version(verbose=False)

        if not _force_reinstall and not self._upgrade_available:
            return set()

        if is_managed_installation():
            print(
                "🛑 Error: this is a managed installation of styro.",
                file=sys.stderr,
            )
            print_upgrade_instruction()
            sys.exit(1)

        return {self}

    async def install(
        self,
        *,
        upgrade: bool = False,
        _force_reinstall: bool = False,
        _deps: bool | dict[Package, asyncio.Event] = True,
    ) -> None:
        if not upgrade and not _force_reinstall:
            print(
                "✋ Package 'styro' is already installed.",
            )
            return

        if is_managed_installation():
            print(
                "🛑 Error: this is a managed installation of styro.",
                file=sys.stderr,
            )
            print_upgrade_instruction()
            sys.exit(1)

        self._upgrade_available = await check_for_new_version(verbose=False)

        if not _force_reinstall and not self._upgrade_available:
            print(
                "✋ Package 'styro' is already up-to-date.",
            )
            return

        await selfupgrade()

        print("✅ Package 'styro' upgraded successfully.")

    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        print(
            "🛑 Error: styro cannot be uninstalled this way.",
            file=sys.stderr,
        )
        if is_managed_installation():
            print(
                "💡 Use your package manager (e.g. pip) to uninstall styro.",
                file=sys.stderr,
            )
        else:
            print(
                "💡 Delete the 'styro' binary in $FOAM_USER_APPBIN to uninstall.",
                file=sys.stderr,
            )
        sys.exit(1)
