from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional


CHECKSUM_ALGORITHM = "sha256"
MANIFEST_NAME = ".vflow-manifest.json"
PENDING_MANIFEST_NAME = ".vflow-manifest.pending.json"
MANIFEST_VERSION = 2
EXTRAS_DIRECTORY = ".vflow-extras"
RAW_SUBPATH = ("Video", "RAW")
CHUNK_SIZE = 1024 * 1024

# Media kinds that ingest accepts into a Shoot folder. Add a kind here to widen
# the include policy; everything else on the card counts as non-footage.
FOOTAGE_EXTENSION_GROUPS = {
    "video": {
        ".mp4",
        ".mov",
        ".mxf",
        ".mts",
        ".m2ts",
        ".avi",
        ".m4v",
        ".braw",
        ".r3d",
        ".crm",
    },
    "audio": {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"},
}
VIDEO_EXTENSIONS = FOOTAGE_EXTENSION_GROUPS["video"]
AUDIO_EXTENSIONS = FOOTAGE_EXTENSION_GROUPS["audio"]
FOOTAGE_EXTENSIONS = frozenset().union(*FOOTAGE_EXTENSION_GROUPS.values())


def raw_root(archive: Path) -> Path:
    """Directory holding every flat Shoot folder."""
    return archive.joinpath(*RAW_SUBPATH)


def shoot_directory(archive: Path, shoot: str) -> Path:
    return raw_root(archive) / shoot


def checksum(path: Path, algorithm: str = CHECKSUM_ALGORITHM) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported manifest checksum algorithm: {algorithm}")
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_identity(value: str, label: str) -> str:
    if (
        value in {"", ".", ".."}
        or value != value.strip()
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError(f"{label} must be one non-empty path segment")
    return value


def relative_path(value: object) -> Path:
    """Turn a manifest-recorded POSIX path into a safe relative Path."""
    if not isinstance(value, str) or not value:
        raise ValueError("Manifest file paths must be non-empty strings")
    pure_path = PurePosixPath(value)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise ValueError(f"Unsafe manifest file path: {value}")
    return Path(*pure_path.parts)


def new_manifest(shoot: str) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        "shoot": shoot,
        "files": [],
        "excluded": [],
        "deduplicated": [],
    }


def read_manifest(path: Path) -> Optional[dict]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        return None
    manifest.setdefault("excluded", [])
    manifest.setdefault("deduplicated", [])
    return manifest


def load_manifest(shoot_path: Path, shoot: str) -> dict:
    """Load the shoot manifest, preferring pending progress from an interrupted ingest."""
    for name in (PENDING_MANIFEST_NAME, MANIFEST_NAME):
        manifest = read_manifest(shoot_path / name)
        if manifest is not None:
            return manifest
    return new_manifest(shoot)


def write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.vflow-part")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def iter_shoot_manifests(archive: Path) -> Iterable[tuple[Path, dict]]:
    """Yield (shoot directory, manifest) for every shoot carrying a manifest."""
    root = raw_root(archive)
    if not root.is_dir():
        return
    for shoot_path in sorted(root.iterdir()):
        if not shoot_path.is_dir():
            continue
        manifest = read_manifest(shoot_path / MANIFEST_NAME)
        if manifest is None:
            manifest = read_manifest(shoot_path / PENDING_MANIFEST_NAME)
        if manifest is not None:
            yield shoot_path, manifest


def build_checksum_index(archive: Path) -> dict[int, dict[str, str]]:
    """Map byte size to checksum to archive-relative location, from shoot manifests."""
    index: dict[int, dict[str, str]] = {}
    for shoot_path, manifest in iter_shoot_manifests(archive):
        for entry in manifest["files"]:
            if not isinstance(entry, dict):
                continue
            size = entry.get("byte_size")
            entry_checksum = entry.get("checksum")
            name = entry.get("name")
            if not isinstance(size, int) or not isinstance(entry_checksum, str) or not name:
                continue
            location = (shoot_path / name).relative_to(archive).as_posix()
            index.setdefault(size, {}).setdefault(entry_checksum, location)
    return index
