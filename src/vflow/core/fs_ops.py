from pathlib import Path
from typing import Set, Tuple

import shutil
import typer


def copy_and_verify(source: Path, dest: Path) -> bool:
    """Copies a file and verifies its existence."""
    try:
        shutil.copy2(source, dest)
        if not (dest / source.name).exists():
            typer.echo(f"  [ERROR] Verification failed for {source.name} at {dest}", err=True)
            return False
    except Exception as e:
        typer.echo(f"  [ERROR] Could not copy {source.name} to {dest}: {e}", err=True)
        return False
    return True


def _is_duplicate(file_path: Path, dest_dir: Path) -> bool:
    """
    Check if a file is a duplicate at the destination (by name and size).
    """
    dest_file = dest_dir / file_path.name
    if not dest_file.exists():
        return False

    try:
        source_size = file_path.stat().st_size
        dest_size = dest_file.stat().st_size
        return source_size == dest_size
    except Exception:
        return False


def _build_destination_index(root: Path) -> Set[Tuple[str, int]]:
    """
    Build a set of (filename, size) for all video files under root.
    Used to skip files already ingested anywhere in laptop or archive (cross-shoot).
    """
    video_extensions = {".mp4", ".mov", ".mxf", ".mts", ".avi", ".m4v", ".braw", ".r3d", ".crm"}
    index: Set[Tuple[str, int]] = set()
    if not root.exists():
        return index
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in video_extensions:
            try:
                index.add((f.name, f.stat().st_size))
            except (OSError, FileNotFoundError):
                pass
    return index


def _format_bytes(num: int) -> str:
    """
    Simple human-readable byte formatter.
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"

