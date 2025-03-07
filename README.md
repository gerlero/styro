# 🏗️ `styro`: A community package manager for OpenFOAM

[![CI](https://github.com/gerlero/styro/actions/workflows/ci.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/gerlero/styro/branch/main/graph/badge.svg)](https://codecov.io/gh/gerlero/styro)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Publish](https://github.com/gerlero/styro/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/pypi-publish.yml)
[![PyPI](https://img.shields.io/pypi/v/styro)](https://pypi.org/project/styro/)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/styro)](https://anaconda.org/conda-forge/styro)
[![Binaries](https://github.com/gerlero/styro/actions/workflows/binaries.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/binaries.yml)
![OpenFOAM](https://img.shields.io/badge/openfoam-.com%20|%20.org-informational)


## ⏬ Installation

Choose any of the following methods:

* With [pip](https://pypi.org/project/pip/) (requires Python 3.7 or later):

    ```bash
    pip install styro
    ```

* With [conda](https://docs.conda.io/en/latest/):

    ```bash
    conda install -c conda-forge styro
    ```

* With [Homebrew](https://brew.sh/):

    ```bash
    brew install gerlero/openfoam/styro
    ```

* Standalone binary (installs to `$FOAM_USER_APPBIN`):

    ```bash
    /bin/sh -c "$(curl https://raw.githubusercontent.com/gerlero/styro/main/install.sh)"
    ```

To actually install packages, **styro** needs OpenFOAM (from either [openfoam.com](https://www.openfoam.com) or [openfoam.org](https://www.openfoam.org)) and [Git](https://www.openfoam.com/download/git).


## ✅ Available commands
- ```styro install <packages>```: Install a package or packages (pass `--upgrade` to upgrade already installed packages)
- ```styro uninstall <packages>```: Uninstall a package or packages
- ```styro freeze```: List installed packages


## 📦 Available packages

**styro** is able to install community packages listed in the [OpenFOAM Package Index (OPI)](https://github.com/exasim-project/opi).
