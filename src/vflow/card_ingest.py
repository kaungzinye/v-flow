from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .shoot_manifest import (
    EXTRAS_DIRECTORY,
    FOOTAGE_EXTENSIONS,
    MANIFEST_NAME,
    PENDING_MANIFEST_NAME,
    batch_identity,
    build_checksum_index,
    checksum,
    destination_name,
    load_manifest,
    place_verified,
    relative_path,
    resolve_unindexed,
    safe_identity,
    scan_unindexed,
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
        batch_id or batch_identity(source, list(sizes.items())),
        "Import Batch identity",
    )

    shoot_path = shoot_directory(archive, shoot)
    shoot_path.mkdir(parents=True, exist_ok=True)
    manifest_path = shoot_path / MANIFEST_NAME
    pending_path = shoot_path / PENDING_MANIFEST_NAME
    manifest = load_manifest(shoot_path, shoot)

    index = build_checksum_index(archive)
    unindexed = scan_unindexed(archive, "video", skip=[shoot_path])
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
                    record["checksum"] = place_verified(source_file, extra)
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
        if known or unindexed.get(byte_size):
            source_checksum = checksum(source_file)
            existing = known.get(source_checksum)
            if existing is not None and not (archive / existing).is_file():
                known.pop(source_checksum, None)
                existing = None
            if existing is None:
                existing = resolve_unindexed(
                    archive, unindexed, index, byte_size, source_checksum, "video"
                )
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

        name = destination_name(relative.name, set(taken), shoot_path)
        stored_checksum = place_verified(
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
