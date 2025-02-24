# 📦 `styro`: A package manager for OpenFOAM

| ‼️ This project is still at the proof-of-concept stage. Please try it at your own risk! |
| ---- |


[![CI](https://github.com/gerlero/styro/actions/workflows/ci.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/ci.yml)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Publish](https://github.com/gerlero/styro/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/pypi-publish.yml)
[![PyPI](https://img.shields.io/pypi/v/styro)](https://pypi.org/project/styro/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/styro)](https://pypi.org/project/styro/)
![OpenFOAM](https://img.shields.io/badge/openfoam-.com%20|%20.org-informational)


## Installation

```bash
pip install styro
```

**styro** requires OpenFOAM, Python 3.7 or later, and Git.


## Available commands
- ```styro install <packages>```: Install a package or packages (pass `--upgrade` to upgrade already installed packages)
- ```styro uninstall <packages>```: Uninstall a package or packages
- ```styro freeze```: List installed packages


## Available packages

**styro** is able to install packages listed in the [OpenFOAM Package Index (OPI)](https://github.com/exasim-project/opi).


## Major TODO list

- Enforce OpenFOAM version constraints
- Add CMake support
- Add locking to allow concurrent operations
- Add tests
