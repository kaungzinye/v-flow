from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .core.fs_ops import copy_and_verify, _format_bytes
from .core.patterns import _matches_pattern


def consolidate_files(
    source_dir: str,
    output_folder_name: Optional[str],
    archive_path: Path,
    destination_path: Optional[str] = None,
    file_filter: Optional[list[str]] = None,
    tags: Optional[str] = None,
    preserve_structure: bool = True,
    dry_run: bool = False,
    delete_source: bool = False,
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
    copied_sources: list[Path] = []

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
                    if delete_source:
                        typer.echo(
                            f"WOULD DELETE AFTER COPY (after manual confirmation): {file}"
                        )

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

                        if delete_source:
                            copied_sources.append(file)
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

    if delete_source and copied_sources:
        typer.echo("\nBackup step finished.")
        typer.echo(
            f"{len(copied_sources)} source file(s) are eligible for deletion (only files that were actually copied)."
        )
        confirm = typer.confirm(
            "Do you want to delete these source files from the backup source folder now?"
        )
        if confirm:
            deleted = 0
            delete_errors = 0
            for src in copied_sources:
                try:
                    if src.exists():
                        src.unlink()
                        deleted += 1
                except Exception as e:
                    delete_errors += 1
                    typer.echo(
                        f"⚠ Warning: Could not delete source file {src}: {e}",
                        err=True,
                    )
            typer.echo(f"\nSource cleanup complete. Deleted {deleted} file(s).")
            if delete_errors:
                typer.echo(
                    f"{delete_errors} file(s) could not be deleted. See warnings above.",
                    err=True,
                )
        else:
            typer.echo(
                "\nNo source files were deleted. You can safely inspect the archive and rerun backup with --delete-source later if desired."
            )


def verify_backup(
    source_dir: str,
    dest_dir: str,
    allow_delete: bool = False,
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

    if not allow_delete:
        return

    confirm = typer.confirm(
        "\nDo you want to delete all files under the source folder now?\n"
        f"  Source: {source_path}\n"
    )
    if not confirm:
        typer.echo("\nNo files were deleted. Source remains intact.")
        return

    deleted = 0
    delete_errors = 0
    for f in source_path.rglob("*"):
        if f.is_file():
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                delete_errors += 1
                typer.echo(
                    f"⚠ Warning: Could not delete file {f}: {e}", err=True
                )

    for d in sorted(
        source_path.rglob("*"), key=lambda p: len(str(p)), reverse=True
    ):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass

    typer.echo(f"\nSource cleanup complete. Deleted {deleted} file(s).")
    if delete_errors:
        typer.echo(
            f"{delete_errors} file(s) could not be deleted. See warnings above.",
            err=True,
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


def remove_duplicates(
    root: Path, dry_run: bool = False, max_age_hours: Optional[int] = None
) -> int:
    """
    Within a root folder, find all video files and remove duplicates: same
    (filename, size) in multiple places. Keeps one copy (first by path sort)
    and deletes the rest. Returns number removed. If max_age_hours is set,
    only consider files modified in the last N hours.
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
    removed = 0
    for key, paths in by_key.items():
        if len(paths) <= 1:
            continue
        paths_sorted = sorted(paths, key=lambda p: str(p))
        keep, duplicates = paths_sorted[0], paths_sorted[1:]
        for dup in duplicates:
            if dry_run:
                typer.echo(f"  [dry-run] would remove duplicate: {dup}")
            else:
                try:
                    dup.unlink()
                    try:
                        rel = dup.relative_to(root)
                    except ValueError:
                        rel = dup
                    typer.echo(f"  Removed duplicate: {rel}")
                    removed += 1
                except OSError as e:
                    typer.echo(
                        f"  [ERROR] Could not remove {dup}: {e}", err=True
                    )
    return removed

