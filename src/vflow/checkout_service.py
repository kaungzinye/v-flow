from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Optional

import typer

from . import config
from .core.fs_ops import _format_bytes
from .import_batch import CONTENTS_DIRECTORY, MANIFEST_NAME


CAMERA_ORIGINALS_DIRECTORY = "Camera Originals"


def _safe_identity(value: str, label: str) -> str:
    if (
        value in {"", ".", ".."}
        or value != value.strip()
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError(f"{label} must be one non-empty path segment")
    return value


def _checksum(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported manifest checksum algorithm: {algorithm}")

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Manifest file paths must be non-empty strings")
    pure_path = PurePosixPath(value)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise ValueError(f"Unsafe manifest file path: {value}")
    return Path(*pure_path.parts)


def _load_checkout_entries(archive: Path, shoot_id: str) -> tuple[Path, list[dict]]:
    shoot_id = _safe_identity(shoot_id, "Shoot identity")
    shoot_directory = archive / CAMERA_ORIGINALS_DIRECTORY / shoot_id
    if not shoot_directory.exists() or not shoot_directory.is_dir():
        raise ValueError(f"Shoot '{shoot_id}' is not present in the Archive: {shoot_directory}")

    batch_directories = sorted(path for path in shoot_directory.iterdir() if path.is_dir())
    if not batch_directories:
        raise ValueError(f"Shoot '{shoot_id}' contains no Import Batches")

    checkout_entries = []
    manifest_paths = set()
    for batch_directory in batch_directories:
        manifest_path = batch_directory / MANIFEST_NAME
        if not manifest_path.is_file():
            raise ValueError(
                f"Import Batch '{batch_directory.name}' has no completed manifest"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Cannot read Archive manifest {manifest_path}: {error}")

        if not isinstance(manifest, dict) or manifest.get("shoot_id") != shoot_id:
            raise ValueError(f"Archive manifest identity does not match Shoot '{shoot_id}'")
        if manifest.get("import_batch_id") != batch_directory.name:
            raise ValueError(
                f"Archive manifest identity does not match Import Batch '{batch_directory.name}'"
            )
        algorithm = manifest.get("checksum_algorithm")
        files = manifest.get("files")
        if not isinstance(algorithm, str) or not isinstance(files, list):
            raise ValueError(f"Archive manifest is incomplete: {manifest_path}")

        for file_entry in files:
            if not isinstance(file_entry, dict):
                raise ValueError(f"Archive manifest has an invalid file entry: {manifest_path}")
            relative_path = _relative_path(file_entry.get("relative_path"))
            manifest_key = (batch_directory.name, relative_path.as_posix())
            if manifest_key in manifest_paths:
                raise ValueError(f"Archive manifest repeats file path: {file_entry.get('relative_path')}")
            manifest_paths.add(manifest_key)
            byte_size = file_entry.get("byte_size")
            expected_checksum = file_entry.get("checksum")
            if (
                not isinstance(byte_size, int)
                or isinstance(byte_size, bool)
                or byte_size < 0
                or not isinstance(expected_checksum, str)
                or not expected_checksum
            ):
                raise ValueError(f"Archive manifest has invalid file metadata: {manifest_path}")

            checkout_entries.append(
                {
                    "import_batch_id": batch_directory.name,
                    "relative_path": relative_path,
                    "source": batch_directory / CONTENTS_DIRECTORY / relative_path,
                    "byte_size": byte_size,
                    "checksum": expected_checksum,
                    "algorithm": algorithm,
                }
            )

    if not checkout_entries:
        raise ValueError(f"Shoot '{shoot_id}' contains no archived files")
    return shoot_directory, checkout_entries


def _plan_working_copy(entries: list[dict], destination: Path) -> dict:
    copy_entries = []
    reused_entries = []
    conflicts = []

    for entry in entries:
        source = entry["source"]
        if not source.is_file():
            raise ValueError(f"Archived Camera Original is missing: {source}")
        if source.stat().st_size != entry["byte_size"]:
            raise ValueError(f"Archived Camera Original has the wrong size: {source}")
        if _checksum(source, entry["algorithm"]) != entry["checksum"]:
            raise ValueError(f"Archived Camera Original failed checksum verification: {source}")

        destination_file = (
            destination
            / entry["import_batch_id"]
            / CONTENTS_DIRECTORY
            / entry["relative_path"]
        )
        planned = dict(entry, destination=destination_file)
        if not destination_file.exists():
            copy_entries.append(planned)
        elif destination_file.is_file() and _checksum(
            destination_file, entry["algorithm"]
        ) == entry["checksum"]:
            reused_entries.append(planned)
        else:
            conflicts.append(destination_file)

    if conflicts:
        listed = "\n".join(f"  - {path}" for path in conflicts)
        raise ValueError(
            "Working Copy conflict: existing content differs from the Archive:\n" + listed
        )

    return {
        "copy_entries": copy_entries,
        "reused_entries": reused_entries,
        "required_bytes": sum(entry["byte_size"] for entry in copy_entries),
        "total_bytes": sum(entry["byte_size"] for entry in entries),
    }


def _copy_verified(entry: dict) -> str:
    source = entry["source"]
    destination = entry["destination"]
    if destination.exists():
        if destination.is_file() and _checksum(
            destination, entry["algorithm"]
        ) == entry["checksum"]:
            return "reused"
        raise ValueError(f"Working Copy conflict at {destination}: existing content differs")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.vflow-part")
    try:
        shutil.copy2(source, temporary)
        if _checksum(temporary, entry["algorithm"]) != entry["checksum"]:
            raise ValueError(f"Working Copy checksum verification failed for {source}")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return "copied"


def _laptop_reserve_bytes(app_config: dict) -> int:
    value = config.get_setting(
        app_config,
        "laptop_free_space_reserve_gb",
        config.DEFAULT_LAPTOP_FREE_SPACE_RESERVE_GB,
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("settings.laptop_free_space_reserve_gb must be a non-negative number")
    return int(value * 1024**3)


def checkout_shoot(
    app_config: dict,
    archive: Path,
    shoot_id: str,
    working_location: Optional[str],
    direct_archive_access: bool,
    dry_run: bool,
) -> dict:
    """Plan or create a checksum-verified Working Copy for one Shoot."""
    if direct_archive_access == bool(working_location):
        raise ValueError(
            "Choose exactly one mode: --working-location <name> or --direct-archive-access"
        )

    shoot_directory, entries = _load_checkout_entries(archive, shoot_id)
    if direct_archive_access:
        return {
            "mode": "direct",
            "shoot_directory": shoot_directory,
            "source_paths": sorted(
                {
                    shoot_directory
                    / entry["import_batch_id"]
                    / CONTENTS_DIRECTORY
                    for entry in entries
                }
            ),
            "files": len(entries),
            "total_bytes": sum(entry["byte_size"] for entry in entries),
        }

    assert working_location is not None
    working_root = config.get_location(app_config, working_location)
    destination = working_root / shoot_id
    plan = _plan_working_copy(entries, destination)
    plan.update(
        {
            "mode": "checkout",
            "working_location": working_location,
            "destination": destination,
            "files": len(entries),
            "dry_run": dry_run,
        }
    )

    if working_location == "laptop":
        reserve_bytes = _laptop_reserve_bytes(app_config)
        free_bytes = shutil.disk_usage(working_root).free
        plan.update({"free_bytes": free_bytes, "reserve_bytes": reserve_bytes})
        if free_bytes - plan["required_bytes"] < reserve_bytes:
            raise ValueError(
                "Laptop capacity preview:\n"
                f"  Additional space required: {_format_bytes(plan['required_bytes'])}\n"
                f"  Free space: {_format_bytes(free_bytes)}\n"
                f"  Free-space reserve: {_format_bytes(reserve_bytes)}\n"
                "Laptop capacity gate failed: the Checkout would violate the configured reserve"
            )

    if dry_run:
        return plan

    copied = 0
    reused_during_copy = 0
    try:
        for entry in plan["copy_entries"]:
            outcome = _copy_verified(entry)
            if outcome == "copied":
                copied += 1
            else:
                reused_during_copy += 1
    except (OSError, ValueError) as error:
        raise ValueError(
            f"Checkout failed: {error}. Verified files remain intact; retry the same Checkout to resume"
        )

    plan["copied"] = copied
    plan["reused"] = len(plan["reused_entries"]) + reused_during_copy
    return plan


def report_checkout(result: dict) -> None:
    """Print a stable, user-facing Checkout or Direct Archive Access summary."""
    if result["mode"] == "direct":
        typer.echo("Direct Archive Access")
        typer.echo(f"Archived Shoot: {result['shoot_directory']}")
        for source_path in result["source_paths"]:
            typer.echo(f"Archived source: {source_path}")
        typer.echo(f"Files available: {result['files']} ({_format_bytes(result['total_bytes'])})")
        typer.echo("Working Copy created: no")
        return

    typer.echo(f"Working location: {result['working_location']}")
    typer.echo(f"Working Copy: {result['destination']}")
    typer.echo(f"Shoot size: {_format_bytes(result['total_bytes'])}")
    typer.echo(f"Additional space required: {_format_bytes(result['required_bytes'])}")
    if "reserve_bytes" in result:
        typer.echo(f"Laptop free space: {_format_bytes(result['free_bytes'])}")
        typer.echo(f"Laptop free-space reserve: {_format_bytes(result['reserve_bytes'])}")

    if result["dry_run"]:
        typer.echo(
            f"Dry run: {len(result['copy_entries'])} files would be copied and "
            f"{len(result['reused_entries'])} verified files would be reused."
        )
    else:
        typer.echo(
            f"Checkout complete: {result['copied']} copied, "
            f"{result['reused']} already verified, {result['files']} total."
        )
