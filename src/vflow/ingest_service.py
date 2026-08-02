from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from .core.date_utils import (
    parse_shoot_date_range,
    format_shoot_name,
)
from .core.fs_ops import copy_and_verify
from .core.patterns import _extract_number_from_filename, _matches_pattern
from .import_batch import ingest_import_batch


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
    archive_dest: Path,
    auto: bool = False,
    force: bool = False,
    skip_laptop: bool = False,
    workspace: bool = False,
    split_threshold: int = 0,
    files_filter: Optional[list[str]] = None,
    import_batch_id: Optional[str] = None,
) -> None:
    """Archive a source hierarchy as one immutable, checksum-verified Import Batch."""
    del force, skip_laptop

    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    if workspace:
        typer.echo(
            "Ingest writes only to the Archive. Create a Working Copy with Checkout.",
            err=True,
        )
        raise typer.Exit(code=1)

    all_source_files = [path for path in source_path.rglob("*") if path.is_file()]
    selected_files: Optional[list[Path]] = None
    if files_filter:
        selected_files = []
        for pattern in files_filter:
            selected_files.extend(
                path for path in all_source_files if _matches_pattern(pattern, path.name)
            )
        selected_files = list(dict.fromkeys(selected_files))
        if not selected_files:
            typer.echo(
                f"No files found matching filter: {', '.join(files_filter)}",
                err=True,
            )
            raise typer.Exit(code=1)

    files_for_identity = selected_files if selected_files is not None else all_source_files
    if not files_for_identity:
        typer.echo("No files found in the source directory.", err=True)
        raise typer.Exit(code=1)

    if split_threshold:
        typer.echo(
            "Import Batches preserve one received source hierarchy; --split-by-gap is not supported.",
            err=True,
        )
        raise typer.Exit(code=1)

    target_shoot_name = shoot_name
    if auto:
        dates = [_get_media_date(path) for path in files_for_identity]
        target_shoot_name = format_shoot_name(
            min(dates).date(), max(dates).date(), "Ingest"
        )
    if not target_shoot_name:
        typer.echo("Shoot name is required when --auto is not used.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Archiving source hierarchy as Shoot '{target_shoot_name}'...")
    result = ingest_import_batch(
        source=source_path,
        archive=archive_dest,
        shoot_id=target_shoot_name,
        import_batch_id=import_batch_id,
        selected_files=selected_files,
    )
    typer.echo(
        f"Import Batch '{result['import_batch_id']}': "
        f"{result['copied']} copied, {result['skipped']} already verified, "
        f"{result['files']} total."
    )
    typer.echo(f"Manifest: {result['manifest_path']}")
    typer.echo("Retained copies: 1 (Archive only). The source remains untouched.")


def photo_ingest(
    source_dir: str,
    shoot_name: str,
    archive_path: Path,
) -> None:
    """
    Copies new RAW photo files from source_dir to archive_path/Photo/RAW/<shoot_name>.
    Skips files that already exist in that specific shoot folder by name+size.
    Preserves timestamps using shutil.copy2.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    photo_extensions = {".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2"}

    all_files: list[Path] = []
    for file_path in source_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in photo_extensions:
            all_files.append(file_path)

    if not all_files:
        typer.echo("No RAW photo files found in source directory.", err=True)
        return

    shoot_dir = archive_path / "Photo" / "RAW" / shoot_name
    try:
        shoot_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create shoot directory: {e}", err=True)
        raise typer.Exit(code=1)

    # Build index of files already in this specific shoot folder only (not archive-wide)
    shoot_index: set[tuple[str, int]] = set()
    for f in shoot_dir.iterdir():
        if f.is_file() and f.suffix.lower() in photo_extensions:
            try:
                shoot_index.add((f.name, f.stat().st_size))
            except (OSError, FileNotFoundError):
                pass

    typer.echo(f"\nSource: {source_path}")
    typer.echo(f"Destination: {shoot_dir}")
    typer.echo(f"Found: {len(all_files)} RAW file(s) on card")
    typer.echo(f"Already in shoot folder: {len(shoot_index)} file(s)")

    copied_count = 0
    skipped_count = 0
    error_count = 0

    with typer.progressbar(all_files, label=f"Photo ingest {shoot_name}") as progress:
        for file_path in progress:
            try:
                size = file_path.stat().st_size
            except (OSError, FileNotFoundError):
                error_count += 1
                continue

            key = (file_path.name, size)
            if key in shoot_index:
                skipped_count += 1
                continue

            dest_file = shoot_dir / file_path.name
            try:
                shutil.copy2(str(file_path), str(dest_file))
                shoot_index.add(key)
                copied_count += 1
            except Exception as e:
                typer.echo(f"\n[ERROR] Could not copy {file_path.name}: {e}", err=True)
                error_count += 1

    typer.echo(f"\n{'=' * 70}")
    typer.echo("PHOTO INGEST COMPLETE")
    typer.echo(f"{'=' * 70}")
    typer.echo(f"Copied:  {copied_count}")
    typer.echo(f"Skipped: {skipped_count} (already exist in shoot folder)")
    typer.echo(f"Errors:  {error_count}")
    typer.echo(f"{'=' * 70}\n")


def card_report(
    source_dir: str,
    archive_path: Path,
) -> None:
    """
    Reports what's on a card. Auto-detects video (private/M4ROOT/CLIP) and photo
    (DCIM/100MSDCF) folders, groups files by date, and shows first/last filename,
    count, and whether videos are already in the archive.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    video_folder = source_path / "private" / "M4ROOT" / "CLIP"
    photo_folder = source_path / "DCIM" / "100MSDCF"

    video_extensions = {".mp4", ".mov", ".mxf", ".mts", ".avi", ".m4v", ".braw", ".r3d", ".crm"}
    photo_extensions = {".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2"}

    typer.echo("\n" + "=" * 70)
    typer.echo("CARD REPORT")
    typer.echo("=" * 70)
    typer.echo(f"Card: {source_path}")

    # Build archive-wide video index for presence check
    archive_video_raw = archive_path / "Video" / "RAW"
    archive_video_index: set[tuple[str, int]] = set()
    if archive_video_raw.exists():
        for f in archive_video_raw.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    archive_video_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    from collections import defaultdict

    # VIDEO SECTION
    if video_folder.exists() and video_folder.is_dir():
        video_files: list[Path] = []
        for f in video_folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                video_files.append(f)

        typer.echo(f"\nVIDEOS  ({video_folder})")
        typer.echo("-" * 70)

        if not video_files:
            typer.echo("  No video files found.")
        else:
            by_date: dict = defaultdict(list)
            for f in video_files:
                try:
                    d = _get_media_date(f).date()
                    by_date[d].append(f)
                except Exception:
                    continue

            for d in sorted(by_date.keys()):
                day_files = sorted(by_date[d], key=lambda f: f.name)
                count = len(day_files)
                first = day_files[0].name
                last = day_files[-1].name
                on_archive = sum(
                    1 for f in day_files
                    if (f.name, f.stat().st_size) in archive_video_index
                )
                hdd_label = f"{on_archive}/{count} on HDD" if on_archive > 0 else "NOT on HDD"
                if first == last:
                    typer.echo(f"  {d}  {count} file(s)  [{first}]  {hdd_label}")
                else:
                    typer.echo(f"  {d}  {count} file(s)  [{first} .. {last}]  {hdd_label}")
    else:
        typer.echo(f"\nVIDEOS  — folder not found ({video_folder})")

    # PHOTO SECTION
    if photo_folder.exists() and photo_folder.is_dir():
        photo_files: list[Path] = []
        for f in photo_folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in photo_extensions:
                photo_files.append(f)

        typer.echo(f"\nPHOTOS  ({photo_folder})")
        typer.echo("-" * 70)

        if not photo_files:
            typer.echo("  No RAW photo files found.")
        else:
            by_date_p: dict = defaultdict(list)
            for f in photo_files:
                try:
                    d = _get_media_date(f).date()
                    by_date_p[d].append(f)
                except Exception:
                    continue

            for d in sorted(by_date_p.keys()):
                day_files = sorted(by_date_p[d], key=lambda f: f.name)
                count = len(day_files)
                first = day_files[0].name
                last = day_files[-1].name
                if first == last:
                    typer.echo(f"  {d}  {count} file(s)  [{first}]")
                else:
                    typer.echo(f"  {d}  {count} file(s)  [{first} .. {last}]")
    else:
        typer.echo(f"\nPHOTOS  — folder not found ({photo_folder})")

    typer.echo("\n" + "=" * 70 + "\n")


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
