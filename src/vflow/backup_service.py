from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .core.fs_ops import copy_and_verify, _format_bytes
from .core.patterns import _matches_pattern
from .shoot_manifest import Layout, PHOTO_EXTENSIONS, raw_label, raw_root


def consolidate_files(
    source_dir: str,
    output_folder_name: Optional[str],
    archive_path: Path,
    destination_path: Optional[str] = None,
    file_filter: Optional[list[str]] = None,
    tags: Optional[str] = None,
    preserve_structure: bool = True,
    dry_run: bool = False,
) -> None:
    """
    Finds unique files from a source directory and copies them to the archive.
    """
    source_path = Path(source_dir)

    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)

    if destination_path:
        output_path = archive_path / destination_path
    elif output_folder_name:
        output_path = archive_path / output_folder_name
    else:
        typer.echo(
            "Either --output-folder or --destination must be provided.", err=True
        )
        raise typer.Exit(code=1)

    if not dry_run:
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            typer.echo(f"Could not create output directory: {e}", err=True)
            raise typer.Exit(code=1)

    typer.echo("Building index of existing archive files (this may take a moment)...")
    archive_index: set[tuple[str, int]] = set()
    all_archive_files = list(archive_path.rglob("*.*"))
    with typer.progressbar(all_archive_files, label="Indexing archive") as progress:
        for file in progress:
            if file.is_file():
                try:
                    archive_index.add((file.name, file.stat().st_size))
                except FileNotFoundError:
                    continue

    video_extensions = {
        ".mp4",
        ".mov",
        ".mxf",
        ".mts",
        ".avi",
        ".m4v",
        ".braw",
        ".r3d",
        ".crm",
    }
    typer.echo("Scanning source directory...")
    all_source_files = list(source_path.rglob("*.*"))
    source_files = [
        f
        for f in all_source_files
        if f.is_file() and f.suffix.lower() in video_extensions
    ]

    if file_filter:
        filtered_files: list[Path] = []
        for pattern in file_filter:
            pattern_path = source_path / pattern
            if pattern_path.exists():
                if pattern_path.is_file() and pattern_path.suffix.lower() in video_extensions:
                    filtered_files.append(pattern_path)
                elif pattern_path.is_dir():
                    for file_path in pattern_path.rglob("*"):
                        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                            filtered_files.append(file_path)
            else:
                for f in source_files:
                    rel_path_str = str(f.relative_to(source_path))
                    if (
                        _matches_pattern(pattern, f.name)
                        or _matches_pattern(pattern, rel_path_str)
                        or any(
                            _matches_pattern(pattern, part)
                            for part in f.relative_to(source_path).parts
                        )
                    ):
                        filtered_files.append(f)
        source_files = list(dict.fromkeys(filtered_files))

        if not source_files:
            typer.echo(
                f"⚠ No files found matching filter: {', '.join(file_filter)}", err=True
            )
            typer.echo(
                f"   Searched {len(all_source_files)} file(s) in: {source_path}"
            )
            raise typer.Exit(code=1)

        typer.echo(
            f"Found {len(source_files)} file(s) matching filter (out of {len([f for f in all_source_files if f.is_file()])} total)."
        )
    else:
        typer.echo(f"Found {len(source_files)} video file(s) to process.")

    typer.echo(
        f"{'Dry-run: would copy unique files to' if dry_run else 'Copying unique files to'}: {output_path}"
    )

    copied_count = 0
    skipped_count = 0
    error_count = 0

    if dry_run:
        with typer.progressbar(source_files, label="Analyzing for backup") as progress:
            for file in progress:
                try:
                    if preserve_structure:
                        rel_path = file.relative_to(source_path)
                        dest_file = output_path / rel_path
                    else:
                        dest_file = output_path / file.name

                    file_id = (file.name, file.stat().st_size)

                    if file_id in archive_index:
                        skipped_count += 1
                        typer.echo(f"SKIP (already in archive): {file}")
                        continue

                    if dest_file.exists():
                        try:
                            source_size = file.stat().st_size
                            dest_size = dest_file.stat().st_size
                            if source_size == dest_size:
                                skipped_count += 1
                                typer.echo(
                                    f"SKIP (already at destination): {file}"
                                )
                                continue
                        except Exception:
                            pass

                    copied_count += 1
                    typer.echo(f"WOULD COPY: {file} -> {dest_file}")
                except FileNotFoundError:
                    continue
                except Exception as e:
                    typer.echo(
                        f"\n[ERROR] Could not analyze {file.name}: {e}", err=True
                    )
                    error_count += 1

        typer.echo("\nBackup dry-run complete.")
        typer.echo(f"{copied_count} file(s) would be copied.")
        typer.echo(f"{skipped_count} file(s) would be skipped as duplicates.")
        if error_count > 0:
            typer.echo(f"Errors during analysis: {error_count}", err=True)
        return

    copied_log_path = output_path / "copied_files.txt"
    skipped_log_path = output_path / "skipped_duplicates.txt"

    with copied_log_path.open("w") as copied_log, skipped_log_path.open(
        "w"
    ) as skipped_log:
        with typer.progressbar(source_files, label="Consolidating") as progress:
            for file in progress:
                try:
                    if preserve_structure:
                        rel_path = file.relative_to(source_path)
                        dest_file = output_path / rel_path
                        dest_dir = dest_file.parent
                    else:
                        dest_file = output_path / file.name
                        dest_dir = output_path

                    dest_dir.mkdir(parents=True, exist_ok=True)

                    file_id = (file.name, file.stat().st_size)
                    if file_id in archive_index:
                        skipped_log.write(f"{file}\n")
                        skipped_count += 1
                        continue

                    if dest_file.exists():
                        try:
                            source_size = file.stat().st_size
                            dest_size = dest_file.stat().st_size
                            if source_size == dest_size:
                                skipped_log.write(f"{file}\n")
                                skipped_count += 1
                                continue
                        except Exception:
                            pass

                    if copy_and_verify(file, dest_dir):
                        copied_log.write(f"{file}\n")
                        archive_index.add(file_id)
                        copied_count += 1

                        if tags:
                            from .core.media_ops import tag_media_file

                            try:
                                tagged_file = tag_media_file(dest_file, tags)
                                from shutil import move

                                move(str(tagged_file), str(dest_file))
                            except Exception as e:
                                typer.echo(
                                    f"\n⚠ Warning: Could not tag {dest_file.name}: {e}",
                                    err=True,
                                )

                    else:
                        error_count += 1

                except FileNotFoundError:
                    continue
                except Exception as e:
                    typer.echo(
                        f"\n[ERROR] Could not process {file.name}: {e}", err=True
                    )
                    error_count += 1

    typer.echo("\nConsolidation complete.")
    typer.echo(f"{copied_count} unique files copied.")
    typer.echo(f"{skipped_count} duplicate files skipped.")
    if error_count > 0:
        typer.echo(f"Errors: {error_count}", err=True)
    typer.echo(f"See log files in {output_path} for details.")


def verify_backup(
    source_dir: str,
    dest_dir: str,
    archive_wide: bool = False,
) -> None:
    """
    Verify that all files in source_dir exist in dest_dir with the same relative path and size.
    """
    source_path = Path(source_dir)
    dest_path = Path(dest_dir)

    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)
    if not dest_path.is_dir():
        typer.echo(f"Destination is not a valid directory: {dest_path}", err=True)
        raise typer.Exit(code=1)

    scope_desc = (
        "archive-wide (by name+size anywhere under destination)"
        if archive_wide
        else "by relative path"
    )
    typer.echo(
        "Verifying backup from:\n"
        f"  Source:      {source_path}\n"
        f"  Destination: {dest_path}\n"
        f"  Scope:       {scope_desc}"
    )

    if archive_wide:
        dest_index_name_size: set[tuple[str, int]] = set()
        for f in dest_path.rglob("*"):
            if f.is_file():
                try:
                    dest_index_name_size.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    continue
    else:
        dest_index: dict[Path, int] = {}
        for f in dest_path.rglob("*"):
            if f.is_file():
                try:
                    rel = f.relative_to(dest_path)
                    dest_index[rel] = f.stat().st_size
                except (OSError, FileNotFoundError):
                    continue

    missing: list[Path] = []
    size_mismatch: list[tuple[Path, int, int]] = []
    checked = 0

    for f in source_path.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(source_path)
            size = f.stat().st_size
        except (OSError, FileNotFoundError):
            continue
        checked += 1

        if archive_wide:
            if (f.name, size) not in dest_index_name_size:
                missing.append(rel)
        else:
            dest_size = dest_index.get(rel)
            if dest_size is None:
                missing.append(rel)
            elif dest_size != size:
                size_mismatch.append((rel, size, dest_size))

    typer.echo("\nVerification summary")
    typer.echo("--------------------")
    typer.echo(f"Files checked in source: {checked}")
    typer.echo(f"Missing in destination:  {len(missing)}")
    typer.echo(f"Size mismatches:         {len(size_mismatch)}")

    if missing:
        typer.echo("\nMissing files (relative to source root):")
        for rel in missing[:20]:
            typer.echo(f"  - {rel}")
        if len(missing) > 20:
            typer.echo(f"  ... and {len(missing) - 20} more.")

    if size_mismatch:
        typer.echo(
            "\nFiles with size mismatch (relative path | source size -> dest size):"
        )
        for rel, s_size, d_size in size_mismatch[:20]:
            typer.echo(f"  - {rel} | {s_size} -> {d_size}")
        if len(size_mismatch) > 20:
            typer.echo(f"  ... and {len(size_mismatch) - 20} more.")

    if missing or size_mismatch:
        typer.echo(
            "\nBackup verification FAILED. Some files are missing or differ in size. "
            "Please investigate before deleting anything.",
            err=True,
        )
        return

    typer.echo(
        "\nBackup verification PASSED. All source files exist in destination with matching sizes."
    )


def list_backups(archive_path: Path, subpath: str) -> None:
    """
    List backup folders under a given subpath of the archive with file counts and sizes.
    """
    base = archive_path / subpath

    if not base.exists() or not base.is_dir():
        typer.echo(f"No backup directory found at: {base}")
        return

    typer.echo(f"Listing backups under: {base}")

    backups: list[tuple[str, int, int, float]] = []

    for d in base.iterdir():
        if not d.is_dir():
            continue
        file_count = 0
        total_size = 0
        latest_mtime = 0.0
        for f in d.rglob("*"):
            if f.is_file():
                try:
                    st = f.stat()
                    file_count += 1
                    total_size += st.st_size
                    if st.st_mtime > latest_mtime:
                        latest_mtime = st.st_mtime
                except (OSError, FileNotFoundError):
                    continue
        backups.append((d.name, file_count, total_size, latest_mtime))

    if not backups:
        typer.echo("No backup folders found.")
        return

    backups.sort(key=lambda x: x[3], reverse=True)

    typer.echo("\nBackups:")
    typer.echo("Name\tFiles\tSize\tLast Modified")
    from datetime import datetime

    for name, count, size, mtime in backups:
        if mtime:
            ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        else:
            ts = "-"
        typer.echo(f"{name}\t{count}\t{_format_bytes(size)}\t{ts}")


def restore_folder(
    source_dir: str, dest_dir: str, dry_run: bool = False, overwrite: bool = False
) -> None:
    """
    Restore (copy) a folder tree from source_dir to dest_dir.
    """
    source_path = Path(source_dir)
    dest_path = Path(dest_dir)

    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)

    try:
        dest_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(
            f"Could not create destination directory: {dest_path} ({e})", err=True
        )
        raise typer.Exit(code=1)

    typer.echo(
        f"{'Dry-running' if dry_run else 'Restoring'} folder from:\n"
        f"  Source:      {source_path}\n"
        f"  Destination: {dest_path}\n"
        f"  Overwrite:   {'yes' if overwrite else 'no (skip different existing files)'}"
    )

    files = [f for f in source_path.rglob("*") if f.is_file()]

    if not files:
        typer.echo("No files found in source directory.")
        return

    copied = 0
    skipped = 0
    conflicts = 0
    errors = 0

    with typer.progressbar(files, label="Restoring") as progress:
        for src in progress:
            try:
                rel = src.relative_to(source_path)
                dest_file = dest_path / rel
                dest_dir_path = dest_file.parent
                dest_dir_path.mkdir(parents=True, exist_ok=True)

                src_size = src.stat().st_size

                if dest_file.exists():
                    try:
                        dest_size = dest_file.stat().st_size
                    except (OSError, FileNotFoundError):
                        dest_size = -1

                    if dest_size == src_size:
                        skipped += 1
                        continue

                    if not overwrite:
                        conflicts += 1
                        typer.echo(
                            f"\nConflict (sizes differ, not overwriting): {rel} "
                            f"({src_size} -> {dest_size})"
                        )
                        continue

                    if dry_run:
                        copied += 1
                        typer.echo(f"\nWOULD OVERWRITE: {rel}")
                        continue

                    if copy_and_verify(src, dest_dir_path):
                        copied += 1
                    else:
                        errors += 1
                    continue

                if dry_run:
                    copied += 1
                    typer.echo(f"\nWOULD COPY: {rel}")
                    continue

                if copy_and_verify(src, dest_dir_path):
                    copied += 1
                else:
                    errors += 1

            except Exception as e:
                errors += 1
                typer.echo(
                    f"\n[ERROR] Could not process {src}: {e}", err=True
                )

    typer.echo("\nRestore summary")
    typer.echo("---------------")
    typer.echo(f"Files considered: {len(files)}")
    typer.echo(f"Copied{' (simulated)' if dry_run else ''}: {copied}")
    typer.echo(f"Skipped (already same): {skipped}")
    typer.echo(f"Conflicts (different, not overwritten): {conflicts}")
    if errors:
        typer.echo(f"Errors: {errors}", err=True)


def card_verify(
    source_dir: str,
    archive_path: Path,
    photo_shoot: Optional[str] = None,
    layout: Optional[Layout] = None,
) -> None:
    """
    Verifies card contents against the archive before formatting.

    Videos are checked across the whole footage root by name+size.
    Photos are checked against the one named Collection only,
    to avoid Sony filename-recycling false positives.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    video_folder = source_path / "private" / "M4ROOT" / "CLIP"
    photo_folder = source_path / "DCIM" / "100MSDCF"

    video_extensions = {".mp4", ".mov", ".mxf", ".mts", ".avi", ".m4v", ".braw", ".r3d", ".crm"}
    photo_extensions = PHOTO_EXTENSIONS
    video_label = raw_label("video", layout)
    photo_label = raw_label("photo", layout)

    has_videos = video_folder.exists() and video_folder.is_dir()
    has_photos = photo_folder.exists() and photo_folder.is_dir()

    typer.echo("\n" + "=" * 70)
    typer.echo("CARD VERIFY")
    typer.echo("=" * 70)
    typer.echo(f"Card: {source_path}")

    overall_pass = True

    # VIDEO VERIFICATION
    if has_videos:
        video_files: list[Path] = [
            f for f in video_folder.rglob("*")
            if f.is_file() and f.suffix.lower() in video_extensions
        ]

        archive_video_raw = raw_root(archive_path, "video", layout)
        archive_video_index: set[tuple[str, int]] = set()
        if archive_video_raw.exists():
            for f in archive_video_raw.rglob("*"):
                if f.is_file() and f.suffix.lower() in video_extensions:
                    try:
                        archive_video_index.add((f.name, f.stat().st_size))
                    except (OSError, FileNotFoundError):
                        pass

        missing_videos: list[str] = []
        for f in video_files:
            try:
                key = (f.name, f.stat().st_size)
            except (OSError, FileNotFoundError):
                missing_videos.append(f.name)
                continue
            if key not in archive_video_index:
                missing_videos.append(f.name)

        video_pass = len(missing_videos) == 0
        if not video_pass:
            overall_pass = False

        typer.echo(f"\nVIDEOS  (checked archive-wide under {video_label})")
        typer.echo(f"  On card:       {len(video_files)}")
        typer.echo(f"  In archive:    {len(video_files) - len(missing_videos)}")
        typer.echo(f"  Missing:       {len(missing_videos)}")
        typer.echo(f"  Result:        {'PASS' if video_pass else 'FAIL'}")
        if missing_videos:
            typer.echo("  Missing files:")
            for name in missing_videos[:20]:
                typer.echo(f"    - {name}")
            if len(missing_videos) > 20:
                typer.echo(f"    ... and {len(missing_videos) - 20} more.")
    else:
        typer.echo(f"\nVIDEOS  — card folder not found, skipping ({video_folder})")

    # PHOTO VERIFICATION
    if has_photos:
        if not photo_shoot:
            typer.echo("\nPHOTOS  — skipped (no --photo-shoot provided)")
        else:
            photo_files: list[Path] = [
                f for f in photo_folder.rglob("*")
                if f.is_file() and f.suffix.lower() in photo_extensions
            ]

            shoot_photo_dir = raw_root(archive_path, "photo", layout) / photo_shoot
            shoot_photo_index: set[tuple[str, int]] = set()
            if shoot_photo_dir.exists():
                for f in shoot_photo_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in photo_extensions:
                        try:
                            shoot_photo_index.add((f.name, f.stat().st_size))
                        except (OSError, FileNotFoundError):
                            pass
            else:
                typer.echo(f"\nPHOTOS  — shoot folder not found: {shoot_photo_dir}", err=True)
                overall_pass = False

            missing_photos: list[str] = []
            for f in photo_files:
                try:
                    key = (f.name, f.stat().st_size)
                except (OSError, FileNotFoundError):
                    missing_photos.append(f.name)
                    continue
                if key not in shoot_photo_index:
                    missing_photos.append(f.name)

            photo_pass = len(missing_photos) == 0
            if not photo_pass:
                overall_pass = False

            typer.echo(f"\nPHOTOS  (checked against {photo_label}/{photo_shoot} only)")
            typer.echo(f"  On card:       {len(photo_files)}")
            typer.echo(f"  In shoot:      {len(photo_files) - len(missing_photos)}")
            typer.echo(f"  Missing:       {len(missing_photos)}")
            typer.echo(f"  Result:        {'PASS' if photo_pass else 'FAIL'}")
            if missing_photos:
                typer.echo("  Missing files:")
                for name in missing_photos[:20]:
                    typer.echo(f"    - {name}")
                if len(missing_photos) > 20:
                    typer.echo(f"    ... and {len(missing_photos) - 20} more.")
    else:
        typer.echo(f"\nPHOTOS  — card folder not found, skipping ({photo_folder})")

    typer.echo("\n" + "=" * 70)
    typer.echo(f"OVERALL: {'PASS — safe to format card' if overall_pass else 'FAIL — do not format, files missing from archive'}")
    typer.echo("=" * 70 + "\n")


def list_duplicates(
    root: Path, max_age_hours: Optional[int] = None
) -> list[tuple[tuple[str, int], list[Path]]]:
    """
    Find all duplicate files (same name + size) under root. Returns list of
    ((name, size), [path1, path2, ...]) for each group with more than one path.
    If max_age_hours is set, only consider files modified in the last N hours.
    """
    import time

    video_extensions = {
        ".mp4",
        ".mov",
        ".mxf",
        ".mts",
        ".avi",
        ".m4v",
        ".braw",
        ".r3d",
        ".crm",
    }
    cutoff = (time.time() - max_age_hours * 3600) if max_age_hours else None
    by_key: dict[tuple[str, int], list[Path]] = {}
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in video_extensions:
            try:
                st = f.stat()
                if cutoff is not None and st.st_mtime < cutoff:
                    continue
                key = (f.name, st.st_size)
                by_key.setdefault(key, []).append(f)
            except (OSError, FileNotFoundError):
                pass
    return [(key, paths) for key, paths in by_key.items() if len(paths) > 1]

