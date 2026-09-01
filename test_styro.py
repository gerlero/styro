import os
from pathlib import Path
from subprocess import run

import cyclopts
import pytest

from styro.__main__ import app


def _app(args: list[str]) -> None:
    if cyclopts.__version__.startswith("3."):
        app(args)
    else:
        app(args, result_action="return_value")


def test_styro() -> None:
    _app(["install", "styro"])

    with pytest.raises(SystemExit) as e:
        _app(["uninstall", "styro"])
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,
    reason="requires OpenFOAM v2112 or later",
)
def test_install(tmp_path: Path) -> None:
    _app(["uninstall", "reagency"])

    _app(["install", "reagency"])

    _app(["freeze"])

    run(
        ["git", "clone", "https://github.com/gerlero/reagency.git"],
        cwd=tmp_path,
        check=True,
    )
    _app(["install", str(tmp_path / "reagency")])

    _app(["freeze"])

    _app(["install", "https://github.com/gerlero/reagency.git"])
    _app(["freeze"])

    _app(["uninstall", "reagency"])
    _app(["freeze"])


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,
    reason="requires OpenFOAM v2112 or later",
)
def test_package_with_dependencies() -> None:
    _app(["uninstall", "porousmicrotransport", "reaagency"])

    _app(["install", "porousmicrotransport"])

    _app(["freeze"])
    with pytest.raises(SystemExit) as e:
        _app(["uninstall", "reagency"])
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0

    _app(["uninstall", "reagency", "porousmicrotransport"])
