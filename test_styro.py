import os
from pathlib import Path
from subprocess import run

import pytest

from styro.__main__ import app


def test_styro() -> None:
    app(["install", "styro"])

    with pytest.raises(SystemExit) as e:
        app(["uninstall", "styro"])
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_install(tmp_path: Path) -> None:
    app(["uninstall", "reagency"])

    app(["install", "reagency"])

    app(["freeze"])

    run(
        ["git", "clone", "https://github.com/gerlero/reagency.git"],  # noqa: S607
        cwd=tmp_path,
        check=True,
    )
    app(["install", str(tmp_path / "reagency")])

    app(["freeze"])

    app(["install", "https://github.com/gerlero/reagency.git"])

    app(["freeze"])

    app(["uninstall", "reagency"])


app(["freeze"])


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_package_with_dependencies() -> None:
    app(["uninstall", "porousmicrotransport", "reaagency"])

    app(["install", "porousmicrotransport"])

    app(["freeze"])

    with pytest.raises(SystemExit) as e:
        app(["uninstall", "reagency"])
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0

    app(["uninstall", "reagency", "porousmicrotransport"])
