from __future__ import annotations

import typer

from . import _Package

app = typer.Typer()


@app.command()
def install(packages: list[str]) -> None:
    """Install OpenFOAM packages from the OpenFOAM Package Index."""
    errors = False
    for package in packages:
        pkg = _Package(package)

        try:
            typer.echo(f"Downloading {pkg.name}...")
            pkg.download()

            typer.echo(f"Installing {pkg.name}...")
            pkg.install()

            typer.echo(f"Package '{pkg.name}' installed successfully.")
            new_libs = pkg.installed_libs
            if new_libs:
                typer.echo(f"Installed libs: {' '.join(new_libs)}")
            new_apps = pkg.installed_apps
            if new_apps:
                typer.echo(f"Installed apps: {' '.join(new_apps)}")
        except (ValueError, RuntimeError) as e:
            typer.echo(f"Error installing package '{pkg.name}': {e}")
            errors = True

    if errors:
        raise typer.Exit(code=1)


@app.command()
def uninstall(packages: list[str]) -> None:
    """Uninstall OpenFOAM packages."""
    errors = False
    for package in packages:
        pkg = _Package(package)

        try:
            typer.echo(f"Uninstalling {pkg.name}...")
            pkg.uninstall()

            typer.echo(f"Package '{pkg.name}' uninstalled successfully.")
        except (ValueError, RuntimeError) as e:
            typer.echo(f"Error uninstalling package '{pkg.name}': {e}")
            errors = True

    if errors:
        raise typer.Exit(code=1)


@app.command()
def freeze() -> None:
    """List installed OpenFOAM packages."""
    for pkg in _Package.installed_packages():
        typer.echo(pkg)
