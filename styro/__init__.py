from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import requests
from git import Repo

__version__ = "0.1.1"


try:
    _APPBIN_PATH = Path(os.environ["FOAM_USER_APPBIN"])
    _LIBBIN_PATH = Path(os.environ["FOAM_USER_LIBBIN"])
except KeyError as e:
    msg = "No OpenFOAM environment found. Please activate (source) the OpenFOAM environment first."
    raise RuntimeError(msg) from e

assert _APPBIN_PATH.parent == _LIBBIN_PATH.parent

_PLATFORM_PATH = _APPBIN_PATH.parent
_STYRO_PATH = _PLATFORM_PATH / "styro"
_PKG_PATH = _STYRO_PATH / "pkg"
_MANIFEST_PATH = _STYRO_PATH / "installed.json"


class _Package:
    def __init__(self, name: str) -> None:
        self.name = name.lower().replace("_", "-")

    @property
    def _metadata(self) -> dict:
        response = requests.get(
            f"https://raw.githubusercontent.com/exasim-project/opi/refs/heads/main/pkg/{self.name}/metadata.json",
            timeout=10,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:  # noqa: PLR2004
                msg = f"Package '{self.name}' not found in the OpenFOAM package index. See https://github.com/exasim-project/opi for more information."
                raise ValueError(msg) from e
            raise

        return response.json()

    @staticmethod
    def installed_packages() -> list[str]:
        try:
            with _MANIFEST_PATH.open() as f:
                manifest = json.load(f)
        except FileNotFoundError:
            return []

        if manifest["version"] > 1:
            msg = "The installed package manifest is of a newer version. Please update styro."
            raise RuntimeError(msg)

        return list(manifest["packages"].keys())

    @property
    def _install_data(self) -> dict | None:
        try:
            with _MANIFEST_PATH.open() as f:
                manifest = json.load(f)
        except FileNotFoundError:
            return None

        if manifest["version"] > 1:
            msg = "The installed package manifest is of a newer version. Please update styro."
            raise RuntimeError(msg)

        return manifest["packages"].get(self.name)

    @_install_data.setter
    def _install_data(self, data: dict | None) -> None:
        try:
            with _MANIFEST_PATH.open() as f:
                manifest = json.load(f)
        except FileNotFoundError:
            manifest = {"version": 1, "packages": {}}

        if data is None:
            del manifest["packages"][self.name]
        else:
            manifest["packages"][self.name] = data

        with _MANIFEST_PATH.open("w") as f:
            json.dump(manifest, f, indent=4)

    @property
    def is_installed(self) -> bool:
        return self._install_data is not None

    @property
    def installed_apps(self) -> list[str]:
        install_data = self._install_data
        if install_data is None:
            return []
        return install_data["apps"]

    @property
    def installed_libs(self) -> list[str]:
        install_data = self._install_data
        if install_data is None:
            return []
        return install_data["libs"]

    def download(self) -> None:
        if self.is_installed:
            msg = f"Package '{self.name}' is already installed. Uninstall it first."
            raise RuntimeError(msg)

        repo_url = self._metadata["repo"]
        if "://" not in repo_url:
            repo_url = "https://" + repo_url
        if not repo_url.endswith(".git"):
            repo_url += ".git"

        repo_path = _PKG_PATH / self.name

        shutil.rmtree(repo_path, ignore_errors=True)
        Repo.clone_from(repo_url, repo_path)

    def install(self) -> None:
        if self.is_installed:
            msg = f"Package '{self.name}' is already installed. Uninstall it first."
            raise RuntimeError(msg)

        repo_path = _PKG_PATH / self.name
        if not repo_path.is_dir():
            msg = f"Package '{self.name}' is not downloaded. Download it first."
            raise RuntimeError(msg)

        sha = Repo(repo_path).head.object.hexsha

        build = self._metadata.get("build", "wmake")
        if build == "wmake":
            build = ["wmake all -j"]
        elif build == "cmake":
            msg = f"CMake build system required by package '{self.name}' is not supported yet."
            raise NotImplementedError(msg)

        try:
            current_apps = {f for f in _APPBIN_PATH.iterdir() if f.is_file()}
        except FileNotFoundError:
            current_apps = set()

        try:
            current_libs = {f for f in _LIBBIN_PATH.iterdir() if f.is_file()}
        except FileNotFoundError:
            current_libs = set()

        try:
            for cmd in self._metadata.get("build", ["wmake all -j"]):
                subprocess.run(  # noqa: S603
                    ["/bin/bash", "-c", cmd],
                    cwd=repo_path,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
        except subprocess.CalledProcessError as e:
            msg = f"Failed to build package '{self.name}'.\n{e.stderr}"
            raise RuntimeError(msg) from e

        new_apps = sorted(
            f for f in _APPBIN_PATH.iterdir() if f.is_file() and f not in current_apps
        )
        new_libs = sorted(
            f for f in _LIBBIN_PATH.iterdir() if f.is_file() and f not in current_libs
        )

        self._install_data = {
            "sha": sha,
            "apps": [f.name for f in new_apps],
            "libs": [f.stem for f in new_libs],
        }

    def uninstall(self) -> None:
        if self.is_installed:
            for app in self.installed_apps:
                app_path = _APPBIN_PATH / app
                if app_path.is_file():
                    app_path.unlink()

            for lib in self.installed_libs:
                lib_path = _LIBBIN_PATH / lib
                if lib_path.is_file():
                    lib_path.unlink()

            self._install_data = None

        repo_path = _PKG_PATH / self.name
        shutil.rmtree(repo_path, ignore_errors=True)
