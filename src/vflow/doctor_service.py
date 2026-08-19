from __future__ import annotations

import json
import os
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Optional

import typer

from . import config
from .resolve_adapter import ResolveUnavailableError, get_resolve_adapter
from .shoot_manifest import safe_subpath


PACKAGE_NAME = "vflow-cli"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
PYPI_TIMEOUT_SECONDS = 2.0

# What each reported line means: a failing check keeps ingest from running, and an
# informational one describes what a later command will need.
OK = "ok"
FAIL = "fail"
INFO = "info"


def installed_version() -> Optional[str]:
    """The version of v-flow answering this command."""
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return None


def published_version() -> Optional[str]:
    """The newest version on PyPI, or nothing when the network does not answer."""
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=PYPI_TIMEOUT_SECONDS) as response:
            return json.load(response)["info"]["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _check(state: str, text: str) -> dict:
    return {"state": state, "text": text}


def _creatable(path: Path) -> bool:
    """Whether a missing directory could be created where it is asked to sit."""
    existing = path
    while not existing.exists():
        parent = existing.parent
        if parent == existing:
            return False
        existing = parent
    return existing.is_dir() and os.access(existing, os.W_OK)


def _location_checks(app_config: dict) -> list[dict]:
    """The Archive, the Exports folder, and every named Working Location."""
    checks = []
    archive = config.resolve_location(app_config, "archive")
    if not archive:
        checks.append(
            _check(FAIL, "Archive: not configured. Run 'v-flow set archive <path>'.")
        )
    elif config.location_status(archive) == "available":
        checks.append(_check(OK, f"Archive: {archive} [available]"))
    else:
        checks.append(
            _check(
                FAIL,
                f"Archive: {archive} [unavailable]. Connect that drive and re-run "
                "'v-flow doctor', or point 'v-flow set archive <path>' at where it is now.",
            )
        )

    exports = config.resolve_location(app_config, "exports")
    if not exports:
        checks.append(
            _check(
                INFO,
                "Exports: not configured. 'v-flow archive' and 'v-flow finish' need "
                "'v-flow set exports <path>'.",
            )
        )
    else:
        checks.append(
            _check(INFO, f"Exports: {exports} [{config.location_status(exports)}]")
        )

    working = app_config.get("locations", {}).get("working", {})
    for name, path in (working if isinstance(working, dict) else {}).items():
        checks.append(
            _check(
                INFO,
                f"Working location '{name}': {path} [{config.location_status(str(path))}]",
            )
        )
    return checks


def _layout_checks(app_config: dict) -> list[dict]:
    """The layout in force and whether its roots exist or can be created."""
    checks = []
    configured = app_config.get("layout") or {}
    if not isinstance(configured, dict):
        return [
            _check(
                FAIL,
                "Archive layout: the 'layout' section must be a dictionary. "
                "Set each key with 'v-flow set layout.<key> <subpath>'.",
            )
        ]

    layout = {}
    for key, default in config.DEFAULT_LAYOUT.items():
        value = configured.get(key, default)
        try:
            layout[key] = safe_subpath(value, f"layout.{key}")
        except ValueError as error:
            checks.append(
                _check(
                    FAIL,
                    f"Archive layout: {error}. Run 'v-flow set layout.{key} <subpath>'.",
                )
            )
    if not checks:
        stated = ", ".join(f"{key} {'/'.join(parts)}" for key, parts in layout.items())
        checks.append(_check(OK, f"Archive layout: {stated}"))

    archive = config.resolve_location(app_config, "archive")
    if not archive or config.location_status(archive) != "available":
        return checks

    for key, parts in layout.items():
        root = Path(archive).joinpath(*parts)
        if root.is_dir():
            checks.append(_check(OK, f"Archive root {key}: {root} exists"))
        elif root.exists():
            checks.append(
                _check(
                    FAIL,
                    f"Archive root {key}: {root} is a file, not a folder. "
                    f"Move it aside or run 'v-flow set layout.{key} <subpath>'.",
                )
            )
        elif _creatable(root):
            checks.append(
                _check(OK, f"Archive root {key}: {root} will be created by the first ingest")
            )
        else:
            checks.append(
                _check(
                    FAIL,
                    f"Archive root {key}: {root} cannot be created. "
                    "Check the drive's permissions and free space.",
                )
            )
    return checks


def _resolve_check(adapter_source=None) -> dict:
    try:
        (adapter_source or get_resolve_adapter)()
    except (ResolveUnavailableError, OSError) as error:
        return _check(
            INFO,
            f"Resolve API: unavailable. {error} Only 'v-flow finish' and "
            "'v-flow cleanup' need it.",
        )
    return _check(INFO, "Resolve API: reachable")


def _version_check() -> dict:
    installed = installed_version() or "unknown"
    published = published_version()
    if published is None:
        return _check(
            INFO,
            f"Version: {installed} installed. The PyPI check got no answer, "
            "which affects nothing else.",
        )
    if published == installed:
        return _check(INFO, f"Version: {installed} installed, the newest on PyPI")
    return _check(
        INFO,
        f"Version: {installed} installed, {published} on PyPI. "
        f"Upgrade with 'uv tool upgrade {PACKAGE_NAME}'.",
    )


def diagnose(adapter_source=None) -> dict:
    """Describe the whole environment without touching one media file."""
    checks = []
    app_config, problem = config.parse_config()
    if problem is not None:
        checks.append(_check(FAIL, problem))
    else:
        problems = config.config_problems(app_config)
        for text in problems:
            checks.append(_check(FAIL, f"{text} Fix it with 'v-flow set <key> <value>'."))
        if not problems:
            checks.append(_check(OK, f"Config file: {config.CONFIG_PATH}"))
            checks.extend(_location_checks(app_config))
            checks.extend(_layout_checks(app_config))

    checks.append(_resolve_check(adapter_source))
    checks.append(_version_check())
    return {"checks": checks, "ready": not any(item["state"] == FAIL for item in checks)}


def report_doctor(result: dict) -> None:
    """Print one plain line per check, readable aloud to someone who did not run it."""
    for item in result["checks"]:
        typer.echo(f"[{item['state']}] {item['text']}")
    if result["ready"]:
        typer.echo("Ready: ingest and index can run now.")
    else:
        typer.echo("Not ready: fix each [fail] line above, then run 'v-flow doctor' again.")
