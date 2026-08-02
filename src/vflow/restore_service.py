from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


CHECKSUM_ALGORITHM = "sha256"
PARTIAL_SUFFIX = ".vflow-part"


def _checksum(path: Path) -> str:
    digest = hashlib.new(CHECKSUM_ALGORITHM)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_source(archive: Path, source_asset: str) -> Path:
    archive = archive.expanduser().resolve()
    requested = Path(source_asset).expanduser()
    if not requested.is_absolute():
        requested = archive / requested
    if requested.is_symlink():
        raise ValueError(f"Archived asset must not be a symbolic link: {requested}")
    source = requested.resolve()

    if not _is_within(source, archive):
        raise ValueError(f"Restore source must be inside the Archive: {archive}")
    if not source.exists():
        raise ValueError(f"Archived asset not found: {source}")
    if source.is_symlink() or not (source.is_file() or source.is_dir()):
        raise ValueError(f"Archived asset must be a regular file or directory: {source}")
    return source


def _resolve_destination(archive: Path, destination: str) -> Path:
    archive = archive.expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if _is_within(target, archive):
        raise ValueError("Restore destination must be outside the Archive")
    return target


def _source_files(source: Path) -> list[tuple[Path, Path]]:
    if source.is_file():
        return [(source, Path())]

    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Archived asset contains a symbolic link: {path}")
        if path.is_file():
            files.append((path, path.relative_to(source)))
        elif not path.is_dir():
            raise ValueError(f"Archived asset contains an unsupported entry: {path}")
    return files


def _destination_parent_conflicts(destination: Path) -> bool:
    current = destination.parent
    while not current.exists():
        current = current.parent
    return not current.is_dir()


def _plan_restore(source: Path, destination: Path) -> dict:
    source_is_file = source.is_file()
    entries = []

    if not source_is_file and destination.exists() and not destination.is_dir():
        return {
            "source": source,
            "destination": destination,
            "entries": [],
            "source_files": 0,
            "total_bytes": 0,
            "copy_files": 0,
            "copy_bytes": 0,
            "skip_files": 0,
            "conflicts": [destination],
        }

    for source_file, relative_path in _source_files(source):
        destination_file = destination if source_is_file else destination / relative_path
        checksum = _checksum(source_file)
        byte_size = source_file.stat().st_size

        if _destination_parent_conflicts(destination_file):
            action = "conflict"
        elif not destination_file.exists():
            action = "copy"
        elif destination_file.is_file() and _checksum(destination_file) == checksum:
            action = "skip"
        else:
            action = "conflict"

        entries.append(
            {
                "source": source_file,
                "destination": destination_file,
                "checksum": checksum,
                "byte_size": byte_size,
                "action": action,
            }
        )

    return {
        "source": source,
        "destination": destination,
        "entries": entries,
        "source_files": len(entries),
        "total_bytes": sum(entry["byte_size"] for entry in entries),
        "copy_files": sum(entry["action"] == "copy" for entry in entries),
        "copy_bytes": sum(
            entry["byte_size"] for entry in entries if entry["action"] == "copy"
        ),
        "skip_files": sum(entry["action"] == "skip" for entry in entries),
        "conflicts": [
            entry["destination"] for entry in entries if entry["action"] == "conflict"
        ],
    }


def _copy_verified(entry: dict) -> str:
    source = entry["source"]
    destination = entry["destination"]
    if destination.exists():
        if destination.is_file() and _checksum(destination) == entry["checksum"]:
            return "skipped"
        raise ValueError(f"Restore conflict at {destination}: existing content differs")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}{PARTIAL_SUFFIX}")
    try:
        shutil.copy2(source, temporary)
        if _checksum(temporary) != entry["checksum"]:
            raise ValueError(f"Restore checksum verification failed for {source}")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return "copied"


def restore_archive_asset(
    archive: Path,
    source_asset: str,
    destination: str,
    dry_run: bool = False,
) -> dict:
    """Create a verified copy of an explicit archived asset at a chosen destination."""
    source = _resolve_source(archive, source_asset)
    target = _resolve_destination(archive, destination)
    result = {**_plan_restore(source, target), "dry_run": dry_run}

    if dry_run:
        return result
    if result["conflicts"]:
        listed = "\n".join(f"  - {path}" for path in result["conflicts"])
        raise ValueError(
            "Restore conflict: existing destination content differs from the Archive:\n"
            + listed
        )

    copied = 0
    skipped = 0
    try:
        for entry in result["entries"]:
            outcome = _copy_verified(entry)
            copied += outcome == "copied"
            skipped += outcome == "skipped"
    except (OSError, ValueError) as error:
        raise ValueError(
            f"Restore interrupted: {error}\n"
            "Verified destination files and the Archive remain intact; retry the same Restore to resume."
        )

    return {**result, "copied": copied, "skipped": skipped}


def report_restore(result: dict) -> None:
    import typer

    typer.echo(f"Archived source: {result['source']}")
    typer.echo(f"Destination: {result['destination']}")
    typer.echo(
        f"Source: {result['source_files']} files, {result['total_bytes']} bytes"
    )
    if result["dry_run"]:
        for entry in result["entries"]:
            typer.echo(
                f"{entry['action'].upper()}: {entry['source']} -> "
                f"{entry['destination']} ({entry['byte_size']} bytes)"
            )
        for conflict in result["conflicts"]:
            if not any(entry["destination"] == conflict for entry in result["entries"]):
                typer.echo(f"CONFLICT: {conflict}")
        typer.echo("Dry run: no files changed")
        typer.echo(
            f"Expected copies: {result['copy_files']} files, {result['copy_bytes']} bytes"
        )
        typer.echo(f"Verified skips: {result['skip_files']}")
        typer.echo(f"Conflicts: {len(result['conflicts'])}")
    else:
        typer.echo(
            f"Restore complete: {result['copied']} copied, "
            f"{result['skipped']} already verified, {result['source_files']} total"
        )
    typer.echo("Archive changed: no")
