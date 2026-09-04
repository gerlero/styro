<div align="center">
  <a href="https://github.com/gerlero/styro"><img src="https://github.com/gerlero/styro/raw/main/logo.png" alt="styro" width="200"/></a>

  **The package manager for OpenFOAM**

  Simplify your OpenFOAM workflows with easy package installation, management, and distribution
</div>

<div align="center">

[![CI](https://github.com/gerlero/styro/actions/workflows/ci.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/gerlero/styro/branch/main/graph/badge.svg)](https://codecov.io/gh/gerlero/styro)
[![PyPI](https://img.shields.io/pypi/v/styro)](https://pypi.org/project/styro/)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/styro)](https://anaconda.org/conda-forge/styro)
![OpenFOAM](https://img.shields.io/badge/openfoam-.com%20|%20.org-informational)

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Publish](https://github.com/gerlero/styro/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/pypi-publish.yml)
[![Binaries](https://github.com/gerlero/styro/actions/workflows/binaries.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/binaries.yml)
[![Docker](https://github.com/gerlero/styro/actions/workflows/docker.yml/badge.svg)](https://github.com/gerlero/styro/actions/workflows/docker.yml)

</div>

---

## ✨ Why styro?

**styro** brings modern package management to the OpenFOAM ecosystem, making it easy to discover, install, and manage community-contributed packages. Whether you're a researcher, engineer, and/or developer, **styro** streamlines your workflow by eliminating manual compilation and dependency management.

### 🎯 Key benefits

- **🚀 One-command installation** - Install OpenFOAM packages with a single command
- **🌎 Community-driven** - Access packages from the [OpenFOAM Package Index (OPI)](https://github.com/exasim-project/opi)
- **🧩 Broad compatibility** - Works seamlessly with OpenFOAM from [openfoam.com](https://www.openfoam.com) and [openfoam.org](https://www.openfoam.org)
- **📦 Multiple sources** - Install from OPI, local directories, or Git repositories
- **🔄 Easy updates** - Upgrade packages with automatic dependency resolution
- **🛠️ Developer-friendly** - Simple package testing, definition and distribution


## ▶️ Demo

![Demo](https://github.com/gerlero/styro/raw/main/demo.gif)


## 📋 Requirements

**styro** works with OpenFOAM (from either [openfoam.com](https://www.openfoam.com) or [openfoam.org](https://www.openfoam.org)).


## ⏬ Installation

Choose any of the following methods:

* With [pip](https://pypi.org/project/pip/) (requires Python 3.9 or later):

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
    /bin/bash -c "$(curl https://raw.githubusercontent.com/gerlero/styro/main/install.sh)"
    ```

* [Docker](https://www.docker.com) image:

    ```bash
    docker pull microfluidica/styro
    ```


## 🧑‍💻 Command reference

| Command | Description | Example |
|---------|-------------|---------|
| ⏬ `styro install <packages>` | Install one or more packages | `styro install cfmesh` |
| ⬆️ `styro install --upgrade <packages>` | Upgrade already installed packages | `styro install --upgrade cfmesh` |
| 🗑️ `styro uninstall <packages>` | Remove installed packages | `styro uninstall cfmesh` |
| 🔍 `styro freeze` | List all installed packages | `styro freeze` |
| 🔄 `styro install --upgrade styro` | Upgrade **styro** itself (only for standalone installs) | `styro install --upgrade styro` |


## 📦 Package sources

### ✨ OpenFOAM Package Index (OPI)

**styro** automatically discovers packages from the community-maintained [OpenFOAM Package Index](https://github.com/exasim-project/opi).

```bash
styro install cfmesh
```

### 🖥️ Local packages

Install packages from your local filesystem:

```bash
styro install /path/to/my-custom-package
```

**Pro tip:** Add a [`metadata.json`](https://github.com/exasim-project/opi/blob/main/metadata.json) file to the package directory to customize installation behavior.

### 🌎 Git repositories

Install directly from any Git repository:

```bash
styro install https://github.com/username/my-openfoam-package.git
```

Just like local packages, add a `metadata.json` file to the repository root for custom installation settings.


## 🤝 Contributing

We welcome contributions! Here's how you can help:

- **📦 Add packages** to the [OpenFOAM Package Index](https://github.com/exasim-project/opi)
- **🐛 Report bugs** or request features via [GitHub Issues](https://github.com/gerlero/styro/issues)
- **🔧 Submit pull requests** to improve styro itself
