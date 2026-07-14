import os
from pathlib import Path
from subprocess import run

import pytest

from styro.__main__ import app


def test_styro() -> None:
    app(["install", "styro"], result_action="return_value")

    with pytest.raises(SystemExit) as e:
        app(["uninstall", "styro"], result_action="return_value")
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,
    reason="requires OpenFOAM v2112 or later",
)
def test_install(tmp_path: Path) -> None:
    app(["uninstall", "reagency"], result_action="return_value")

    app(["install", "reagency"], result_action="return_value")

    app(["freeze"], result_action="return_value")

    run(
        ["git", "clone", "https://github.com/gerlero/reagency.git"],
        cwd=tmp_path,
        check=True,
    )
    app(["install", str(tmp_path / "reagency")], result_action="return_value")

    app(["freeze"], result_action="return_value")

    app(
        ["install", "https://github.com/gerlero/reagency.git"],
        result_action="return_value",
    )

    app(["freeze"], result_action="return_value")

    app(["uninstall", "reagency"], result_action="return_value")
    app(["freeze"], result_action="return_value")


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,
    reason="requires OpenFOAM v2112 or later",
)
def test_package_with_dependencies() -> None:
    app(
        ["uninstall", "porousmicrotransport", "reaagency"], result_action="return_value"
    )

    app(["install", "porousmicrotransport"], result_action="return_value")

    app(["freeze"], result_action="return_value")
    with pytest.raises(SystemExit) as e:
        app(["uninstall", "reagency"], result_action="return_value")
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0

    app(["uninstall", "reagency", "porousmicrotransport"], result_action="return_value")
