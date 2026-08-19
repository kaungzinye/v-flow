from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .shoot_manifest import (
    MANIFEST_NAME,
    PENDING_MANIFEST_NAME,
    PHOTO_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    batch_identity,
    build_checksum_index,
    checksum,
    destination_name,
    load_manifest,
    manifest_source,
    place_verified,
    relative_path,
    safe_identity,
    shoot_directory,
    write_json_atomically,
)


def _hidden_reason(relative: Path) -> Optional[str]:
    if any(part.startswith(".") for part in relative.parts[:-1]):
        return "hidden folder"
    if relative.name.startswith("._"):
        return "AppleDouble sidecar"
    if relative.name.startswith("."):
        return "hidden file"
    return None


def _exclusion_reason(relative: Path, attached: bool) -> Optional[str]:
    reason = _hidden_reason(relative)
    if reason is not None:
        return reason
    suffix = relative.suffix.lower()
    if suffix in SIDECAR_EXTENSIONS:
        return None if attached else "editing sidecar without its photo"
    if suffix not in PHOTO_EXTENSIONS:
        return "non-photo file type"
    return None


def _attach_sidecars(candidates: list[tuple[Path, Path]]) -> dict[Path, tuple[Path, str]]:
    """Map each editing sidecar to the photo it belongs to, matched inside one card folder."""
    by_name: dict[tuple[Path, str], Path] = {}
    by_stem: dict[tuple[Path, str], Path] = {}
    for relative, _ in candidates:
        if _hidden_reason(relative) is not None:
            continue
        if relative.suffix.lower() in PHOTO_EXTENSIONS:
            by_name.setdefault((relative.parent, relative.name.lower()), relative)
            by_stem.setdefault((relative.parent, relative.stem.lower()), relative)

    attached: dict[Path, tuple[Path, str]] = {}
    for relative, _ in candidates:
        if _hidden_reason(relative) is not None:
            continue
        if relative.suffix.lower() not in SIDECAR_EXTENSIONS:
            continue
        base = relative.name[: -len(relative.suffix)].lower()
        photo = by_name.get((relative.parent, base))
        mode = "name"
        if photo is None:
            photo = by_stem.get((relative.parent, base))
            mode = "stem"
        if photo is not None:
            attached[relative] = (photo, mode)
    return attached


def _sidecar_name(photo_name: str, mode: str, suffix: str) -> str:
    """The sidecar name that keeps a sidecar paired with its photo's archived name."""
    if mode == "name":
        return f"{photo_name}{suffix}"
    return f"{Path(photo_name).stem}{suffix}"


class _Collection:
    """One flat photo folder plus the manifest that describes it."""

    def __init__(self, directory: Path, manifest: dict, path: Path):
        self.directory = directory
        self.manifest = manifest
        self.path = path
        self.taken = {entry["name"]: entry["checksum"] for entry in manifest["files"]}

    def add(self, record: dict) -> None:
        self.manifest["files"].append(record)
        self.taken[record["name"]] = record["checksum"]

    def save(self) -> None:
        write_json_atomically(self.path, self.manifest)


def ingest_photos(
    source: Path,
    archive: Path,
    collection: str,
    batch_id: Optional[str] = None,
) -> dict:
    """Copy RAW photos and their editing sidecars into a flat Collection folder."""
    collection = safe_identity(collection, "Collection identity")
    candidates = sorted(
        (path.relative_to(source), path)
        for path in source.rglob("*")
        if path.is_file()
    )
    if not candidates:
        raise ValueError("No files found in the source directory.")

    sizes = {relative.as_posix(): path.stat().st_size for relative, path in candidates}
    batch_id = safe_identity(
        batch_id or batch_identity(source, list(sizes.items())),
        "Import Batch identity",
    )

    collection_path = shoot_directory(archive, collection, "photo")
    collection_path.mkdir(parents=True, exist_ok=True)
    manifest_path = collection_path / MANIFEST_NAME
    pending_path = collection_path / PENDING_MANIFEST_NAME
    manifest = load_manifest(collection_path, collection, "photo")
    primary = _Collection(collection_path, manifest, pending_path)
    collections = {collection_path: primary}

    index = build_checksum_index(archive, "photo")
    recorded = {
        (entry.get("batch_id"), entry.get("source_relative_path")): entry
        for entry in manifest["files"]
    }
    attached = _attach_sidecars(candidates)
    riders: dict[Path, list[tuple[Path, Path, str]]] = {}
    for relative, path in candidates:
        pair = attached.get(relative)
        if pair is not None:
            riders.setdefault(pair[0], []).append((relative, path, pair[1]))

    counts = {"copied": 0, "verified": 0, "deduplicated": 0, "excluded": 0}

    def target_for(location: str) -> _Collection:
        directory = (archive / location).parent
        known = collections.get(directory)
        if known is None:
            known = _Collection(
                directory,
                load_manifest(directory, directory.name, "photo"),
                manifest_source(directory),
            )
            collections[directory] = known
        return known

    def record_exclusion(card_path: str, record: dict) -> None:
        manifest["excluded"] = [
            item
            for item in manifest["excluded"]
            if (item.get("batch_id"), item.get("source_relative_path"))
            != (batch_id, card_path)
        ]
        manifest["excluded"].append(record)
        counts["excluded"] += 1

    def place(
        target: _Collection,
        source_file: Path,
        relative: Path,
        desired: str,
        extra: Optional[dict] = None,
    ) -> None:
        """Land one file in a Collection, reusing an identical copy already sitting there."""
        card_path = relative.as_posix()
        byte_size = sizes[card_path]
        source_checksum = checksum(source_file)
        record = {
            "name": desired,
            "byte_size": byte_size,
            "checksum": source_checksum,
            "source_relative_path": card_path,
            "source_name": source.name,
            "batch_id": batch_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        record.update(extra or {})

        settled = target.directory / desired
        if settled.is_file() and checksum(settled) == source_checksum:
            if target.taken.get(desired) != source_checksum:
                if desired != relative.name:
                    record["original_name"] = relative.name
                target.add(record)
            counts["verified"] += 1
            return

        name = destination_name(desired, set(target.taken), target.directory)
        place_verified(source_file, target.directory / name, expected=source_checksum)
        record["name"] = name
        if name != relative.name:
            record["original_name"] = relative.name
        target.add(record)
        index.setdefault(byte_size, {}).setdefault(
            source_checksum, (target.directory / name).relative_to(archive).as_posix()
        )
        counts["copied"] += 1

    for relative, source_file in candidates:
        card_path = relative.as_posix()
        byte_size = sizes[card_path]
        ingested_at = datetime.now(timezone.utc).isoformat()

        if relative in attached:
            continue

        reason = _exclusion_reason(relative, attached=False)
        if reason is not None:
            record_exclusion(
                card_path,
                {
                    "source_relative_path": card_path,
                    "byte_size": byte_size,
                    "reason": reason,
                    "batch_id": batch_id,
                    "ingested_at": ingested_at,
                },
            )
            primary.save()
            continue

        target = primary
        stored: Optional[str] = None
        source_checksum: Optional[str] = None

        entry = recorded.get((batch_id, card_path))
        if entry is not None:
            archived = collection_path / relative_path(entry["name"])
            if archived.is_file() and checksum(archived) == entry["checksum"]:
                stored = entry["name"]
                counts["verified"] += 1
            else:
                manifest["files"].remove(entry)
                primary.taken.pop(entry["name"], None)
                index.get(entry["byte_size"], {}).pop(entry["checksum"], None)

        if stored is None:
            known = index.get(byte_size, {})
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
                    counts["deduplicated"] += 1
                    target = target_for(existing)
                    stored = Path(existing).name

        if stored is None:
            name = destination_name(relative.name, set(primary.taken), collection_path)
            stored_checksum = place_verified(
                source_file, collection_path / name, expected=source_checksum
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
            primary.add(record)
            index.setdefault(byte_size, {}).setdefault(
                stored_checksum, (collection_path / name).relative_to(archive).as_posix()
            )
            counts["copied"] += 1
            stored = name

        for sidecar, sidecar_file, mode in riders.get(relative, []):
            place(
                target,
                sidecar_file,
                sidecar,
                _sidecar_name(stored, mode, sidecar.suffix),
                {"sidecar_for": stored},
            )
            if target is not primary:
                target.save()
        primary.save()

    primary.save()
    for other in collections.values():
        if other is not primary:
            other.save()
    os.replace(pending_path, manifest_path)

    return {
        "collection": collection,
        "batch_id": batch_id,
        "collection_directory": collection_path,
        "manifest_path": manifest_path,
        "files": len(manifest["files"]),
        **counts,
    }
