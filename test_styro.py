import os
from pathlib import Path
from subprocess import run

import pytest
from typer.testing import CliRunner

from styro import __version__
from styro.__main__ import app

runner = CliRunner()


def test_styro() -> None:
    result = runner.invoke(app, ["install", "styro"])
    assert result.exit_code == 0
    assert "styro" in result.stdout

    result = runner.invoke(app, ["uninstall", "styro"])
    assert result.exit_code != 0
    assert "styro" in result.stdout


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_install(tmp_path: Path) -> None:
    result = runner.invoke(app, ["uninstall", "reagency"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = runner.invoke(app, ["install", "reagency"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    run(  # noqa: S603
        ["git", "clone", "https://github.com/gerlero/reagency.git"],  # noqa: S607
        cwd=tmp_path,
        check=True,
    )
    result = runner.invoke(app, ["install", str(tmp_path / "reagency")])
    assert result.exit_code == 0

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout
    assert (tmp_path / "reagency").as_uri() in result.stdout

    result = runner.invoke(app, ["install", "https://github.com/gerlero/reagency.git"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout
    assert "https://github.com/gerlero/reagency.git" in result.stdout

    result = runner.invoke(app, ["uninstall", "reagency"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" not in result.stdout


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_package_with_dependencies() -> None:
    result = runner.invoke(app, ["uninstall", "porousmicrotransport", "reagency"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = runner.invoke(app, ["install", "porousmicrotransport"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout
    assert "reagency" in result.stdout

    result = runner.invoke(app, ["uninstall", "reagency"])
    assert result.exit_code != 0
    assert "porousmicrotransport" in result.stdout
    assert "reagency" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "styro" in result.stdout
    assert __version__ in result.stdout
