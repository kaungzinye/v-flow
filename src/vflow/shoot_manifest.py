from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from string import ascii_lowercase
from typing import Iterable, Optional


CHECKSUM_ALGORITHM = "sha256"
MANIFEST_NAME = ".vflow-manifest.json"
PENDING_MANIFEST_NAME = ".vflow-manifest.pending.json"
MANIFEST_VERSION = 2
EXTRAS_DIRECTORY = ".vflow-extras"
CHUNK_SIZE = 1024 * 1024

# Provenance for an entry hashed where it already sat, rather than copied in by
# an Import Batch.
INDEXED_SOURCE = "indexed-in-place"

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
    "compressed": {".jpg", ".jpeg", ".heic"},
    "sidecar": {".pp3", ".xmp"},
}
PHOTO_EXTENSIONS = frozenset(
    PHOTO_EXTENSION_GROUPS["raw"] | PHOTO_EXTENSION_GROUPS["compressed"]
)
SIDECAR_EXTENSIONS = frozenset(PHOTO_EXTENSION_GROUPS["sidecar"])

# Card directories holding camera-generated preview images. Add a camera's
# thumbnail directory name here to keep its previews out of Collections.
THUMBNAIL_DIRECTORIES = {"thmbnl"}


def thumbnail_reason(relative: Path) -> Optional[str]:
    """Why a card file counts as a camera preview rather than a photo, if it does."""
    if relative.suffix.lower() not in PHOTO_EXTENSION_GROUPS["compressed"]:
        return None
    if any(part.lower() in THUMBNAIL_DIRECTORIES for part in relative.parts[:-1]):
        return "camera thumbnail"
    return None


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


def is_partial(manifest: dict) -> bool:
    """Whether a manifest covers only some of its folder's files."""
    return bool(manifest.get("partial"))


def covered_names(manifest: dict) -> set[str]:
    """Folder file names the manifest already carries a checksum for."""
    return {
        entry["name"]
        for entry in manifest["files"]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }


def folder_files(directory: Path) -> list[tuple[str, int]]:
    """Visible file names and byte sizes in a flat folder, read by stat alone."""
    found: list[tuple[str, int]] = []
    try:
        with os.scandir(directory) as scan:
            for entry in scan:
                if entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    found.append((entry.name, entry.stat(follow_symlinks=False).st_size))
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(found)


def uncovered_files(directory: Path, manifest: dict) -> list[tuple[str, int]]:
    """Visible files in a folder that its manifest carries no checksum for."""
    covered = covered_names(manifest)
    return [pair for pair in folder_files(directory) if pair[0] not in covered]


def iter_raw_folders(archive: Path, kind: str = "video") -> Iterable[Path]:
    """Every flat folder of one media kind under its RAW root."""
    root = raw_root(archive, kind)
    if not root.is_dir():
        return
    for path in sorted(root.iterdir()):
        if path.is_dir():
            yield path


def iter_shoot_manifests(archive: Path, kind: str = "video") -> Iterable[tuple[Path, dict]]:
    """Yield (folder, manifest) for every folder of one media kind carrying a manifest."""
    for shoot_path in iter_raw_folders(archive, kind):
        for name in (PENDING_MANIFEST_NAME, MANIFEST_NAME):
            manifest = read_manifest(shoot_path / name)
            if manifest is not None:
                yield shoot_path, manifest
                break


def scan_unindexed(
    archive: Path, kind: str = "video", skip: Iterable[Path] = ()
) -> dict[int, list[Path]]:
    """Map byte size to the RAW-root files no manifest covers, from names and sizes only."""
    skipped = set(skip)
    sized: dict[int, list[Path]] = {}
    for directory in iter_raw_folders(archive, kind):
        if directory in skipped:
            continue
        manifest = load_manifest(directory, directory.name, kind)
        for name, byte_size in uncovered_files(directory, manifest):
            sized.setdefault(byte_size, []).append(directory / name)
    return sized


def indexed_entry(path: Path) -> dict:
    """Hash one file where it sits and describe it as indexed in place."""
    return {
        "name": path.name,
        "byte_size": path.stat().st_size,
        "checksum": checksum(path),
        "source": INDEXED_SOURCE,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }


def add_indexed_entry(directory: Path, manifest: dict, entry: dict) -> None:
    """Fold one indexed entry into a manifest, marking it partial while files remain."""
    manifest["files"] = [
        item
        for item in manifest["files"]
        if not (isinstance(item, dict) and item.get("name") == entry["name"])
    ]
    manifest["files"].append(entry)
    if uncovered_files(directory, manifest):
        manifest["partial"] = True
    else:
        manifest.pop("partial", None)


def index_file(path: Path, kind: str = "video") -> str:
    """Hash one unindexed file and persist its checksum into its folder's manifest."""
    directory = path.parent
    manifest = load_manifest(directory, directory.name, kind)
    entry = indexed_entry(path)
    add_indexed_entry(directory, manifest, entry)
    write_json_atomically(manifest_source(directory), manifest)
    return entry["checksum"]


def resolve_unindexed(
    archive: Path,
    sized: dict[int, list[Path]],
    index: dict[int, dict[str, str]],
    byte_size: int,
    source_checksum: str,
    kind: str = "video",
) -> Optional[str]:
    """Hash size-matched unindexed files one by one until one proves identical.

    A size match is a tripwire, never a skip: every candidate it selects is hashed,
    and the checksum lands in a manifest so no candidate is ever hashed twice.
    """
    candidates = sized.get(byte_size) or []
    while candidates:
        candidate = candidates.pop(0)
        try:
            candidate_checksum = index_file(candidate, kind)
        except OSError:
            continue
        location = candidate.relative_to(archive).as_posix()
        index.setdefault(byte_size, {}).setdefault(candidate_checksum, location)
        if candidate_checksum == source_checksum:
            return location
    return None


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
