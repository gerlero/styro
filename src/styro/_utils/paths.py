from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator


def path_from_uri(uri: str, /) -> Path:
    assert uri.startswith("file://")
    if sys.version_info >= (3, 13):
        return Path.from_uri(uri)

    from urllib.request import url2pathname

    ret = Path(url2pathname(uri.removeprefix("file:")))
    assert ret.is_absolute()
    return ret


@contextmanager
def get_changed_files(path: Path, /) -> Generator[set[Path], None, None]:
    before = {file: file.stat().st_mtime for file in path.rglob("*") if file.is_file()}
    ret: set[Path] = set()
    try:
        yield ret
    finally:
        after_files = {file for file in path.rglob("*") if file.is_file()}
        before_files = set(before.keys())

        # Add newly created files (files that exist now but didn't before)
        new_files = after_files - before_files
        ret.update(new_files)

        # Add modified files (files that existed before but have different timestamps)
        for file in after_files & before_files:
            if file.stat().st_mtime != before[file]:
                ret.add(file)
