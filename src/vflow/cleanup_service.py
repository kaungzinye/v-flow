from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional, Union

import typer

from . import config
from .checkout_service import _checksum, _load_checkout_entries
from .resolve_adapter import ResolveAdapter


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(directory.resolve(strict=False))
        return True
    except ValueError:
        return False


def _cleanup_plan(
    app_config: dict,
    archive: Path,
    shoot: str,
    working_location: str,
) -> dict:
    working_root = config.get_location(app_config, working_location)
    target = working_root / shoot
    if _is_within(target, archive):
        raise ValueError(
            f"Archive safety gate failed: Cleanup refuses targets inside Archive storage: {target}"
        )
    if not target.exists() or not target.is_dir():
        raise ValueError(f"Working Copy is unavailable: {target}")

    _, entries = _load_checkout_entries(archive, shoot, config.get_layout(app_config))
    files = []
    for entry in entries:
        archived = entry["source"]
        working = target / entry["name"]
        planned = {
            "working": working,
            "archive": archived,
            "byte_size": entry["byte_size"],
            "checksum": entry["checksum"],
            "algorithm": entry["algorithm"],
        }
        _verify_planned_file(planned)
        files.append(planned)

    return {
        "shoot": shoot,
        "working_location": working_location,
        "archive_root": archive,
        "target": target,
        "files": files,
        "bytes": sum(item["working"].stat().st_size for item in files),
    }


def _verify_planned_file(item: dict) -> None:
    archived = item["archive"]
    working = item["working"]
    if not archived.is_file() or archived.stat().st_size != item["byte_size"]:
        raise ValueError(
            f"Archive checksum gate failed: archived Camera Original is missing or has the wrong size: {archived}"
        )
    if _checksum(archived, item["algorithm"]) != item["checksum"]:
        raise ValueError(
            f"Archive checksum gate failed: archived Camera Original differs from its manifest: {archived}"
        )
    if not working.is_file():
        raise ValueError(
            f"Working Copy verification failed: expected file is missing: {working}"
        )
    if (
        working.stat().st_size != item["byte_size"]
        or _checksum(working, item["algorithm"]) != item["checksum"]
    ):
        raise ValueError(
            f"Working Copy verification failed: content is not preserved in the Archive: {working}"
        )


def prepare_cleanup(
    app_config: dict,
    archive: Path,
    shoot: str,
    working_location: str,
    project: Optional[str],
    adapter: Optional[Union[ResolveAdapter, Callable[[], ResolveAdapter]]],
    skip_resolve_validation: bool = False,
    dry_run: bool = False,
) -> dict:
    """Pass every safety gate and return a deletion plan for a Working Copy."""
    plan = _cleanup_plan(app_config, archive, shoot, working_location)
    plan.update(
        {
            "project": project,
            "skip_resolve_validation": skip_resolve_validation,
            "dry_run": dry_run,
            "resolve": None,
        }
    )
    if skip_resolve_validation:
        return plan
    if not project:
        raise ValueError(
            "Resolve validation gate failed: --project is required unless --skip-resolve-validation is supplied"
        )
    if adapter is None:
        raise ValueError("Resolve validation gate failed: no Resolve adapter is available")
    if callable(adapter):
        adapter = adapter()

    validation = adapter.validate_project_media(
        project,
        {item["working"]: item["archive"] for item in plan["files"]},
        allow_relink=not dry_run,
    )
    unresolved = validation.get("unresolved", [])
    if unresolved:
        listed = "\n".join(f"  - {path}" for path in unresolved)
        action = "would require relinking" if dry_run else "remain offline or linked to the Working Copy"
        raise ValueError(
            f"Resolve validation gate failed: {len(unresolved)} media file(s) {action}:\n{listed}"
        )
    plan["resolve"] = validation
    return plan


def delete_working_copy(plan: dict) -> dict:
    """Delete only the manifest-backed files in a prepared Cleanup plan."""
    deleted = 0
    failures = []
    for item in plan["files"]:
        path = item["working"]
        try:
            if _is_within(path, plan["archive_root"]):
                raise ValueError(
                    f"Archive safety gate failed immediately before deletion: {path}"
                )
            _verify_planned_file(item)
            path.unlink()
            deleted += 1
        except (OSError, ValueError) as error:
            failures.append((path, str(error)))

    target = plan["target"]
    for directory, _, _ in os.walk(target, topdown=False):
        try:
            Path(directory).rmdir()
        except OSError:
            pass

    result = dict(plan, deleted=deleted, failures=failures)
    return result


def report_cleanup(plan: dict) -> None:
    typer.echo(f"Shoot: {plan['shoot']}")
    typer.echo(f"Working Copy: {plan['target']}")
    typer.echo(f"Archive checksum verified: {len(plan['files'])} files")
    if plan["skip_resolve_validation"]:
        typer.echo("Resolve validation: explicitly skipped")
    elif plan["resolve"] is not None:
        typer.echo(f"Resolve media confirmed: {plan['resolve'].get('confirmed', 0)}")
        typer.echo(f"Resolve media relinked: {plan['resolve'].get('relinked', 0)}")
        if plan["resolve"].get("pending_relinks"):
            typer.echo(
                f"Resolve media that would be relinked: {len(plan['resolve']['pending_relinks'])}"
            )
    if plan["dry_run"]:
        typer.echo(f"Dry run: {len(plan['files'])} files would be deleted")
    elif "deleted" in plan:
        typer.echo(f"Working Copy files deleted: {plan['deleted']}")
        typer.echo(f"Deletion failures: {len(plan['failures'])}")
        for path, error in plan["failures"]:
            typer.echo(f"  - {path}: {error}", err=True)
