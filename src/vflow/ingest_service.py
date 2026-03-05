from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from .core.date_utils import (
    parse_shoot_date_range,
    format_shoot_name,
    cluster_files_by_date,
)
from .core.fs_ops import copy_and_verify, _build_destination_index, _is_duplicate
from .core.patterns import _extract_number_from_filename, _matches_pattern


def _get_media_date(file_path: Path) -> datetime:
    """
    Extract the date/time from a media file.
    Uses filesystem creation date (birthtime) if available, else modification time.
    """
    try:
        stat = file_path.stat()
        creation_time = getattr(stat, "st_birthtime", None)
        if creation_time:
            return datetime.fromtimestamp(creation_time)
        return datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        return datetime.now()


def _find_existing_shoots(laptop_dest: Path, archive_dest: Path) -> dict:
    """
    Find all existing shoots and their date ranges, tracking where they exist.
    Returns a dict mapping shoot_name -> {
        'date_range': (start_date, end_date),
        'in_laptop': bool,
        'in_archive': bool
    }
    """
    shoots: dict[str, dict] = {}

    if laptop_dest.exists():
        for shoot_dir in laptop_dest.iterdir():
            if shoot_dir.is_dir():
                date_range = parse_shoot_date_range(shoot_dir.name)
                if date_range:
                    shoots[shoot_dir.name] = {
                        "date_range": date_range,
                        "in_laptop": True,
                        "in_archive": False,
                    }

    archive_raw = archive_dest / "Video" / "RAW"
    if archive_raw.exists():
        for shoot_dir in archive_raw.iterdir():
            if shoot_dir.is_dir():
                date_range = parse_shoot_date_range(shoot_dir.name)
                if date_range:
                    if shoot_dir.name in shoots:
                        shoots[shoot_dir.name]["in_archive"] = True
                    else:
                        shoots[shoot_dir.name] = {
                            "date_range": date_range,
                            "in_laptop": False,
                            "in_archive": True,
                        }

    return shoots


def _find_matching_shoot(file_date_range: tuple, existing_shoots: dict) -> Optional[str]:
    """
    Find an existing shoot whose date range contains the file date range.
    Returns shoot name or None.
    """
    file_start, file_end = file_date_range
    for shoot_name, shoot_info in existing_shoots.items():
        shoot_start, shoot_end = shoot_info["date_range"]
        if shoot_start <= file_start and file_end <= shoot_end:
            return shoot_name
    return None


def ingest_report(
    source_dir: str,
    archive_path: Path,
    laptop_path: Optional[Path] = None,
    priority_day: Optional[int] = None,
    priority_month: Optional[int] = None,
) -> None:
    """
    Scans SD card (or source) for video files, compares against BOTH laptop ingest
    and archive, and reports what has not been ingested. A file is considered
    ingested if it exists (same name and size) in either destination.
    Optionally highlights a priority date (e.g. 28th).
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

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
    all_files: list[Path] = []
    for file_path in source_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            all_files.append(file_path)

    if not all_files:
        typer.echo("No video files found in the source directory.", err=True)
        return

    laptop_index: set[tuple[str, int]] = set()
    if laptop_path and laptop_path.exists():
        for f in laptop_path.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    laptop_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    archive_raw = archive_path / "Video" / "RAW"
    archive_index: set[tuple[str, int]] = set()
    if archive_raw.exists():
        for f in archive_raw.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    archive_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    from collections import defaultdict

    by_date: dict[date, list[tuple[Path, int, bool, bool]]] = defaultdict(list)
    for f in all_files:
        try:
            dt = _get_media_date(f)
            d = dt.date()
            size = f.stat().st_size
            key = (f.name, size)
            in_laptop = key in laptop_index
            in_archive = key in archive_index
            by_date[d].append((f, size, in_laptop, in_archive))
        except (OSError, FileNotFoundError):
            continue

    dates_sorted = sorted(by_date.keys())

    typer.echo("\n" + "=" * 70)
    typer.echo("INGEST REPORT (SD CARD = SOURCE OF TRUTH)")
    typer.echo("=" * 70)
    typer.echo(f"SD card: {source_path}")
    typer.echo(f"Laptop:  {laptop_path}")
    typer.echo(f"Archive: {archive_raw}")
    typer.echo(
        f"Total on SD: {len(all_files)}  |  Laptop index: {len(laptop_index)}  |  Archive index: {len(archive_index)}"
    )
    typer.echo("=" * 70)

    not_on_laptop_by_date: dict[date, list] = {}
    not_on_archive_by_date: dict[date, list] = {}
    for d in dates_sorted:
        items = by_date[d]
        on_laptop = sum(1 for _, _, lb, _ in items if lb)
        on_archive = sum(1 for _, _, _, ab in items if ab)
        missing_laptop = [x for x in items if not x[2]]
        missing_archive = [x for x in items if not x[3]]
        not_on_laptop_by_date[d] = missing_laptop
        not_on_archive_by_date[d] = missing_archive
        priority_mark = ""
        if priority_day is not None and d.day == priority_day:
            if priority_month is None or d.month == priority_month:
                priority_mark = "  << PRIORITY"
        typer.echo(
            f"\n{d}  on SD: {len(items)}  |  laptop: {on_laptop}/{len(items)}  |  archive: {on_archive}/{len(items)}{priority_mark}"
        )
        if missing_laptop:
            names = sorted(x[0].name for x in missing_laptop)
            typer.echo(
                "   Missing from laptop:  "
                + (
                    ", ".join(names)
                    if len(names) <= 10
                    else f"{names[0]} .. {names[-1]} ({len(names)} files)"
                )
            )
        if missing_archive:
            names = sorted(x[0].name for x in missing_archive)
            typer.echo(
                "   Missing from archive: "
                + (
                    ", ".join(names)
                    if len(names) <= 10
                    else f"{names[0]} .. {names[-1]} ({len(names)} files)"
                )
            )

    on_both = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if lb and ab
    )
    laptop_only_from_sd = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if lb and not ab
    )
    archive_only_from_sd = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if ab and not lb
    )
    on_neither = sum(
        1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if not lb and not ab
    )

    typer.echo("\n" + "=" * 70)
    typer.echo("SUMMARY (files on SD card)")
    typer.echo("=" * 70)
    typer.echo(f"  On both laptop + archive: {on_both}")
    typer.echo(f"  On laptop only:           {laptop_only_from_sd}")
    typer.echo(f"  On archive only:          {archive_only_from_sd}")
    typer.echo(f"  On neither (not ingested): {on_neither}")
    typer.echo("=" * 70)

    if on_neither > 0:
        typer.echo("\nSUGGESTED INGEST (missing from both):")
        for d in dates_sorted:
            not_ing = [x for x in by_date[d] if not x[2] and not x[3]]
            if not not_ing:
                continue
            names = sorted(x[0].name for x in not_ing)
            nums = [_extract_number_from_filename(n) for n in names]
            nums = [n for n in nums if n is not None]
            if nums:
                typer.echo(
                    f"  {d}:  --files C{min(nums)}-C{max(nums)}  ({len(not_ing)} files)"
                )
    typer.echo("")


def ingest_shoot(
    source_dir: str,
    shoot_name: str,
    laptop_dest: Path,
    archive_dest: Path,
    auto: bool = False,
    force: bool = False,
    skip_laptop: bool = False,
    workspace_dest: Optional[Path] = None,
    split_threshold: int = 0,
    files_filter: Optional[list[str]] = None,
) -> None:
    """
    The core logic for the ingest command with date-aware duplicate detection.
    Supports splitting by time gap, skipping laptop backup, and ingesting to workspace.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

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
    all_files: list[Path] = []
    for file_path in source_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            all_files.append(file_path)

    if not all_files:
        typer.echo("No video files found in the source directory.", err=True)
        return

    if files_filter:
        files_to_ingest: list[Path] = []
        for pattern in files_filter:
            matching = [f for f in all_files if _matches_pattern(pattern, f.name)]
            files_to_ingest.extend(matching)
        files_to_ingest = list(dict.fromkeys(files_to_ingest))

        if not files_to_ingest:
            typer.echo(
                f"⚠ No files found matching filter: {', '.join(files_filter)}", err=True
            )
            typer.echo(f"   Searched {len(all_files)} file(s) in: {source_path}")
            if len(all_files) <= 10:
                typer.echo(
                    f"   Available files: {', '.join([f.name for f in all_files[:10]])}"
                )
            else:
                typer.echo(
                    f"   Sample files: {', '.join([f.name for f in all_files[:5]])}..."
                )
            raise typer.Exit(code=1)

        typer.echo(
            f"\nFound {len(files_to_ingest)} file(s) matching filter (out of {len(all_files)} total)."
        )
    else:
        files_to_ingest = all_files
    typer.echo(f"\nFound {len(files_to_ingest)} video file(s) to ingest.")

    files_with_dates = [(f, _get_media_date(f)) for f in files_to_ingest]

    clusters: list[list[Path]] = []
    if split_threshold > 0:
        clusters = cluster_files_by_date(files_with_dates, split_threshold)
        if len(clusters) > 1:
            typer.echo(
                f"✓ Splitting footage into {len(clusters)} shoots (gap > {split_threshold}h)."
            )
    else:
        clusters = [[f for f, _ in files_with_dates]]

    archive_raw_root = archive_dest / "Video" / "RAW"
    laptop_index = _build_destination_index(laptop_dest)
    archive_index = _build_destination_index(archive_raw_root)
    typer.echo(
        f"Laptop ingest index: {len(laptop_index)} file(s). Archive index: {len(archive_index)} file(s)."
    )

    for i, cluster_files in enumerate(clusters):
        if len(clusters) > 1:
            typer.echo(
                f"\n{'=' * 30} PART {i + 1}/{len(clusters)} {'=' * 30}"
            )

        cluster_dates = [_get_media_date(f) for f in cluster_files]
        min_dt = min(cluster_dates)
        max_dt = max(cluster_dates)
        min_date = min_dt.date()
        max_date = max_dt.date()

        typer.echo(f"Date range: {min_date} to {max_date}")
        typer.echo(f"Files in this shoot: {len(cluster_files)}")

        existing_shoots = _find_existing_shoots(laptop_dest, archive_dest)
        target_shoot_name: Optional[str] = None

        if auto:
            base_name = format_shoot_name(min_date, max_date, "Ingest")
            if len(clusters) > 1:
                target_shoot_name = f"{base_name}_Part{i+1}"
            else:
                file_date_range = (min_date, max_date)
                matching_shoot = _find_matching_shoot(file_date_range, existing_shoots)

                if matching_shoot:
                    target_shoot_name = matching_shoot
                    typer.echo(f"\n✓ Using existing shoot: {target_shoot_name}")
                else:
                    target_shoot_name = base_name
                    typer.echo(f"\n✓ Creating new shoot: {target_shoot_name}")
        else:
            if not shoot_name:
                typer.echo(
                    "Shoot name is required when --auto is not used.", err=True
                )
                raise typer.Exit(code=1)

            if len(clusters) > 1:
                target_shoot_name = f"{shoot_name}_Part{i+1}"
            else:
                target_shoot_name = shoot_name

            if len(clusters) == 1:
                if target_shoot_name in existing_shoots:
                    shoot_info = existing_shoots[target_shoot_name]
                    shoot_start, shoot_end = shoot_info["date_range"]
                    if not (shoot_start <= min_date and max_date <= shoot_end):
                        typer.echo(
                            f"\n⚠ WARNING: Shoot '{target_shoot_name}' exists with date range {shoot_start} to {shoot_end}",
                            err=True,
                        )
                        typer.echo(
                            f"   But files have date range {min_date} to {max_date}",
                            err=True,
                        )
                        if not force:
                            typer.echo(
                                "   Use --force to proceed anyway.", err=True
                            )
                            raise typer.Exit(code=1)

        shoot_exists_info = existing_shoots.get(
            target_shoot_name,
            {
                "in_laptop": False,
                "in_archive": False,
            },
        )

        shoot_in_laptop = shoot_exists_info.get("in_laptop", False)
        shoot_in_archive = shoot_exists_info.get("in_archive", False)

        laptop_shoot_dir = laptop_dest / target_shoot_name
        archive_shoot_dir = archive_dest / "Video" / "RAW" / target_shoot_name
        workspace_shoot_dir = None
        if workspace_dest:
            workspace_shoot_dir = workspace_dest / target_shoot_name / "01_Source"

        copy_to_laptop = not skip_laptop
        copy_to_archive = True
        copy_to_workspace = workspace_dest is not None

        if skip_laptop:
            typer.echo("   Skipping laptop ingest as requested.")

        if shoot_in_archive and not shoot_in_laptop and copy_to_laptop:
            typer.echo(
                f"\n✓ Shoot '{target_shoot_name}' exists in archive but not in ingest.",
                err=True,
            )
            typer.echo(
                "   Will ingest to laptop only (skipping archive copy since it's already archived)."
            )
            copy_to_archive = False

        if copy_to_laptop:
            try:
                if not laptop_shoot_dir.exists():
                    laptop_shoot_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                if e.errno == 28:
                    typer.echo(
                        "  [WARNING] Laptop storage full. Skipping copy to laptop.",
                        err=True,
                    )
                    copy_to_laptop = False
                else:
                    typer.echo(f"Could not create laptop directory: {e}", err=True)
                    raise typer.Exit(code=1)

        if copy_to_archive:
            try:
                if not archive_shoot_dir.exists():
                    archive_shoot_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                typer.echo(f"Could not create archive directory: {e}", err=True)
                raise typer.Exit(code=1)

        if copy_to_workspace:
            try:
                if not workspace_shoot_dir.exists():
                    workspace_shoot_dir.mkdir(parents=True, exist_ok=True)
                (workspace_dest / target_shoot_name / "02_Resolve").mkdir(
                    exist_ok=True
                )
                (workspace_dest / target_shoot_name / "03_Exports").mkdir(
                    exist_ok=True
                )
                (workspace_dest / target_shoot_name / "04_FinalRenders").mkdir(
                    exist_ok=True
                )
                (workspace_dest / target_shoot_name / "05_Graded_Selects").mkdir(
                    exist_ok=True
                )
            except OSError as e:
                if e.errno == 28:
                    typer.echo(
                        "  [WARNING] Workspace storage full. Skipping copy to workspace.",
                        err=True,
                    )
                    copy_to_workspace = False
                else:
                    typer.echo(
                        f"Could not create workspace directories: {e}", err=True
                    )
                    raise typer.Exit(code=1)

        copied_count = 0
        skipped_count = 0
        error_count = 0

        with typer.progressbar(
            cluster_files, label=f"Ingesting {target_shoot_name}"
        ) as progress:
            for file_path in progress:
                try:
                    file_key = (file_path.name, file_path.stat().st_size)
                except OSError:
                    file_key = (file_path.name, 0)

                laptop_dup = (file_key in laptop_index) if copy_to_laptop else False
                archive_dup = (file_key in archive_index) if copy_to_archive else False
                workspace_dup = (
                    _is_duplicate(file_path, workspace_shoot_dir)
                    if copy_to_workspace
                    else False
                )

                all_dups = True
                if copy_to_laptop and not laptop_dup:
                    all_dups = False
                if copy_to_archive and not archive_dup:
                    all_dups = False
                if copy_to_workspace and not workspace_dup:
                    all_dups = False

                if all_dups:
                    skipped_count += 1
                    continue

                file_copied = False

                if copy_to_laptop and not laptop_dup:
                    try:
                        typer.echo(f"  -> Laptop: {laptop_shoot_dir}")
                        if copy_and_verify(file_path, laptop_shoot_dir):
                            file_copied = True
                            laptop_index.add(file_key)
                        else:
                            error_count += 1
                    except OSError as e:
                        if e.errno == 28:
                            typer.echo(
                                "  [WARNING] Laptop storage full. Skipping copy to laptop.",
                                err=True,
                            )
                            copy_to_laptop = False
                        else:
                            typer.echo(
                                f"  [ERROR] Copy to laptop failed: {e}", err=True
                            )
                            error_count += 1

                if copy_to_archive and not archive_dup:
                    try:
                        typer.echo(f"  -> Archive: {archive_shoot_dir}")
                        if copy_and_verify(file_path, archive_shoot_dir):
                            file_copied = True
                            archive_index.add(file_key)
                        else:
                            error_count += 1
                    except OSError as e:
                        if e.errno == 28:
                            typer.echo(
                                f"  [CRITICAL] Archive storage full. Cannot backup {file_path.name}!",
                                err=True,
                            )
                            error_count += 1
                        else:
                            typer.echo(
                                f"  [ERROR] Copy to archive failed: {e}", err=True
                            )
                            error_count += 1

                if copy_to_workspace and not workspace_dup:
                    try:
                        typer.echo(f"  -> Workspace: {workspace_shoot_dir}")
                        if copy_and_verify(file_path, workspace_shoot_dir):
                            file_copied = True
                        else:
                            error_count += 1
                    except OSError as e:
                        if e.errno == 28:
                            typer.echo(
                                "  [WARNING] Workspace storage full. Skipping copy to workspace.",
                                err=True,
                            )
                            copy_to_workspace = False
                        else:
                            typer.echo(
                                f"  [ERROR] Copy to workspace failed: {e}", err=True
                            )
                            error_count += 1

                if file_copied:
                    copied_count += 1

        typer.echo(
            f"Finished {target_shoot_name}: {copied_count} copied, {skipped_count} skipped, {error_count} errors."
        )

    typer.echo(f"\n{'=' * 70}")
    typer.echo("ALL INGEST TASKS COMPLETE")
    typer.echo(f"{'=' * 70}\n")


def prep_shoot(shoot_name: str, laptop_ingest_path: Path, work_ssd_path: Path) -> None:
    """
    Moves a shoot from the ingest area to the working SSD and creates the project structure.
    Checks for existing files and handles partial preps gracefully.
    """
    source_shoot_dir = laptop_ingest_path / shoot_name
    if not source_shoot_dir.exists() or not source_shoot_dir.is_dir():
        typer.echo(
            f"Shoot directory not found at ingest location: {source_shoot_dir}",
            err=True,
        )
        raise typer.Exit(code=1)

    project_dir = work_ssd_path / shoot_name
    source_folder = project_dir / "01_Source"
    resolve_folder = project_dir / "02_Resolve"
    exports_folder = project_dir / "03_Exports"
    final_renders_folder = project_dir / "04_FinalRenders"
    graded_selects_folder = project_dir / "05_Graded_Selects"

    project_exists = project_dir.exists()

    if project_exists:
        typer.echo(f"\n⚠ WARNING: Project folder already exists at: {project_dir}")
        typer.echo("   Will only move files that don't already exist in the project.")
    else:
        typer.echo(f"\n✓ Creating new project structure at: {project_dir}")

    try:
        if not project_exists:
            typer.echo("Creating project structure...")
        source_folder.mkdir(parents=True, exist_ok=True)
        resolve_folder.mkdir(exist_ok=True)
        exports_folder.mkdir(exist_ok=True)
        final_renders_folder.mkdir(exist_ok=True)
        graded_selects_folder.mkdir(exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create project directories on work SSD: {e}", err=True)
        raise typer.Exit(code=1)

    video_extensions = {".mp4", ".mov", ".mxf", ".mts", ".avi", ".m4v", ".braw"}
    files_to_move = [
        p
        for p in source_shoot_dir.iterdir()
        if p.is_file() and p.suffix.lower() in video_extensions
    ]

    if not files_to_move:
        typer.echo(
            "No video files found in the source shoot directory to move."
        )
        return

    existing_files: list[str] = []
    if source_folder.exists():
        existing_files = [f.name for f in source_folder.iterdir() if f.is_file()]

    files_already_exist = 0
    files_to_process: list[Path] = []

    for f in files_to_move:
        if f.name in existing_files:
            existing_path = source_folder / f.name
            if existing_path.exists():
                try:
                    if f.stat().st_size == existing_path.stat().st_size:
                        files_already_exist += 1
                        continue
                except Exception:
                    pass
        files_to_process.append(f)

    total_files = len(files_to_move)

    typer.echo(f"\n{'=' * 70}")
    typer.echo("PREP SUMMARY")
    typer.echo(f"{'=' * 70}")
    typer.echo(f"Shoot: {shoot_name}")
    typer.echo(f"Source: {source_shoot_dir}")
    typer.echo(f"Destination: {project_dir}")
    typer.echo(f"Total files in ingest: {total_files}")
    typer.echo(f"Files already in project: {files_already_exist}")
    typer.echo(f"Files to move: {len(files_to_process)}")
    typer.echo(f"{'=' * 70}\n")

    if files_already_exist > 0:
        typer.echo(
            f"⚠ {files_already_exist}/{total_files} files already exist in project. Skipping duplicates."
        )

    if not files_to_process:
        typer.echo("All files already exist in project. Nothing to move.")
        typer.echo("\nPrep complete. Project is ready for editing.")
        return

    typer.echo(f"Moving {len(files_to_process)} video files to {source_folder}...")
    moved_count = 0
    error_count = 0

    with typer.progressbar(files_to_process, label="Prepping") as progress:
        for f in progress:
            try:
                dest_path = source_folder / f.name
                if dest_path.exists():
                    typer.echo(f"\n⚠ SKIPPING (already exists): {f.name}")
                    continue

                shutil.move(str(f), str(source_folder))
                moved_count += 1
            except Exception as e:
                typer.echo(f"\n[ERROR] Could not move {f.name}: {e}", err=True)
                error_count += 1

    typer.echo(f"\n{'=' * 70}")
    typer.echo("PREP COMPLETE")
    typer.echo(f"{'=' * 70}")
    typer.echo(f"Files moved: {moved_count}")
    typer.echo(f"Files skipped (already exist): {files_already_exist}")
    if error_count > 0:
        typer.echo(f"Errors: {error_count}", err=True)
    typer.echo(f"{'=' * 70}\n")
    typer.echo("Project is ready for editing.")


def pull_shoot(
    shoot_name: str,
    work_ssd_path: Path,
    archive_path: Path,
    source_type: str = "raw",
    files_filter: Optional[list[str]] = None,
) -> None:
    """
    Pulls files from archive to the work SSD for editing.
    Creates project structure and copies (doesn't move) files from archive.
    """
    pull_raw = source_type in ("raw", "both")
    pull_selects = source_type in ("selects", "both")

    if not pull_raw and not pull_selects:
        typer.echo(
            f"Invalid source type: {source_type}. Must be 'raw', 'selects', or 'both'.",
            err=True,
        )
        raise typer.Exit(code=1)

    project_dir = work_ssd_path / shoot_name
    source_folder = project_dir / "01_Source"
    resolve_folder = project_dir / "02_Resolve"
    exports_folder = project_dir / "03_Exports"
    final_renders_folder = project_dir / "04_FinalRenders"
    graded_selects_folder = project_dir / "05_Graded_Selects"

    project_exists = project_dir.exists()

    if project_exists:
        typer.echo(f"\n✓ Project folder already exists at: {project_dir}")
        typer.echo("   Will only copy files that don't already exist in the project.")
    else:
        typer.echo(f"\n✓ Creating new project structure at: {project_dir}")

    try:
        if not project_exists:
            typer.echo("Creating project structure...")
        source_folder.mkdir(parents=True, exist_ok=True)
        resolve_folder.mkdir(exist_ok=True)
        exports_folder.mkdir(exist_ok=True)
        final_renders_folder.mkdir(exist_ok=True)
        graded_selects_folder.mkdir(exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create project directories on work SSD: {e}", err=True)
        raise typer.Exit(code=1)

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
    total_copied = 0
    total_skipped = 0
    total_errors = 0

    sources_to_pull: list[tuple[str, Path, Path]] = []
    if pull_raw:
        archive_raw_dir = archive_path / "Video" / "RAW" / shoot_name
        if archive_raw_dir.exists() and archive_raw_dir.is_dir():
            sources_to_pull.append(("RAW", archive_raw_dir, source_folder))
        else:
            typer.echo(
                f"⚠ Warning: RAW directory not found: {archive_raw_dir}", err=True
            )

    if pull_selects:
        archive_selects_dir = archive_path / "Video" / "Graded_Selects" / shoot_name
        if archive_selects_dir.exists() and archive_selects_dir.is_dir():
            sources_to_pull.append(
                ("Graded Selects", archive_selects_dir, graded_selects_folder)
            )
        else:
            typer.echo(
                f"⚠ Warning: Graded Selects directory not found: {archive_selects_dir}",
                err=True,
            )

    if not sources_to_pull:
        typer.echo(
            f"No source directories found in archive for shoot '{shoot_name}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    for source_label, archive_dir, dest_folder in sources_to_pull:
        typer.echo(f"\n{'=' * 70}")
        typer.echo(f"PULLING FROM {source_label.upper()}")
        typer.echo(f"{'=' * 70}")

        all_files = [
            p
            for p in archive_dir.iterdir()
            if p.is_file() and p.suffix.lower() in video_extensions
        ]

        if not all_files:
            typer.echo(f"No video files found in {source_label} directory: {archive_dir}")
            continue

        if files_filter:
            files_to_copy: list[Path] = []
            for pattern in files_filter:
                matching = [f for f in all_files if _matches_pattern(pattern, f.name)]
                files_to_copy.extend(matching)
            files_to_copy = list(dict.fromkeys(files_to_copy))
        else:
            files_to_copy = all_files

        if not files_to_copy:
            if files_filter:
                typer.echo(
                    f"⚠ No files found matching filter in {source_label}: {', '.join(files_filter)}"
                )
                typer.echo(f"   Searched {len(all_files)} file(s) in: {archive_dir}")
                if len(all_files) <= 10:
                    typer.echo(
                        f"   Available files: {', '.join([f.name for f in all_files[:10]])}"
                    )
                else:
                    typer.echo(
                        f"   Sample files: {', '.join([f.name for f in all_files[:5]])}..."
                    )
            else:
                typer.echo(f"No video files found in {source_label} directory.")
            continue

        existing_files: list[str] = []
        if dest_folder.exists():
            existing_files = [f.name for f in dest_folder.iterdir() if f.is_file()]

        files_already_exist = 0
        files_to_process: list[Path] = []

        for f in files_to_copy:
            if f.name in existing_files:
                existing_path = dest_folder / f.name
                if existing_path.exists():
                    try:
                        if f.stat().st_size == existing_path.stat().st_size:
                            files_already_exist += 1
                            continue
                    except Exception:
                        pass
            files_to_process.append(f)

        total_files = len(files_to_copy)

        typer.echo(f"Archive source: {archive_dir}")
        typer.echo(f"Destination: {dest_folder}")
        typer.echo(f"Total files available: {total_files}")
        typer.echo(f"Files already exist: {files_already_exist}")
        typer.echo(f"Files to copy: {len(files_to_process)}")
        if files_filter:
            typer.echo(f"Filter applied: {', '.join(files_filter)}")

        if files_already_exist > 0:
            typer.echo(
                f"⚠ {files_already_exist}/{total_files} files already exist. Skipping duplicates."
            )

        if not files_to_process:
            typer.echo(f"All files already exist in {dest_folder}. Skipping.")
            continue

        typer.echo(
            f"\nCopying {len(files_to_process)} files from {source_label}..."
        )
        copied_count = 0
        error_count = 0

        with typer.progressbar(
            files_to_process, label=f"Pulling {source_label}"
        ) as progress:
            for f in progress:
                try:
                    dest_path = dest_folder / f.name
                    if dest_path.exists():
                        typer.echo(f"\n⚠ SKIPPING (already exists): {f.name}")
                        total_skipped += 1
                        continue

                    copy_and_verify(f, dest_folder)
                    copied_count += 1
                    total_copied += 1
                except Exception as e:
                    typer.echo(
                        f"\n[ERROR] Could not copy {f.name}: {e}", err=True
                    )
                    error_count += 1
                    total_errors += 1

        typer.echo(
            f"✓ {source_label}: {copied_count} copied, {files_already_exist} skipped"
        )
        total_skipped += files_already_exist

    typer.echo(f"\n{'=' * 70}")
    typer.echo("PULL COMPLETE")
    typer.echo(f"{'=' * 70}")
    typer.echo(f"Total files copied: {total_copied}")
    typer.echo(f"Total files skipped: {total_skipped}")
    if total_errors > 0:
        typer.echo(f"Errors: {total_errors}", err=True)
    typer.echo(f"{'=' * 70}\n")
    typer.echo("Project is ready for editing.")

