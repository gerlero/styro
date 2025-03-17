import os

import pytest
from typer.testing import CliRunner

from styro import __version__, app

runner = CliRunner()


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_porousmicrotransport() -> None:
    result = runner.invoke(app, ["install", "porousmicrotransport"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = runner.invoke(app, ["uninstall", "porousmicrotransport"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = runner.invoke(app, ["freeze"])
    assert result.exit_code == 0
    assert "porousmicrotransport" not in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "styro" in result.stdout
    assert __version__ in result.stdout
