from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Optional


CHECKSUM_ALGORITHM = "sha256"
EXPORT_CATEGORIES = {
    "final-video": ("Final Videos", "Project"),
    "graded-select": ("Graded Selects", "Shoot"),
}


def _checksum(path: Path) -> str:
    digest = hashlib.new(CHECKSUM_ALGORITHM)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_segment(value: str, label: str) -> str:
    if (
        value in {"", ".", ".."}
        or value != value.strip()
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError(f"{label} must be one non-empty path segment")
    return value


def _export_paths(
    exports: Path,
    archive: Path,
    export_type: str,
    file_name: str,
    project: Optional[str],
    shoot: Optional[str],
) -> tuple[str, str, Path, Path]:
    try:
        category, identity_label = EXPORT_CATEGORIES[export_type]
    except KeyError:
        raise ValueError("Export type must be 'final-video' or 'graded-select'")

    file_name = _safe_segment(file_name, "Export filename")
    if export_type == "final-video":
        if not project or shoot:
            raise ValueError(
                "Final Video archive requires --project and does not accept --shoot"
            )
        identity = _safe_segment(project, identity_label)
    else:
        if not shoot or project:
            raise ValueError(
                "Graded Select archive requires --shoot and does not accept --project"
            )
        identity = _safe_segment(shoot, identity_label)

    relative_path = Path(category) / identity / file_name
    return category, identity, exports / relative_path, archive / "Exports" / relative_path


def _plan(source: Path, destination: Path) -> dict:
    if not source.exists() or not source.is_file():
        raise ValueError(f"Local export not found: {source}")

    checksum = _checksum(source)
    if not destination.exists():
        action = "copy"
    elif destination.is_file() and _checksum(destination) == checksum:
        action = "skip"
    else:
        raise ValueError(
            f"Archive conflict: existing content differs at {destination}"
        )

    return {
        "source": source,
        "destination": destination,
        "checksum": checksum,
        "byte_size": source.stat().st_size,
        "action": action,
    }


def _copy_verified(plan: dict) -> None:
    source = plan["source"]
    destination = plan["destination"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.vflow-part")
    try:
        shutil.copy2(source, temporary)
        if _checksum(temporary) != plan["checksum"]:
            raise ValueError(f"Archive checksum verification failed for {source}")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def archive_export(
    exports: Path,
    archive: Path,
    export_type: str,
    file_name: str,
    project: Optional[str] = None,
    shoot: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Copy and verify one local export without changing its source."""
    category, identity, source, destination = _export_paths(
        exports,
        archive,
        export_type,
        file_name,
        project,
        shoot,
    )
    plan = _plan(source, destination)

    if not dry_run and plan["action"] == "copy":
        _copy_verified(plan)

    return {
        **plan,
        "category": category,
        "identity": identity,
        "dry_run": dry_run,
        "copied": int(not dry_run and plan["action"] == "copy"),
        "verified": int(not dry_run),
        "skipped": int(not dry_run and plan["action"] == "skip"),
        "retained": 1,
        "would_copy": int(dry_run and plan["action"] == "copy"),
        "would_skip": int(dry_run and plan["action"] == "skip"),
    }


def report_archive(result: dict) -> None:
    import typer

    typer.echo(f"Category: {result['category']}")
    typer.echo(f"Source: {result['source']}")
    typer.echo(f"Archive: {result['destination']}")
    if result["dry_run"]:
        typer.echo("Dry run: no files changed")
        typer.echo(f"Would copy: {result['would_copy']}")
        typer.echo(f"Would skip verified: {result['would_skip']}")
    else:
        typer.echo(f"Copied: {result['copied']}")
        typer.echo(f"Verified: {result['verified']}")
        typer.echo(f"Skipped: {result['skipped']}")
    typer.echo(f"Retained local files: {result['retained']}")
