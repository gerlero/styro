import os
from pathlib import Path
from subprocess import run
from io import StringIO
import sys
from contextlib import redirect_stdout, redirect_stderr

import pytest

from styro import __version__
from styro.__main__ import app


class CycloptsTestResult:
    """Simple test result class to mimic typer.testing.Result"""
    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout 
        self.stderr = stderr


def invoke_app(app_instance, args):
    """Simple test runner for cyclopts apps"""
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    exit_code = 0
    
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            app_instance(args)
    except SystemExit as e:
        exit_code = e.code if e.code is not None else 0
    except Exception:
        exit_code = 1
        
    return CycloptsTestResult(
        exit_code=exit_code,
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue()
    )


def test_styro() -> None:
    result = invoke_app(app, ["install", "styro"])
    assert result.exit_code == 0
    assert "styro" in result.stdout

    result = invoke_app(app, ["uninstall", "styro"])
    assert result.exit_code != 0
    assert "styro" in result.stdout


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_install(tmp_path: Path) -> None:
    result = invoke_app(app, ["uninstall", "reagency"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = invoke_app(app, ["install", "reagency"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = invoke_app(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    run(
        ["git", "clone", "https://github.com/gerlero/reagency.git"],  # noqa: S607
        cwd=tmp_path,
        check=True,
    )
    result = invoke_app(app, ["install", str(tmp_path / "reagency")])
    assert result.exit_code == 0

    result = invoke_app(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout
    assert (tmp_path / "reagency").as_uri() in result.stdout

    result = invoke_app(app, ["install", "https://github.com/gerlero/reagency.git"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = invoke_app(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout
    assert "https://github.com/gerlero/reagency.git" in result.stdout

    result = invoke_app(app, ["uninstall", "reagency"])
    assert result.exit_code == 0
    assert "reagency" in result.stdout

    result = invoke_app(app, ["freeze"])
    assert result.exit_code == 0
    assert "reagency" not in result.stdout


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_package_with_dependencies() -> None:
    result = invoke_app(app, ["uninstall", "porousmicrotransport", "reagency"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = invoke_app(app, ["install", "porousmicrotransport"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout

    result = invoke_app(app, ["freeze"])
    assert result.exit_code == 0
    assert "porousmicrotransport" in result.stdout
    assert "reagency" in result.stdout

    result = invoke_app(app, ["uninstall", "reagency"])
    assert result.exit_code != 0
    assert "porousmicrotransport" in result.stdout
    assert "reagency" in result.stdout


def test_version() -> None:
    result = invoke_app(app, ["--version"])
    assert result.exit_code == 0
    assert "styro" in result.stdout
    assert __version__ in result.stdout
