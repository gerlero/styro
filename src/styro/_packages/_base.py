import asyncio
import contextlib
import os
import re
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import aioshutil

from styro._openfoam import get_changed_binaries, openfoam_version, platform_path
from styro._packages._lock import lock
from styro._utils.status import Status
from styro._utils.subprocess import run

if TYPE_CHECKING:
    from styro._packages._self import Styro

_NAME_REGEX = re.compile(r"^(?!.*--)[a-z0-9]+(-[a-z0-9]+)*$")
_install_lock = asyncio.Lock()


def _check_for_duplicate_names(pkgs: set["Package"], /) -> None:
    duplicate_names = {
        pkg.name for pkg in pkgs if len([p for p in pkgs if p.name == pkg.name]) > 1
    }
    if duplicate_names:
        print(
            f"🛑 Error: duplicate/conflicting package names: {', '.join(duplicate_names)}",
            file=sys.stderr,
        )
        sys.exit(1)


async def _detect_cycles(pkgs: set["Package"], /, *, upgrade: bool = False) -> None:
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
        pkg: "Package",
        /,
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


def _all_installed_binaries() -> set[Path]:
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


class Package:
    @staticmethod
    def _parse_package_str(
        package: str, /
    ) -> tuple[str, None] | tuple[None, str] | tuple[str, str]:
        name = package.lower().replace("_", "-")
        if _NAME_REGEX.fullmatch(name):
            return name, None
        if "@" in package:
            name, origin = package.split("@", 1)
            name = name.rstrip().lower().replace("_", "-")
            origin = origin.lstrip()
            if _NAME_REGEX.fullmatch(name):
                return name, origin
            print(
                f"🛑 Error: Invalid package name: {name}",
                file=sys.stderr,
            )
            sys.exit(1)
        return None, package

    @staticmethod
    def all_installed() -> set["Package"]:
        with lock as installed:
            return {Package(name) for name in installed.get("packages", {})}

    @staticmethod
    @lock
    async def resolve_all(
        pkgs: set["Package"],
        /,
        *,
        upgrade: bool = False,
    ) -> set["Package"]:
        _check_for_duplicate_names(pkgs)

        # Detect cycles before attempting resolution
        await _detect_cycles(pkgs, upgrade=upgrade)

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
    async def install_all(pkgs: set["Package"], /, *, upgrade: bool = False) -> None:
        to_install = {
            pkg: asyncio.Event()
            for pkg in await Package.resolve_all(pkgs, upgrade=upgrade)
        }

        not_to_install = pkgs.difference(to_install)

        _check_for_duplicate_names(set(to_install).union(not_to_install))

        await asyncio.gather(
            *(pkg.install(upgrade=upgrade, _deps=False) for pkg in not_to_install),
            *(
                pkg.install(_force_reinstall=True, _deps=to_install)
                for pkg in to_install
            ),
        )

    @staticmethod
    @lock
    async def uninstall_all(pkgs: set["Package"], /) -> None:
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

    @overload
    def __new__(cls, package: Literal["styro"], /) -> "Styro": ...

    @overload
    def __new__(cls, package: str, /) -> "Package": ...

    def __new__(cls, package: str, /) -> "Package":  # noqa: PYI034
        if cls is not Package:
            return super().__new__(cls)

        name, origin = Package._parse_package_str(package)

        if name == "styro":
            from styro._packages._self import Styro

            return super().__new__(Styro)

        with lock as installed:
            if name is not None and origin is None:
                with contextlib.suppress(KeyError):
                    origin = installed["packages"][name]["origin"]

            if origin is not None:
                if origin.startswith(("http://", "https://")):
                    from styro._packages._git import GitPackage

                    return super().__new__(GitPackage)
                from styro._packages._local import LocalPackage

                return super().__new__(LocalPackage)

            from styro._packages._indexed import IndexedPackage

            return super().__new__(IndexedPackage)

    def __init__(self, name: str, /) -> None:
        if not _NAME_REGEX.fullmatch(name):
            print(
                f"🛑 Error: Invalid package name: {name}",
                file=sys.stderr,
            )
            sys.exit(1)

        from styro._packages._self import Styro

        if name == "styro" and not isinstance(self, Styro):
            print(
                "🛑 Error: 'styro' not allowed as a package name.",
                file=sys.stderr,
            )
            sys.exit(1)
        self.name = name
        self.origin: str | Path | None = None
        self._metadata: dict[str, Any] | None = None
        self._fetched_sha: str | None = None
        self._upgrade_available = False

    def __build_steps(self) -> list[str]:
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

    def __check_compatibility(self) -> None:
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

            if (openfoam_version() < 1000) == (version < 1000):
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
        _resolved: set["Package"] | None = None,
    ) -> set["Package"]:
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
            self.__check_compatibility()
            self.__build_steps()

        if (
            self.installed_sha() is not None
            and not self._upgrade_available
            and not _force_reinstall
        ):
            return set()

        ret: set[Package] = {self}

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

    def requested_dependencies(self) -> set["Package"]:
        assert self._metadata is not None
        return {Package(name) for name in self._metadata.get("requires", [])}

    def installed_dependents(self) -> set["Package"]:
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
        _deps: bool | dict["Package", asyncio.Event] = True,
    ) -> None:
        from styro._packages._local import LocalPackage

        with lock as installed:
            if _deps is True:
                await self.install_all({self}, upgrade=upgrade)
                return

            if (
                self.is_installed()
                and not isinstance(self, LocalPackage)
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
                self.__check_compatibility()

            if (
                self.is_installed()
                and not isinstance(self, LocalPackage)
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

            async with _install_lock:
                with Status(f"⏳ Installing {self.name}") as status:
                    if self.requested_dependencies():
                        env = os.environ.copy()
                        env["OPI_DEPENDENCIES"] = str(self._pkg_path.parent)
                    else:
                        env = None

                    try:
                        with get_changed_binaries() as installed_binaries:
                            for cmd in self.__build_steps():
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
                        all_installed_binaries = _all_installed_binaries()
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
                    await aioshutil.rmtree(self._pkg_path, ignore_errors=True)

                with contextlib.suppress(KeyError):
                    del installed["packages"][self.name]

        assert not self.is_installed()

        print(f"🗑️ Package '{self.name}' uninstalled successfully.")

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def __eq__(self, other: object, /) -> bool:
        if not isinstance(other, Package):
            return NotImplemented
        return self.name == other.name and self.origin == other.origin

    @override
    def __hash__(self) -> int:
        return hash((self.name, self.origin))
