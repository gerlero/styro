import sys

import aiohttp
import typer

from . import __version__


def is_managed_installation() -> bool:
    return not getattr(sys, "frozen", False)


def print_upgrade_instruction() -> None:
    if is_managed_installation():
        typer.echo(
            "Use your package manager (e.g. pip) to upgrade styro.",
            err=True,
        )
    else:
        typer.echo(
            "Run 'styro install --upgrade styro' to upgrade styro.",
            err=True,
        )


async def check_for_new_version(*, verbose: bool = True) -> bool:
    try:
        async with aiohttp.ClientSession(
            raise_for_status=True, timeout=2
        ) as session, session.get(
            "https://api.github.com/repos/gerlero/styro/releases/latest",
        ) as response:
            contents = await response.json()
            latest_version = contents["tag_name"]
    except Exception:  # noqa: BLE001
        return False

    if latest_version.startswith("v"):
        latest_version = latest_version[1:]

    if latest_version != __version__:
        if verbose:
            typer.echo(
                f"⚠️ Warning: you are using styro {__version__}, but version {latest_version} is available.",
                err=True,
            )
            print_upgrade_instruction()
        return True

    return False
