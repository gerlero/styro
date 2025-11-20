import os
import sys
from pathlib import Path
from subprocess import run

import pytest

from styro.__main__ import app

if sys.version_info >= (3, 10):
    RESULT_KWARG = {"result_action": "return_value"}
else:
    RESULT_KWARG = {}


def test_styro() -> None:
    app(["install", "styro"], **RESULT_KWARG)

    with pytest.raises(SystemExit) as e:
        app(["uninstall", "styro"], **RESULT_KWARG)
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_install(tmp_path: Path) -> None:
    app(["uninstall", "reagency"], **RESULT_KWARG)

    app(["install", "reagency"], **RESULT_KWARG)

    app(["freeze"], **RESULT_KWARG)

    run(
        ["git", "clone", "https://github.com/gerlero/reagency.git"],  # noqa: S607
        cwd=tmp_path,
        check=True,
    )
    app(["install", str(tmp_path / "reagency")], **RESULT_KWARG)

    app(["freeze"], **RESULT_KWARG)

    app(
        ["install", "https://github.com/gerlero/reagency.git"],
        **RESULT_KWARG,
    )
    app(["freeze"], **RESULT_KWARG)

    app(["uninstall", "reagency"], **RESULT_KWARG)
    app(["freeze"], **RESULT_KWARG)


@pytest.mark.skipif(
    int(os.environ.get("FOAM_API", "0")) < 2112,  # noqa: PLR2004
    reason="requires OpenFOAM v2112 or later",
)
def test_package_with_dependencies() -> None:
    app(["uninstall", "porousmicrotransport", "reaagency"], **RESULT_KWARG)

    app(["install", "porousmicrotransport"], **RESULT_KWARG)

    app(["freeze"], **RESULT_KWARG)
    with pytest.raises(SystemExit) as e:
        app(["uninstall", "reagency"])
    assert isinstance(e.value, SystemExit)
    assert e.value.code != 0

    app(["uninstall", "reagency", "porousmicrotransport"], **RESULT_KWARG)
