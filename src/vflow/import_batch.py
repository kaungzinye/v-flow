from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer


CHECKSUM_ALGORITHM = "sha256"
MANIFEST_NAME = "manifest.json"
PENDING_MANIFEST_NAME = ".manifest.pending.json"
CONTENTS_DIRECTORY = "contents"
MANIFEST_VERSION = 1


def _checksum(path: Path) -> str:
    digest = hashlib.new(CHECKSUM_ALGORITHM)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_identity(value: str, label: str) -> str:
    if (
        value in {"", ".", ".."}
        or value != value.strip()
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        typer.echo(
            f"{label} must be one non-empty path segment.",
            err=True,
        )
        raise typer.Exit(code=1)
    return value


def _source_entries(
    source: Path, selected_files: Optional[list[Path]] = None
) -> list[dict]:
    files = (
        selected_files
        if selected_files is not None
        else [path for path in source.rglob("*") if path.is_file()]
    )
    entries = []
    for path in sorted(files, key=lambda item: item.relative_to(source).as_posix()):
        relative_path = path.relative_to(source).as_posix()
        entries.append(
            {
                "relative_path": relative_path,
                "byte_size": path.stat().st_size,
                "checksum": _checksum(path),
            }
        )
    return entries


def _generated_batch_identity(source: Path, entries: list[dict]) -> str:
    identity_digest = hashlib.sha256()
    for entry in entries:
        identity_digest.update(entry["relative_path"].encode("utf-8"))
        identity_digest.update(b"\0")
        identity_digest.update(str(entry["byte_size"]).encode("ascii"))
        identity_digest.update(b"\0")
        identity_digest.update(entry["checksum"].encode("ascii"))
        identity_digest.update(b"\n")
    source_name = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip("-.") or "import"
    return f"{source_name}-{identity_digest.hexdigest()[:12]}"


def _copy_verified(source: Path, destination: Path, expected_checksum: str) -> str:
    if destination.exists():
        if destination.is_file() and _checksum(destination) == expected_checksum:
            return "skipped"
        raise ValueError(f"Archive conflict at {destination}: existing content differs")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.vflow-part")
    try:
        shutil.copy2(source, temporary)
        if _checksum(temporary) != expected_checksum:
            raise ValueError(f"Checksum verification failed for {source}")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return "copied"


def _manifest_matches(manifest_path: Path, expected: dict) -> bool:
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    stable_fields = (
        "manifest_version",
        "checksum_algorithm",
        "shoot_id",
        "import_batch_id",
        "files",
    )
    return all(existing.get(field) == expected.get(field) for field in stable_fields)


def _write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.vflow-part")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def ingest_import_batch(
    source: Path,
    archive: Path,
    shoot_id: str,
    import_batch_id: Optional[str] = None,
    selected_files: Optional[list[Path]] = None,
) -> dict:
    """Copy one source hierarchy into an immutable, verified Archive Import Batch."""
    shoot_id = _safe_identity(shoot_id, "Shoot identity")
    entries = _source_entries(source, selected_files)
    if not entries:
        typer.echo("No files found in the source directory.", err=True)
        raise typer.Exit(code=1)

    batch_id = _safe_identity(
        import_batch_id or _generated_batch_identity(source, entries),
        "Import Batch identity",
    )
    batch_directory = archive / "Camera Originals" / shoot_id / batch_id
    contents_directory = batch_directory / CONTENTS_DIRECTORY
    manifest_path = batch_directory / MANIFEST_NAME
    pending_manifest_path = batch_directory / PENDING_MANIFEST_NAME
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        "shoot_id": shoot_id,
        "import_batch_id": batch_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "files": entries,
    }

    if manifest_path.exists() and not _manifest_matches(manifest_path, manifest):
        typer.echo(
            f"Import Batch '{batch_id}' is immutable and its existing manifest differs.",
            err=True,
        )
        raise typer.Exit(code=1)
    if pending_manifest_path.exists() and not _manifest_matches(
        pending_manifest_path, manifest
    ):
        typer.echo(
            f"Incomplete Import Batch '{batch_id}' belongs to different source content.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not manifest_path.exists() and not pending_manifest_path.exists():
        _write_json_atomically(pending_manifest_path, manifest)

    copied = 0
    skipped = 0
    try:
        for entry in entries:
            source_file = source / Path(entry["relative_path"])
            destination_file = contents_directory / Path(entry["relative_path"])
            outcome = _copy_verified(source_file, destination_file, entry["checksum"])
            if outcome == "copied":
                copied += 1
            else:
                skipped += 1
    except (OSError, ValueError) as error:
        typer.echo(f"Import Batch ingest failed: {error}", err=True)
        typer.echo(
            "Verified Archive files remain intact; retry the same ingest to resume.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not manifest_path.exists():
        os.replace(pending_manifest_path, manifest_path)

    return {
        "shoot_id": shoot_id,
        "import_batch_id": batch_id,
        "batch_directory": batch_directory,
        "manifest_path": manifest_path,
        "copied": copied,
        "skipped": skipped,
        "files": len(entries),
    }
