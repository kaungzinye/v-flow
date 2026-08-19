from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from string import ascii_lowercase
from typing import Iterable, Optional


CHECKSUM_ALGORITHM = "sha256"
MANIFEST_NAME = ".vflow-manifest.json"
PENDING_MANIFEST_NAME = ".vflow-manifest.pending.json"
MANIFEST_VERSION = 2
EXTRAS_DIRECTORY = ".vflow-extras"
CHUNK_SIZE = 1024 * 1024

# Where each media kind keeps its flat folders, and what the folder identity is
# called inside a manifest.
RAW_SUBPATHS = {"video": ("Video", "RAW"), "photo": ("Photo", "RAW")}
IDENTITY_KEYS = {"video": "shoot", "photo": "collection"}
RAW_SUBPATH = RAW_SUBPATHS["video"]

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

# Photo kinds that ingest accepts into a photo Collection. Editing sidecars carry
# real work, so they ride into the Collection beside the frame they belong to.
PHOTO_EXTENSION_GROUPS = {
    "raw": {".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2"},
    "sidecar": {".pp3", ".xmp"},
}
PHOTO_EXTENSIONS = frozenset(PHOTO_EXTENSION_GROUPS["raw"])
SIDECAR_EXTENSIONS = frozenset(PHOTO_EXTENSION_GROUPS["sidecar"])


def raw_root(archive: Path, kind: str = "video") -> Path:
    """Directory holding every flat folder of one media kind."""
    return archive.joinpath(*RAW_SUBPATHS[kind])


def shoot_directory(archive: Path, shoot: str, kind: str = "video") -> Path:
    return raw_root(archive, kind) / shoot


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


def new_manifest(identity: str, kind: str = "video") -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        IDENTITY_KEYS[kind]: identity,
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


def load_manifest(shoot_path: Path, shoot: str, kind: str = "video") -> dict:
    """Load the folder manifest, preferring pending progress from an interrupted ingest."""
    for name in (PENDING_MANIFEST_NAME, MANIFEST_NAME):
        manifest = read_manifest(shoot_path / name)
        if manifest is not None:
            return manifest
    return new_manifest(shoot, kind)


def manifest_source(shoot_path: Path) -> Path:
    """The manifest file a loaded manifest belongs in, pending progress first."""
    pending = shoot_path / PENDING_MANIFEST_NAME
    return pending if pending.is_file() else shoot_path / MANIFEST_NAME


def write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.vflow-part")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def iter_shoot_manifests(archive: Path, kind: str = "video") -> Iterable[tuple[Path, dict]]:
    """Yield (folder, manifest) for every folder of one media kind carrying a manifest."""
    root = raw_root(archive, kind)
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


def build_checksum_index(archive: Path, kind: str = "video") -> dict[int, dict[str, str]]:
    """Map byte size to checksum to archive-relative location, from folder manifests."""
    index: dict[int, dict[str, str]] = {}
    for shoot_path, manifest in iter_shoot_manifests(archive, kind):
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


def batch_identity(source: Path, entries: list[tuple[str, int]]) -> str:
    """Identity from source name plus card-relative paths and sizes, without reading content."""
    digest = hashlib.sha256()
    for path, byte_size in sorted(entries):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(byte_size).encode("ascii"))
        digest.update(b"\n")
    source_name = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip("-.") or "card"
    return f"{source_name}-{digest.hexdigest()[:12]}"


def copy_hashing(source: Path, temporary: Path) -> str:
    """Copy one file, hashing the single source read."""
    digest = hashlib.new(CHECKSUM_ALGORITHM)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, temporary.open("wb") as writer:
        for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            writer.write(chunk)
    shutil.copystat(source, temporary)
    return digest.hexdigest()


def place_verified(source: Path, destination: Path, expected: Optional[str] = None) -> str:
    """Copy into place and prove the destination by re-hashing it on the archive drive."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.vflow-part")
    try:
        source_checksum = copy_hashing(source, temporary)
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


def suffixed_names(name: str):
    stem, suffix = Path(name).stem, Path(name).suffix
    yield name
    for letter in ascii_lowercase[1:]:
        yield f"{stem}_{letter}{suffix}"
    counter = 2
    while True:
        yield f"{stem}_{counter}{suffix}"
        counter += 1


def destination_name(name: str, taken: set[str], directory: Path) -> str:
    for candidate in suffixed_names(name):
        if candidate not in taken and not (directory / candidate).exists():
            return candidate
    raise ValueError(f"No available destination name for {name}")
