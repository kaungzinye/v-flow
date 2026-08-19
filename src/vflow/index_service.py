from __future__ import annotations

from pathlib import Path
from typing import Iterable

import typer

from .shoot_manifest import (
    RAW_SUBPATHS,
    add_indexed_entry,
    covered_names,
    indexed_entry,
    is_partial,
    iter_raw_folders,
    load_manifest,
    manifest_source,
    raw_root,
    uncovered_files,
    write_json_atomically,
)


KINDS = ("video", "photo")


def raw_label(kind: str) -> str:
    return "/".join(RAW_SUBPATHS[kind])


def resolve_target(archive: Path, name: str) -> tuple[Path, str]:
    """Locate one Shoot or Collection by folder name or Archive-relative path."""
    if "/" in name:
        directory = archive / name
        for kind in KINDS:
            if directory.parent == raw_root(archive, kind):
                if not directory.is_dir():
                    raise ValueError(f"No folder at {name} in the Archive")
                return directory, kind
        roots = " or ".join(raw_label(kind) for kind in KINDS)
        raise ValueError(f"Indexing covers {roots} only; {name} sits elsewhere")

    matches = [
        (raw_root(archive, kind) / name, kind)
        for kind in KINDS
        if (raw_root(archive, kind) / name).is_dir()
    ]
    if not matches:
        roots = " or ".join(raw_label(kind) for kind in KINDS)
        raise ValueError(f"No Shoot or Collection named '{name}' under {roots}")
    if len(matches) > 1:
        raise ValueError(
            f"'{name}' names both a Shoot and a Collection; "
            f"give an Archive-relative path such as {raw_label('video')}/{name}"
        )
    return matches[0]


def plan_folder(directory: Path, kind: str) -> dict:
    """What one folder still needs hashed before its Shoot Manifest is complete."""
    manifest = load_manifest(directory, directory.name, kind)
    pending = uncovered_files(directory, manifest)
    return {
        "directory": directory,
        "kind": kind,
        "name": directory.name,
        "location": directory.relative_to(directory.parent.parent.parent).as_posix(),
        "manifest": manifest,
        "pending": pending,
        "files": len(pending),
        "bytes": sum(byte_size for _, byte_size in pending),
        "indexed": len(covered_names(manifest)),
        "partial": is_partial(manifest),
    }


def summarize(plan: dict, hashed: int, manifest_path: Path) -> dict:
    return {
        "name": plan["name"],
        "kind": plan["kind"],
        "location": plan["location"],
        "directory": plan["directory"],
        "files": plan["files"],
        "bytes": plan["bytes"],
        "indexed": plan["indexed"],
        "was_partial": plan["partial"],
        "hashed": hashed,
        "manifest_path": manifest_path,
    }


def index_folder(plan: dict) -> dict:
    """Hash every uncovered file in one folder, saving progress after each one."""
    directory = plan["directory"]
    manifest = plan["manifest"]
    manifest_path = manifest_source(directory)
    hashed = 0
    for name, _ in plan["pending"]:
        add_indexed_entry(directory, manifest, indexed_entry(directory / name))
        write_json_atomically(manifest_path, manifest)
        hashed += 1
    if is_partial(manifest) and not uncovered_files(directory, manifest):
        manifest.pop("partial", None)
        write_json_atomically(manifest_path, manifest)
    return summarize(plan, hashed, manifest_path)


def index_archive(
    archive: Path,
    names: Iterable[str] = (),
    all_folders: bool = False,
    dry_run: bool = False,
) -> dict:
    """Give existing folders a complete Shoot Manifest without touching their contents."""
    names = list(names or [])
    if bool(names) == bool(all_folders):
        raise ValueError("Give --folder for each Shoot or Collection, or --all.")

    if all_folders:
        targets = [
            (directory, kind)
            for kind in KINDS
            for directory in iter_raw_folders(archive, kind)
        ]
    else:
        targets = []
        for name in names:
            target = resolve_target(archive, name)
            if target not in targets:
                targets.append(target)

    plans = [plan_folder(directory, kind) for directory, kind in targets]
    work = [plan for plan in plans if plan["pending"] or plan["partial"]]
    result = {
        "dry_run": dry_run,
        "folder_count": len(work),
        "file_total": sum(plan["files"] for plan in work),
        "byte_total": sum(plan["bytes"] for plan in work),
        "complete": len(plans) - len(work),
        "folders": [],
    }
    if dry_run:
        result["folders"] = [
            summarize(plan, 0, manifest_source(plan["directory"])) for plan in work
        ]
        return result
    result["folders"] = [index_folder(plan) for plan in work]
    return result


def report_index(result: dict) -> None:
    verb = "Would index" if result["dry_run"] else "Indexed"
    typer.echo(
        f"{verb} {result['folder_count']} folder(s): "
        f"{result['file_total']} file(s), {result['byte_total']} bytes to read."
    )
    for folder in result["folders"]:
        state = "partially indexed" if folder["was_partial"] else "unindexed"
        typer.echo(
            f"  {folder['location']} [{state}]: "
            f"{folder['files']} file(s), {folder['bytes']} bytes"
        )
    if result["complete"]:
        typer.echo(
            f"Already carrying a complete Shoot Manifest: {result['complete']} folder(s)."
        )
    if result["dry_run"]:
        typer.echo("Dry run: no file was read and no manifest was written.")
    else:
        typer.echo(
            "Every folder's visible contents are untouched; "
            "indexing adds one hidden Shoot Manifest and moves nothing."
        )
