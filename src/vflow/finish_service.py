from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from .resolve_adapter import ResolveAdapter


CHECKSUM_ALGORITHM = "sha256"


def _checksum(path: Path) -> str:
    digest = hashlib.new(CHECKSUM_ALGORITHM)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_project(project: str) -> str:
    if (
        project in {"", ".", ".."}
        or project != project.strip()
        or "/" in project
        or "\\" in project
        or "\x00" in project
    ):
        raise ValueError("Project identity must be one non-empty path segment")
    return project


def _verify_retained_outputs(exports: Path, archive: Path, project: str) -> list[dict]:
    local_directory = exports / "Final Videos" / project
    if not local_directory.exists() or not local_directory.is_dir():
        raise ValueError(
            f"Retained output verification failed: no local Final Videos found for Project '{project}'"
        )

    local_outputs = sorted(
        (path for path in local_directory.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(local_directory).as_posix(),
    )
    if not local_outputs:
        raise ValueError(
            f"Retained output verification failed: no local Final Videos found for Project '{project}'"
        )

    verified = []
    for local_output in local_outputs:
        relative_path = local_output.relative_to(local_directory)
        archived_output = (
            archive / "Exports" / "Final Videos" / project / relative_path
        )
        if not archived_output.exists() or not archived_output.is_file():
            raise ValueError(
                f"Retained output verification failed: archived Final Video is missing: {archived_output}"
            )
        local_checksum = _checksum(local_output)
        if _checksum(archived_output) != local_checksum:
            raise ValueError(
                f"Retained output verification failed: content differs: {archived_output}"
            )
        verified.append(
            {
                "local": local_output,
                "archive": archived_output,
                "byte_size": local_output.stat().st_size,
                "checksum": local_checksum,
            }
        )
    return verified


def _export_backup(
    adapter: ResolveAdapter,
    project: str,
    archived_backup: Path,
) -> tuple[str, str]:
    archived_backup.parent.mkdir(parents=True, exist_ok=True)
    temporary = archived_backup.with_name(
        f".{archived_backup.stem}.vflow-part.drp"
    )
    try:
        temporary.unlink(missing_ok=True)
        if not adapter.export_project_backup(
            project,
            temporary,
            include_stills_and_luts=True,
        ):
            raise ValueError(
                f"Resolve project export failed for Project '{project}'"
            )
        if not temporary.exists() or not temporary.is_file():
            raise ValueError(
                f"Project Backup verification failed: Resolve did not create {temporary}"
            )
        if temporary.stat().st_size == 0:
            raise ValueError(
                f"Project Backup verification failed: Resolve created an empty backup at {temporary}"
            )
        checksum = _checksum(temporary)
        if archived_backup.exists():
            if archived_backup.is_file() and _checksum(archived_backup) == checksum:
                temporary.unlink()
                return checksum, "skipped"
            raise ValueError(
                f"Project Backup conflict: existing Archive content differs at {archived_backup}"
            )
        os.replace(temporary, archived_backup)
        if _checksum(archived_backup) != checksum:
            raise ValueError(
                f"Project Backup verification failed after publishing {archived_backup}"
            )
        return checksum, "copied"
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        for directory in (archived_backup.parent, archived_backup.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def finish_project(
    exports: Path,
    archive: Path,
    project: str,
    adapter: Optional[ResolveAdapter],
    dry_run: bool = False,
) -> dict:
    """Verify retained outputs and create a portable, verified Project Backup."""
    project = _safe_project(project)
    outputs = _verify_retained_outputs(exports, archive, project)
    backup_name = f"{project}.drp"
    archived_backup = archive / "Project Backups" / project / backup_name

    result = {
        "project": project,
        "outputs": outputs,
        "archived_backup": archived_backup,
        "dry_run": dry_run,
        "backup_copied": 0,
        "backup_skipped": 0,
        "retained": len(outputs),
    }
    if dry_run:
        return result
    if adapter is None:
        raise ValueError("Resolve access failed: no Resolve adapter is available")

    checksum, outcome = _export_backup(adapter, project, archived_backup)
    result.update(
        {
            "backup_checksum": checksum,
            "backup_copied": int(outcome == "copied"),
            "backup_skipped": int(outcome == "skipped"),
            "retained": len(outputs),
        }
    )
    return result


def report_finish(result: dict) -> None:
    import typer

    typer.echo(f"Project: {result['project']}")
    typer.echo(f"Verified retained outputs: {len(result['outputs'])}")
    typer.echo(f"Archive Project Backup: {result['archived_backup']}")
    if result["dry_run"]:
        typer.echo("Dry run: Resolve was not called and no files changed")
        typer.echo("Would export Project Backup with stills and LUTs: 1")
    else:
        typer.echo("Project Backups verified: 1")
        typer.echo(f"Project Backups copied: {result['backup_copied']}")
        typer.echo(f"Project Backups skipped: {result['backup_skipped']}")
    typer.echo(f"Retained local files: {result['retained']}")
