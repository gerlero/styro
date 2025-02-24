from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import requests
import typer
from git import Repo

__version__ = "0.1.3"

app = typer.Typer()


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


def _check_version_compatibility(specs: list[str]) -> None:
    if not specs:
        return

    openfoam_version = int(os.environ["FOAM_API"])
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
def install(packages: list[str], *, upgrade: bool = False) -> None:
    """Install OpenFOAM packages from the OpenFOAM Package Index."""
    packages = [package.lower().replace("_", "-") for package in packages]

    platform_path = _platform_path()

    try:
        with (platform_path / "styro" / "installed.json").open() as f:
            installed = json.load(f)
            if installed.get("version") != 1:
                typer.echo(
                    "Error: manifest file is of a different version. Please upgrade styro.",
                    err=True,
                )
                raise typer.Exit(code=1)
    except FileNotFoundError:
        installed = {"version": 1, "packages": {}}

    repo_urls: list[str | None] = []
    builds: list[list[str] | None] = []
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
            typer.echo(f"Error: Failed to resolve package '{package}': {e}", err=True)
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
            typer.echo(f"Error: Failed to resolve package '{package}': {e}", err=True)
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
            assert build is None
            typer.echo(f"Package '{package}' is already installed.")
            continue

        typer.echo(f"Downloading {package}...")

        try:
            shutil.rmtree(platform_path / "styro" / "pkg" / package, ignore_errors=True)
            repo = Repo.clone_from(repo_url, platform_path / "styro" / "pkg" / package)
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

            shutil.rmtree(platform_path / "styro" / "pkg" / package, ignore_errors=True)

            del installed["packages"][package]

        typer.echo(f"Installing {package}...")

        try:
            current_apps = {f for f in (platform_path / "bin").iterdir() if f.is_file()}
        except FileNotFoundError:
            current_apps = set()

        try:
            current_libs = {f for f in (platform_path / "lib").iterdir() if f.is_file()}
        except FileNotFoundError:
            current_libs = set()

        for cmd in build:
            try:
                subprocess.run(  # noqa: S603
                    ["/bin/bash", "-c", cmd],
                    cwd=platform_path / "styro" / "pkg" / package,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                typer.echo(
                    f"Error: failed to build package '{package}'\n{e.stderr}", err=True
                )

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

                for app in new_apps:
                    with contextlib.suppress(FileNotFoundError):
                        app.unlink()

                for lib in new_libs:
                    with contextlib.suppress(FileNotFoundError):
                        lib.unlink()

                shutil.rmtree(
                    platform_path / "styro" / "pkg" / package, ignore_errors=True
                )

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

        with (platform_path / "styro" / "installed.json").open("w") as f:
            json.dump(installed, f, indent=4)

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
def uninstall(packages: list[str]) -> None:
    """Uninstall OpenFOAM packages."""
    packages = [package.lower().replace("_", "-") for package in packages]

    platform_path = _platform_path()

    try:
        with (platform_path / "styro" / "installed.json").open() as f:
            installed = json.load(f)
            if installed.get("version") != 1:
                typer.echo(
                    "Error: installed.json file is of a different version. Please upgrade styro.",
                    err=True,
                )
                raise typer.Exit(code=1)
    except FileNotFoundError:
        installed = {"version": 1, "packages": {}}

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

        with (platform_path / "styro" / "installed.json").open("w") as f:
            json.dump(installed, f, indent=4)

        typer.echo(f"Successfully uninstalled {package}.")


@app.command()
def freeze() -> None:
    """List installed OpenFOAM packages."""
    platform_path = _platform_path()

    try:
        with (platform_path / "styro" / "installed.json").open() as f:
            installed = json.load(f)
            if installed.get("version") != 1:
                typer.echo(
                    "Error: installed.json file is of a different version. Please upgrade styro.",
                    err=True,
                )
                raise typer.Exit(code=1)
    except FileNotFoundError:
        installed = {"version": 1, "packages": {}}

    for package in installed["packages"]:
        typer.echo(package)


if __name__ == "__main__":
    app()
