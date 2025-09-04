<div align="center">
  <img src="https://github.com/gerlero/styro/raw/main/logo.png" alt="styro" width="200"/>
  
  # styro
  
  **🌊 A modern, community-driven package manager for OpenFOAM**
  
  *Simplify your OpenFOAM workflow with easy package installation, management, and distribution*
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

</div>

---

## ✨ Why styro?

**styro** brings modern package management to the OpenFOAM ecosystem, making it easy to discover, install, and manage community-contributed packages. Whether you're a researcher, engineer, or developer, styro streamlines your workflow by eliminating manual compilation and dependency management.

### 🎯 Key Benefits

- **🚀 One-command installation** - Install complex OpenFOAM packages with a single command
- **🌍 Community-driven** - Access packages from the [OpenFOAM Package Index (OPI)](https://github.com/exasim-project/opi)
- **🔄 Version management** - Easy upgrades and dependency resolution
- **📦 Multiple sources** - Install from OPI, local directories, or Git repositories
- **🛠️ Developer-friendly** - Simple package creation and distribution

## 🚀 Quick Start

```bash
# Install styro
pip install styro

# Install a package from the OpenFOAM Package Index
styro install OpenQBMM

# Install from a Git repository
styro install https://github.com/gerlero/reagency.git

# List installed packages
styro freeze

# Upgrade a package
styro install --upgrade OpenQBMM
```

## ▶️ Demo

![Demo](https://github.com/gerlero/styro/raw/main/demo.gif)

## 📋 Requirements

Before using **styro**, ensure you have:

- **OpenFOAM** (from [openfoam.com](https://www.openfoam.com) or [openfoam.org](https://www.openfoam.org))
- **Git** (for repository-based installations)
- **Python 3.8+** (if installing via pip or conda)

## ⏬ Installation

### 🐍 Python Package Managers

<details>
<summary><strong>pip</strong> (recommended)</summary>

```bash
pip install styro
```
*Requires Python 3.8 or later*
</details>

<details>
<summary><strong>conda</strong></summary>

```bash
conda install -c conda-forge styro
```
</details>

### 🍺 System Package Managers

<details>
<summary><strong>Homebrew (macOS/Linux)</strong></summary>

```bash
brew install gerlero/openfoam/styro
```
</details>

### 📦 Standalone Binary

Perfect for use in containers or when you don't want Python dependencies:

```bash
/bin/sh -c "$(curl https://raw.githubusercontent.com/gerlero/styro/main/install.sh)"
```

*Installs to `$FOAM_USER_APPBIN`*


## 🧑‍💻 Command Reference

| Command | Description | Example |
|---------|-------------|---------|
| `styro install <packages>` | Install one or more packages | `styro install OpenQBMM swak4Foam` |
| `styro install --upgrade <packages>` | Upgrade already installed packages | `styro install --upgrade OpenQBMM` |
| `styro uninstall <packages>` | Remove installed packages | `styro uninstall OpenQBMM` |
| `styro freeze` | List all installed packages | `styro freeze` |


## 📦 Package Sources

### ✨ OpenFOAM Package Index (OPI)

**styro** automatically discovers packages from the community-maintained [OpenFOAM Package Index](https://github.com/exasim-project/opi).

**Popular packages include:**
- `OpenQBMM` - Quadrature-based moment methods
- `swak4Foam` - Swiss Army Knife for OpenFOAM
- `cfMesh` - Library for mesh generation
- `DAFoam` - Discrete adjoint solver

<details>
<summary>View all available packages</summary>

Browse the complete catalog at: https://github.com/exasim-project/opi/tree/main/pkg

```bash
# Install any indexed package by name
styro install <package-name>
```
</details>

### 🖥️ Local Packages

Install packages from your local filesystem:

```bash
styro install /path/to/my-custom-package
```

**Pro tip:** Add a [`metadata.json`](https://github.com/exasim-project/opi/blob/main/metadata.json) file to customize installation behavior.

### 🌎 Git Repositories

Install directly from any Git repository:

```bash
# From GitHub
styro install https://github.com/username/my-openfoam-package.git

# From GitLab
styro install https://gitlab.com/username/my-package.git

# With specific branch/tag
styro install https://github.com/username/package.git@v1.2.3
```

Just like local packages, add a `metadata.json` file to the repository root for custom installation settings.

---

## 🛠️ Troubleshooting

<details>
<summary><strong>Common Issues</strong></summary>

**Package not found**
```bash
# Make sure OpenFOAM environment is loaded
source /path/to/openfoam/etc/bashrc

# Check package name spelling
styro freeze  # lists installed packages
```

**Installation fails**
- Ensure you have write permissions to the OpenFOAM installation directory
- Check that Git is installed and accessible
- Verify OpenFOAM environment variables are set correctly

**Python/pip issues**
```bash
# Try installing in user mode
pip install --user styro

# Or use conda instead
conda install -c conda-forge styro
```

</details>

## 🤝 Contributing

We welcome contributions! Here's how you can help:

- **📦 Add packages** to the [OpenFOAM Package Index](https://github.com/exasim-project/opi)
- **🐛 Report bugs** or request features via [GitHub Issues](https://github.com/gerlero/styro/issues)
- **🔧 Submit pull requests** to improve styro itself
- **📝 Improve documentation** and help others in discussions

## 📚 Learn More

- **📖 Documentation:** [OpenFOAM Package Index](https://github.com/exasim-project/opi)
- **💬 Discussions:** [GitHub Discussions](https://github.com/gerlero/styro/discussions)
- **🐛 Issues:** [Bug Reports & Feature Requests](https://github.com/gerlero/styro/issues)
- **📧 Contact:** ggerlero@cimec.unl.edu.ar

---

<div align="center">
  <strong>Made with ❤️ for the OpenFOAM community</strong>
  <br>
  <em>Star ⭐ this repository if styro helps your workflow!</em>
</div>
