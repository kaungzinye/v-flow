from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from string import ascii_lowercase
from typing import Optional

from .shoot_manifest import (
    CHECKSUM_ALGORITHM,
    CHUNK_SIZE,
    EXTRAS_DIRECTORY,
    FOOTAGE_EXTENSIONS,
    MANIFEST_NAME,
    PENDING_MANIFEST_NAME,
    build_checksum_index,
    checksum,
    load_manifest,
    relative_path,
    safe_identity,
    shoot_directory,
    write_json_atomically,
)


def _exclusion_reason(relative: Path) -> Optional[str]:
    if any(part.startswith(".") for part in relative.parts[:-1]):
        return "hidden folder"
    name = relative.name
    if name.startswith("._"):
        return "AppleDouble sidecar"
    if name.startswith("."):
        return "hidden file"
    if relative.suffix.lower() not in FOOTAGE_EXTENSIONS:
        return "non-footage file type"
    return None


def _batch_identity(source: Path, entries: list[tuple[str, int]]) -> str:
    """Identity from source name plus card-relative paths and sizes, without reading content."""
    digest = hashlib.sha256()
    for path, byte_size in sorted(entries):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(byte_size).encode("ascii"))
        digest.update(b"\n")
    source_name = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip("-.") or "card"
    return f"{source_name}-{digest.hexdigest()[:12]}"


def _copy_hashing(source: Path, temporary: Path) -> str:
    """Copy one file, hashing the single source read."""
    digest = hashlib.new(CHECKSUM_ALGORITHM)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, temporary.open("wb") as writer:
        for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            writer.write(chunk)
    shutil.copystat(source, temporary)
    return digest.hexdigest()


def _place_verified(source: Path, destination: Path, expected: Optional[str] = None) -> str:
    """Copy into place and prove the destination by re-hashing it on the archive drive."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.vflow-part")
    try:
        source_checksum = _copy_hashing(source, temporary)
        if expected is not None and source_checksum != expected:
            raise ValueError(f"Source content changed during ingest: {source}")
        if checksum(temporary) != source_checksum:
            raise ValueError(f"Checksum verification failed for {destination}")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return source_checksum


def _suffixed_names(name: str):
    stem, suffix = Path(name).stem, Path(name).suffix
    yield name
    for letter in ascii_lowercase[1:]:
        yield f"{stem}_{letter}{suffix}"
    counter = 2
    while True:
        yield f"{stem}_{counter}{suffix}"
        counter += 1


def _destination_name(name: str, taken: set[str], shoot_path: Path) -> str:
    for candidate in _suffixed_names(name):
        if candidate not in taken and not (shoot_path / candidate).exists():
            return candidate
    raise ValueError(f"No available destination name for {name}")


def ingest_card(
    source: Path,
    archive: Path,
    shoot: str,
    batch_id: Optional[str] = None,
    selected_files: Optional[list[Path]] = None,
    include_all: bool = False,
) -> dict:
    """Copy footage from one card into a flat Shoot folder backed by a hidden manifest."""
    shoot = safe_identity(shoot, "Shoot identity")
    source_files = (
        selected_files
        if selected_files is not None
        else [path for path in source.rglob("*") if path.is_file()]
    )
    candidates = sorted(
        (path.relative_to(source), path) for path in source_files
    )
    if not candidates:
        raise ValueError("No files found in the source directory.")

    sizes = {
        relative.as_posix(): path.stat().st_size for relative, path in candidates
    }
    batch_id = safe_identity(
        batch_id or _batch_identity(source, list(sizes.items())),
        "Import Batch identity",
    )

    shoot_path = shoot_directory(archive, shoot)
    shoot_path.mkdir(parents=True, exist_ok=True)
    manifest_path = shoot_path / MANIFEST_NAME
    pending_path = shoot_path / PENDING_MANIFEST_NAME
    manifest = load_manifest(shoot_path, shoot)

    index = build_checksum_index(archive)
    recorded = {
        (entry.get("batch_id"), entry.get("source_relative_path")): entry
        for entry in manifest["files"]
    }
    taken = {entry["name"]: entry["checksum"] for entry in manifest["files"]}

    copied = 0
    verified = 0
    deduplicated = 0
    excluded = 0

    def save_progress() -> None:
        write_json_atomically(pending_path, manifest)

    for relative, source_file in candidates:
        card_path = relative.as_posix()
        byte_size = sizes[card_path]
        ingested_at = datetime.now(timezone.utc).isoformat()

        reason = _exclusion_reason(relative)
        if reason is not None:
            record = {
                "source_relative_path": card_path,
                "byte_size": byte_size,
                "reason": reason,
                "batch_id": batch_id,
                "ingested_at": ingested_at,
            }
            if include_all:
                extra = shoot_path / EXTRAS_DIRECTORY / relative
                if not extra.is_file():
                    record["checksum"] = _place_verified(source_file, extra)
                else:
                    record["checksum"] = checksum(extra)
                record["stored_as"] = (
                    Path(EXTRAS_DIRECTORY) / relative
                ).as_posix()
            manifest["excluded"] = [
                item
                for item in manifest["excluded"]
                if (item.get("batch_id"), item.get("source_relative_path"))
                != (batch_id, card_path)
            ]
            manifest["excluded"].append(record)
            excluded += 1
            save_progress()
            continue

        entry = recorded.get((batch_id, card_path))
        if entry is not None:
            archived = shoot_path / relative_path(entry["name"])
            if archived.is_file() and checksum(archived) == entry["checksum"]:
                verified += 1
                continue
            manifest["files"].remove(entry)
            taken.pop(entry["name"], None)
            index.get(entry["byte_size"], {}).pop(entry["checksum"], None)

        known = index.get(byte_size, {})
        source_checksum: Optional[str] = None
        if known:
            source_checksum = checksum(source_file)
            existing = known.get(source_checksum)
            if existing is not None and not (archive / existing).is_file():
                known.pop(source_checksum, None)
                existing = None
            if existing is not None:
                manifest["deduplicated"] = [
                    item
                    for item in manifest["deduplicated"]
                    if (item.get("batch_id"), item.get("source_relative_path"))
                    != (batch_id, card_path)
                ]
                manifest["deduplicated"].append(
                    {
                        "source_relative_path": card_path,
                        "original_name": relative.name,
                        "byte_size": byte_size,
                        "checksum": source_checksum,
                        "existing_location": existing,
                        "batch_id": batch_id,
                        "ingested_at": ingested_at,
                    }
                )
                deduplicated += 1
                save_progress()
                continue

        name = _destination_name(relative.name, set(taken), shoot_path)
        stored_checksum = _place_verified(
            source_file, shoot_path / name, expected=source_checksum
        )
        record = {
            "name": name,
            "byte_size": byte_size,
            "checksum": stored_checksum,
            "source_relative_path": card_path,
            "source_name": source.name,
            "batch_id": batch_id,
            "ingested_at": ingested_at,
        }
        if name != relative.name:
            record["original_name"] = relative.name
        manifest["files"].append(record)
        taken[name] = stored_checksum
        index.setdefault(byte_size, {}).setdefault(
            stored_checksum, (shoot_path / name).relative_to(archive).as_posix()
        )
        copied += 1
        save_progress()

    write_json_atomically(pending_path, manifest)
    os.replace(pending_path, manifest_path)

    return {
        "shoot": shoot,
        "batch_id": batch_id,
        "shoot_directory": shoot_path,
        "manifest_path": manifest_path,
        "copied": copied,
        "verified": verified,
        "deduplicated": deduplicated,
        "excluded": excluded,
        "files": len(manifest["files"]),
    }
