"""A community package manager for OpenFOAM."""

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

if sys.version_info >= (3, 9):
    from collections.abc import Generator
else:
    from typing import Generator

import requests
import typer
from git import Repo

__version__ = "0.1.10"

app = typer.Typer(help=__doc__)


def _platform_path() -> Path:
    try:
        app_path = Path(os.environ["FOAM_USER_APPBIN"])
        lib_path = Path(os.environ["FOAM_USER_LIBBIN"])
    except KeyError as e:
        typer.echo(
            "Error: No OpenFOAM environment found. Please activate (source) the OpenFOAM environment first.",
            err=True,
        )
        raise typer.Exit(code=1) from e

    assert app_path.parent == lib_path.parent
    platform_path = app_path.parent

    assert app_path == platform_path / "bin"
    assert lib_path == platform_path / "lib"

    return platform_path


@contextlib.contextmanager
def _installed(*, write: bool = False) -> Generator[dict, None, None]:
    platform_path = _platform_path()

    installed_path = platform_path / "styro" / "installed.json"

    installed_path.parent.mkdir(parents=True, exist_ok=True)
    installed_path.touch(exist_ok=True)
    with installed_path.open("r+" if write else "r") as f:
        fcntl.flock(f, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        if f.seek(0, os.SEEK_END) == 0:
            installed = {"version": 1, "packages": {}}
        else:
            f.seek(0)
            installed = json.load(f)

        if installed.get("version") != 1:
            typer.echo(
                "Error: installed.json file is of a newer version. Please upgrade styro.",
                err=True,
            )
            raise typer.Exit(code=1)

        try:
            yield installed
        finally:
            if write:
                f.seek(0)
                json.dump(installed, f, indent=4)
                f.truncate()


def _check_version_compatibility(specs: List[str]) -> None:
    if not specs:
        return

    openfoam_version_str = os.environ["WM_PROJECT_VERSION"]
    if openfoam_version_str.startswith("v"):
        openfoam_version = int(openfoam_version_str[1:])
    else:
        openfoam_version = int(openfoam_version_str)
    distro_compatibility = False

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
                    f"Warning: Ignoring invalid version specifier '{spec}'.", err=True
                )
                continue
        except ValueError:
            typer.echo(
                f"Warning: Ignoring invalid version specifier '{spec}'.", err=True
            )
            continue

        if (openfoam_version < 1000) == (version < 1000):  # noqa: PLR2004
            distro_compatibility = True

            if not compatible:
                typer.echo(
                    f"Error: OpenFOAM version is {openfoam_version}, but package requires {spec}.",
                    err=True,
                )

    if not distro_compatibility:
        typer.echo(
            f"Error: Package is not compatible with this OpenFOAM distribution (requires {specs}).",
            err=True,
        )


@app.command()
def install(packages: List[str], *, upgrade: bool = False) -> None:
    """Install OpenFOAM packages from the OpenFOAM Package Index."""
    packages = [package.lower().replace("_", "-") for package in packages]
    platform_path = _platform_path()

    with _installed(write=True) as installed:
        repo_urls: List[Optional[str]] = []
        builds: List[Optional[str]] = []
        for package in packages:
            typer.echo(f"Resolving {package}...")

            if package in installed["packages"] and not upgrade:
                repo_urls.append(None)
                builds.append(None)
                continue

            try:
                response = requests.get(
                    f"https://raw.githubusercontent.com/exasim-project/opi/refs/heads/main/pkg/{package}/metadata.json",
                    timeout=10,
                )
            except Exception as e:
                typer.echo(
                    f"Error: Failed to resolve package '{package}': {e}", err=True
                )
                raise typer.Exit(code=1) from e

            if response.status_code == 404:  # noqa: PLR2004
                typer.echo(
                    f"Error: Package '{package}' not found in the OpenFOAM Package Index (OPI).\nSee https://github.com/exasim-project/opi for more information.",
                    err=True,
                )
                raise typer.Exit(code=1)

            try:
                response.raise_for_status()

                metadata = response.json()

                _check_version_compatibility(metadata.get("version", []))

                repo_url = metadata["repo"]
                if "://" not in repo_url:
                    repo_url = f"https://{repo_url}"
                if not repo_url.endswith(".git"):
                    repo_url += ".git"

                repo_urls.append(repo_url)

                build = metadata.get("build", "wmake")
            except Exception as e:
                typer.echo(
                    f"Error: Failed to resolve package '{package}': {e}", err=True
                )
                raise typer.Exit(code=1) from e

            if build == "wmake":
                build = ["wmake all -j"]
            elif build == "cmake":
                typer.echo(
                    f"Error: CMake build system (required by {package}) is not supported yet.",
                    err=True,
                )
                raise typer.Exit(code=1)

            builds.append(build)

        typer.echo(f"Successfully resolved {len(repo_urls)} package(s).")

        for package, repo_url, build in zip(packages, repo_urls, builds):
            if repo_url is None:
                assert not upgrade
                assert build is None
                typer.echo(f"Package '{package}' is already installed.")
                continue

            pkg_path = platform_path / "styro" / "pkg" / package
            try:
                repo = Repo(pkg_path)
                if repo.remotes.origin.url != repo_url:
                    repo.remote("origin").set_url(repo_url)
                default_branch = repo.remotes.origin.refs[0].name.split("/")[-1]
                repo.git.checkout(default_branch)
                repo.remotes.origin.fetch()
                repo.git.reset("--hard", f"origin/{default_branch}")
                typer.echo(f"Updating {package}...")
                repo.git.pull()
            except Exception:  # noqa: BLE001
                try:
                    shutil.rmtree(pkg_path, ignore_errors=True)
                    typer.echo(f"Downloading {package}...")
                    repo = Repo.clone_from(repo_url, pkg_path)
                except Exception as e:
                    typer.echo(f"Error downloading package '{package}': {e}")
                    raise typer.Exit(code=1) from e

            if package in installed["packages"]:
                assert upgrade
                if repo.head.commit.hexsha == installed["packages"][package]["sha"]:
                    typer.echo(f"Package '{package}' is already up-to-date.")
                    continue

                typer.echo(f"Uninstalling {package}...")

                for app in installed["packages"][package]["apps"]:
                    with contextlib.suppress(FileNotFoundError):
                        (platform_path / "bin" / app).unlink()

                for lib in installed["packages"][package]["libs"]:
                    with contextlib.suppress(FileNotFoundError):
                        (platform_path / "lib" / lib).unlink()

                shutil.rmtree(pkg_path, ignore_errors=True)

                del installed["packages"][package]

            typer.echo(f"Installing {package}...")

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
                    for f in (platform_path / "bin").iterdir()
                    if f.is_file()
                }
            except FileNotFoundError:
                current_apps = {}
            try:
                current_libs = {
                    f: f.stat().st_mtime
                    for f in (platform_path / "lib").iterdir()
                    if f.is_file()
                }
            except FileNotFoundError:
                current_libs = {}

            for cmd in build:
                try:
                    subprocess.run(  # noqa: S603
                        ["/bin/bash", "-c", cmd],
                        cwd=pkg_path,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except subprocess.CalledProcessError as e:
                    typer.echo(
                        f"Error: failed to build package '{package}'\n{e.stderr}",
                        err=True,
                    )

                    try:
                        new_apps = sorted(
                            f
                            for f in (platform_path / "bin").iterdir()
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
                            for f in (platform_path / "lib").iterdir()
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

                    shutil.rmtree(pkg_path, ignore_errors=True)

                    raise typer.Exit(code=1) from e

            try:
                new_apps = sorted(
                    f
                    for f in (platform_path / "bin").iterdir()
                    if f.is_file() and f not in current_apps
                )
            except FileNotFoundError:
                new_apps = []

            try:
                new_libs = sorted(
                    f
                    for f in (platform_path / "lib").iterdir()
                    if f.is_file() and f not in current_libs
                )
            except FileNotFoundError:
                new_libs = []

            assert package not in installed["packages"]

            installed["packages"][package] = {
                "sha": repo.head.commit.hexsha,
                "apps": [app.name for app in new_apps],
                "libs": [lib.name for lib in new_libs],
            }

            typer.echo(f"Package '{package}' installed successfully.")

            if new_libs:
                typer.echo("New libraries:")
                for lib in new_libs:
                    typer.echo(f"  {lib.name}")

            if new_apps:
                typer.echo("New applications:")
                for app in new_apps:
                    typer.echo(f"  {app.name}")


@app.command()
def uninstall(packages: List[str]) -> None:
    """Uninstall OpenFOAM packages."""
    packages = [package.lower().replace("_", "-") for package in packages]
    platform_path = _platform_path()

    with _installed(write=True) as installed:
        for package in packages:
            if package not in installed["packages"]:
                typer.echo(
                    f"Warning: skipping package '{package}' as it is not installed.",
                    err=True,
                )
                continue

            typer.echo(f"Uninstalling {package}...")
            for app in installed["packages"][package]["apps"]:
                with contextlib.suppress(FileNotFoundError):
                    (platform_path / "bin" / app).unlink()

            for lib in installed["packages"][package]["libs"]:
                with contextlib.suppress(FileNotFoundError):
                    (platform_path / "lib" / lib).unlink()

            shutil.rmtree(platform_path / "styro" / "pkg" / package, ignore_errors=True)

            del installed["packages"][package]

            typer.echo(f"Successfully uninstalled {package}.")


@app.command()
def freeze() -> None:
    """List installed OpenFOAM packages."""
    with _installed() as installed:
        for package in installed["packages"]:
            typer.echo(package)


if __name__ == "__main__":
    app()
