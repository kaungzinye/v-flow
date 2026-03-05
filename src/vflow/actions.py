import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import re
import typer

from . import utils_date
from .core.fs_ops import copy_and_verify, _build_destination_index, _is_duplicate, _format_bytes
from .core.patterns import _extract_number_from_filename, _parse_range_pattern, _matches_pattern

def _get_media_date(file_path: Path) -> datetime:
    """
    Extract the date/time from a media file.
    Uses filesystem creation date (birthtime) if available, else modification time.
    """
    try:
        # On macOS, try to get birthtime (creation date)
        stat = file_path.stat()
        creation_time = getattr(stat, 'st_birthtime', None)
        if creation_time:
            return datetime.fromtimestamp(creation_time)
        # Fallback to modification time
        return datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        # Last resort: use current date/time
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
    shoots = {}
    
    # Check laptop ingest folder
    if laptop_dest.exists():
        for shoot_dir in laptop_dest.iterdir():
            if shoot_dir.is_dir():
                date_range = utils_date.parse_shoot_date_range(shoot_dir.name)
                if date_range:
                    shoots[shoot_dir.name] = {
                        'date_range': date_range,
                        'in_laptop': True,
                        'in_archive': False
                    }
    
    # Check archive RAW folder
    archive_raw = archive_dest / "Video" / "RAW"
    if archive_raw.exists():
        for shoot_dir in archive_raw.iterdir():
            if shoot_dir.is_dir():
                date_range = utils_date.parse_shoot_date_range(shoot_dir.name)
                if date_range:
                    if shoot_dir.name in shoots:
                        # Update existing entry to mark it's also in archive
                        shoots[shoot_dir.name]['in_archive'] = True
                    else:
                        # New entry - only in archive
                        shoots[shoot_dir.name] = {
                            'date_range': date_range,
                            'in_laptop': False,
                            'in_archive': True
                        }
    
    return shoots

def _find_matching_shoot(file_date_range: tuple, existing_shoots: dict) -> str:
    """
    Find an existing shoot whose date range contains the file date range.
    Returns shoot name or None.
    """
    file_start, file_end = file_date_range
    for shoot_name, shoot_info in existing_shoots.items():
        shoot_start, shoot_end = shoot_info['date_range']
        # Check if file range fits within shoot range
        if shoot_start <= file_start and file_end <= shoot_end:
            return shoot_name
    return None

def ingest_report(source_dir: str, archive_path: Path, laptop_path: Optional[Path] = None, priority_day: Optional[int] = None, priority_month: Optional[int] = None):
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

    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    all_files = []
    for file_path in source_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            all_files.append(file_path)

    if not all_files:
        typer.echo("No video files found in the source directory.", err=True)
        return

    # Build separate indexes: (filename, size) in laptop and in archive
    laptop_index = set()
    if laptop_path and laptop_path.exists():
        for f in laptop_path.rglob('*'):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    laptop_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    archive_raw = archive_path / "Video" / "RAW"
    archive_index = set()
    if archive_raw.exists():
        for f in archive_raw.rglob('*'):
            if f.is_file() and f.suffix.lower() in video_extensions:
                try:
                    archive_index.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    pass

    # SD card = source of truth. For each file on SD: check laptop, check archive.
    from collections import defaultdict
    by_date = defaultdict(list)  # date -> [(path, size, in_laptop, in_archive), ...]
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
    typer.echo(f"Total on SD: {len(all_files)}  |  Laptop index: {len(laptop_index)}  |  Archive index: {len(archive_index)}")
    typer.echo("=" * 70)

    not_on_laptop_by_date = {}
    not_on_archive_by_date = {}
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
        typer.echo(f"\n{d}  on SD: {len(items)}  |  laptop: {on_laptop}/{len(items)}  |  archive: {on_archive}/{len(items)}{priority_mark}")
        if missing_laptop:
            names = sorted(x[0].name for x in missing_laptop)
            typer.echo(f"   Missing from laptop:  {', '.join(names) if len(names) <= 10 else f'{names[0]} .. {names[-1]} ({len(names)} files)'}")
        if missing_archive:
            names = sorted(x[0].name for x in missing_archive)
            typer.echo(f"   Missing from archive: {', '.join(names) if len(names) <= 10 else f'{names[0]} .. {names[-1]} ({len(names)} files)'}")

    # Summary: what laptop has from SD, what archive has from SD
    on_both = sum(1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if lb and ab)
    laptop_only_from_sd = sum(1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if lb and not ab)
    archive_only_from_sd = sum(1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if ab and not lb)
    on_neither = sum(1 for d in dates_sorted for (_, _, lb, ab) in by_date[d] if not lb and not ab)

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
                typer.echo(f"  {d}:  --files C{min(nums)}-C{max(nums)}  ({len(not_ing)} files)")
    typer.echo("")

def list_duplicates(root: Path, max_age_hours: Optional[int] = None) -> list[tuple[tuple[str, int], list[Path]]]:
    """
    Find all duplicate files (same name + size) under root. Returns list of
    ((name, size), [path1, path2, ...]) for each group with more than one path.
    If max_age_hours is set, only consider files modified in the last N hours.
    """
    import time
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    cutoff = (time.time() - max_age_hours * 3600) if max_age_hours else None
    by_key = {}  # (name, size) -> [path, ...]
    for f in root.rglob('*'):
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

def remove_duplicates(root: Path, dry_run: bool = False, max_age_hours: Optional[int] = None) -> int:
    """
    Within a root folder (e.g. archive Video/RAW or laptop Ingest), find all video
    files and remove duplicates: same (filename, size) in multiple places. Keeps
    one copy (first by path sort) and deletes the rest. Returns number removed.
    If max_age_hours is set, only consider files modified in the last N hours.
    """
    import time
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    cutoff = (time.time() - max_age_hours * 3600) if max_age_hours else None
    by_key = {}  # (name, size) -> [path, ...]
    for f in root.rglob('*'):
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
                    typer.echo(f"  Removed duplicate: {dup.relative_to(root)}")
                    removed += 1
                except OSError as e:
                    typer.echo(f"  [ERROR] Could not remove {dup}: {e}", err=True)
    return removed

def ingest_shoot(source_dir: str, shoot_name: str, laptop_dest: Path, archive_dest: Path, auto: bool = False, force: bool = False, skip_laptop: bool = False, workspace_dest: Optional[Path] = None, split_threshold: int = 0, files_filter: Optional[list[str]] = None):
    """
    The core logic for the ingest command with date-aware duplicate detection.
    Supports splitting by time gap, skipping laptop backup, and ingesting to workspace.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    # 1. Recursively find all video files
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    all_files = []
    for file_path in source_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            all_files.append(file_path)

    if not all_files:
        typer.echo("No video files found in the source directory.", err=True)
        return

    # Apply filter if provided
    if files_filter:
        files_to_ingest = []
        for pattern in files_filter:
            # Use smart matching that handles ranges and zero-padding
            matching = [f for f in all_files if _matches_pattern(pattern, f.name)]
            files_to_ingest.extend(matching)
        # Remove duplicates while preserving order
        files_to_ingest = list(dict.fromkeys(files_to_ingest))
        
        if not files_to_ingest:
            typer.echo(f"⚠ No files found matching filter: {', '.join(files_filter)}", err=True)
            typer.echo(f"   Searched {len(all_files)} file(s) in: {source_path}")
            if len(all_files) <= 10:
                typer.echo(f"   Available files: {', '.join([f.name for f in all_files[:10]])}")
            else:
                typer.echo(f"   Sample files: {', '.join([f.name for f in all_files[:5]])}...")
            raise typer.Exit(code=1)
        
        typer.echo(f"\nFound {len(files_to_ingest)} file(s) matching filter (out of {len(all_files)} total).")
    else:
        files_to_ingest = all_files
    typer.echo(f"\nFound {len(files_to_ingest)} video file(s) to ingest.")

    # 2. Extract dates and prepare clusters
    files_with_dates = [(f, _get_media_date(f)) for f in files_to_ingest]
    
    clusters = []
    if split_threshold > 0:
        clusters = utils_date.cluster_files_by_date(files_with_dates, split_threshold)
        if len(clusters) > 1:
            typer.echo(f"✓ Splitting footage into {len(clusters)} shoots (gap > {split_threshold}h).")
    else:
        clusters = [[f for f, d in files_with_dates]]

    # Global (name, size) indexes so we skip files already ingested anywhere (any shoot)
    archive_raw_root = archive_dest / "Video" / "RAW"
    laptop_index = _build_destination_index(laptop_dest)
    archive_index = _build_destination_index(archive_raw_root)
    typer.echo(f"Laptop ingest index: {len(laptop_index)} file(s). Archive index: {len(archive_index)} file(s).")

    # Process each cluster as a separate shoot
    for i, cluster_files in enumerate(clusters):
        if len(clusters) > 1:
            typer.echo(f"\n{'='*30} PART {i+1}/{len(clusters)} {'='*30}")

        # Calculate dates for this cluster
        cluster_dates = [_get_media_date(f) for f in cluster_files]
        min_dt = min(cluster_dates)
        max_dt = max(cluster_dates)
        min_date = min_dt.date()
        max_date = max_dt.date()
        
        typer.echo(f"Date range: {min_date} to {max_date}")
        typer.echo(f"Files in this shoot: {len(cluster_files)}")

        # 3. Discover existing shoots and determine target shoot folder
        existing_shoots = _find_existing_shoots(laptop_dest, archive_dest)
        
        target_shoot_name = None
        
        if auto:
            # Auto mode: find matching shoot or create new one
            # Use base name from dates
            base_name = utils_date.format_shoot_name(min_date, max_date, "Ingest")
            
            # If splitting, ensure unique names if dates overlap or just for clarity
            if len(clusters) > 1:
                # Check if base_name already implies uniqueness (different dates)
                # If multiple clusters have same date range (e.g. same day), we MUST append suffix
                # To be safe and consistent, if splitting is active, we can append suffix
                # Or we can check if base_name is already taken by another cluster?
                # Simplest: Append _PartX if splitting
                target_shoot_name = f"{base_name}_Part{i+1}"
            else:
                # Normal auto behavior
                file_date_range = (min_date, max_date)
                matching_shoot = _find_matching_shoot(file_date_range, existing_shoots)
                
                if matching_shoot:
                    target_shoot_name = matching_shoot
                    typer.echo(f"\n✓ Using existing shoot: {target_shoot_name}")
                else:
                    target_shoot_name = base_name
                    typer.echo(f"\n✓ Creating new shoot: {target_shoot_name}")
        else:
            # Manual mode
            if not shoot_name:
                typer.echo("Shoot name is required when --auto is not used.", err=True)
                raise typer.Exit(code=1)
            
            if len(clusters) > 1:
                target_shoot_name = f"{shoot_name}_Part{i+1}"
            else:
                target_shoot_name = shoot_name
            
            # Validate date range (skip if splitting, as manual name + part is new)
            # Only validate if we are NOT splitting or if it's the only cluster
            if len(clusters) == 1:
                if target_shoot_name in existing_shoots:
                    shoot_info = existing_shoots[target_shoot_name]
                    shoot_start, shoot_end = shoot_info['date_range']
                    if not (shoot_start <= min_date and max_date <= shoot_end):
                        typer.echo(f"\n⚠ WARNING: Shoot '{target_shoot_name}' exists with date range {shoot_start} to {shoot_end}", err=True)
                        typer.echo(f"   But files have date range {min_date} to {max_date}", err=True)
                        if not force:
                            typer.echo("   Use --force to proceed anyway.", err=True)
                            raise typer.Exit(code=1)

        # Check where target shoot exists
        shoot_exists_info = existing_shoots.get(target_shoot_name, {
            'in_laptop': False,
            'in_archive': False
        })
        
        shoot_in_laptop = shoot_exists_info.get('in_laptop', False)
        shoot_in_archive = shoot_exists_info.get('in_archive', False)
        
        # Prepare destinations
        laptop_shoot_dir = laptop_dest / target_shoot_name
        archive_shoot_dir = archive_dest / "Video" / "RAW" / target_shoot_name
        workspace_shoot_dir = None
        if workspace_dest:
            workspace_shoot_dir = workspace_dest / target_shoot_name / "01_Source"

        # Determine copy strategy
        copy_to_laptop = not skip_laptop
        copy_to_archive = True
        copy_to_workspace = workspace_dest is not None

        if skip_laptop:
            typer.echo("   Skipping laptop ingest as requested.")
            
        if shoot_in_archive and not shoot_in_laptop and copy_to_laptop:
            typer.echo(f"\n✓ Shoot '{target_shoot_name}' exists in archive but not in ingest.", err=True)
            typer.echo("   Will ingest to laptop only (skipping archive copy since it's already archived).")
            copy_to_archive = False

        # Create directories
        # Laptop
        if copy_to_laptop:
            try:
                if not laptop_shoot_dir.exists():
                    laptop_shoot_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                if e.errno == 28:
                    typer.echo(f"  [WARNING] Laptop storage full. Skipping copy to laptop.", err=True)
                    copy_to_laptop = False
                else:
                    typer.echo(f"Could not create laptop directory: {e}", err=True)
                    raise typer.Exit(code=1)

        # Archive (Critical)
        if copy_to_archive:
            try:
                if not archive_shoot_dir.exists():
                    archive_shoot_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                typer.echo(f"Could not create archive directory: {e}", err=True)
                raise typer.Exit(code=1)
                
        # Workspace
        if copy_to_workspace:
            try:
                if not workspace_shoot_dir.exists():
                    workspace_shoot_dir.mkdir(parents=True, exist_ok=True)
                # Also create other project folders if ingesting to workspace
                (workspace_dest / target_shoot_name / "02_Resolve").mkdir(exist_ok=True)
                (workspace_dest / target_shoot_name / "03_Exports").mkdir(exist_ok=True)
                (workspace_dest / target_shoot_name / "04_FinalRenders").mkdir(exist_ok=True)
                (workspace_dest / target_shoot_name / "05_Graded_Selects").mkdir(exist_ok=True)
            except OSError as e:
                if e.errno == 28:
                    typer.echo(f"  [WARNING] Workspace storage full. Skipping copy to workspace.", err=True)
                    copy_to_workspace = False
                else:
                    typer.echo(f"Could not create workspace directories: {e}", err=True)
                    raise typer.Exit(code=1)

        # Ingest files
        copied_count = 0
        skipped_count = 0
        error_count = 0

        with typer.progressbar(cluster_files, label=f"Ingesting {target_shoot_name}") as progress:
            for file_path in progress:
                try:
                    file_key = (file_path.name, file_path.stat().st_size)
                except OSError:
                    file_key = (file_path.name, 0)
                # Check duplicates: global index (any shoot) so 28th already ingested is skipped when ingesting 28+29
                laptop_dup = (file_key in laptop_index) if copy_to_laptop else False
                archive_dup = (file_key in archive_index) if copy_to_archive else False
                workspace_dup = _is_duplicate(file_path, workspace_shoot_dir) if copy_to_workspace else False

                # Skip if all targets are duplicates
                all_dups = True
                if copy_to_laptop and not laptop_dup: all_dups = False
                if copy_to_archive and not archive_dup: all_dups = False
                if copy_to_workspace and not workspace_dup: all_dups = False

                if all_dups:
                    skipped_count += 1
                    continue

                file_copied = False

                # Copy to Laptop
                if copy_to_laptop and not laptop_dup:
                    try:
                        typer.echo(f"  -> Laptop: {laptop_shoot_dir}")
                        if copy_and_verify(file_path, laptop_shoot_dir):
                            file_copied = True
                            laptop_index.add(file_key)
                        else:
                            error_count += 1
                    except OSError as e:
                        if e.errno == 28: # No space left on device
                            typer.echo(f"  [WARNING] Laptop storage full. Skipping copy to laptop.", err=True)
                            copy_to_laptop = False # Disable for subsequent files
                        else:
                            typer.echo(f"  [ERROR] Copy to laptop failed: {e}", err=True)
                            error_count += 1
                
                # Copy to Archive (Primary Backup - Always attempt)
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
                             typer.echo(f"  [CRITICAL] Archive storage full. Cannot backup {file_path.name}!", err=True)
                             error_count += 1
                             # We don't disable archive copy globally because maybe some files fit? 
                             # But usually full is full. Let's keep trying or maybe stop?
                             # For safety, let's just log error.
                        else:
                             typer.echo(f"  [ERROR] Copy to archive failed: {e}", err=True)
                             error_count += 1
                        
                # Copy to Workspace
                if copy_to_workspace and not workspace_dup:
                    try:
                        typer.echo(f"  -> Workspace: {workspace_shoot_dir}")
                        if copy_and_verify(file_path, workspace_shoot_dir):
                            file_copied = True
                        else:
                            error_count += 1
                    except OSError as e:
                        if e.errno == 28: # No space left on device
                            typer.echo(f"  [WARNING] Workspace storage full. Skipping copy to workspace.", err=True)
                            copy_to_workspace = False # Disable for subsequent files
                        else:
                            typer.echo(f"  [ERROR] Copy to workspace failed: {e}", err=True)
                            error_count += 1
                
                if file_copied:
                    copied_count += 1

        typer.echo(f"Finished {target_shoot_name}: {copied_count} copied, {skipped_count} skipped, {error_count} errors.")

    typer.echo(f"\n{'='*70}")
    typer.echo(f"ALL INGEST TASKS COMPLETE")
    typer.echo(f"{'='*70}\n")

def prep_shoot(shoot_name: str, laptop_ingest_path: Path, work_ssd_path: Path):
    """
    Moves a shoot from the ingest area to the working SSD and creates the project structure.
    Checks for existing files and handles partial preps gracefully.
    """
    source_shoot_dir = laptop_ingest_path / shoot_name
    if not source_shoot_dir.exists() or not source_shoot_dir.is_dir():
        typer.echo(f"Shoot directory not found at ingest location: {source_shoot_dir}", err=True)
        raise typer.Exit(code=1)

    # Check if project already exists on work SSD
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

    # Create project structure on the work SSD
    try:
        if not project_exists:
            typer.echo(f"Creating project structure...")
        source_folder.mkdir(parents=True, exist_ok=True)
        resolve_folder.mkdir(exist_ok=True)
        exports_folder.mkdir(exist_ok=True)
        final_renders_folder.mkdir(exist_ok=True)
        graded_selects_folder.mkdir(exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create project directories on work SSD: {e}", err=True)
        raise typer.Exit(code=1)

    # Find files to move from ingest
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw'}
    files_to_move = [p for p in source_shoot_dir.iterdir() if p.is_file() and p.suffix.lower() in video_extensions]

    if not files_to_move:
        typer.echo("No video files found in the source shoot directory to move.")
        return

    # Pre-check: count files that already exist
    existing_files = []
    if source_folder.exists():
        existing_files = [f.name for f in source_folder.iterdir() if f.is_file()]
    
    files_already_exist = 0
    files_to_process = []
    
    for f in files_to_move:
        if f.name in existing_files:
            # Check if it's actually the same file (by size)
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
    
    # Summary
    typer.echo(f"\n{'='*70}")
    typer.echo(f"PREP SUMMARY")
    typer.echo(f"{'='*70}")
    typer.echo(f"Shoot: {shoot_name}")
    typer.echo(f"Source: {source_shoot_dir}")
    typer.echo(f"Destination: {project_dir}")
    typer.echo(f"Total files in ingest: {total_files}")
    typer.echo(f"Files already in project: {files_already_exist}")
    typer.echo(f"Files to move: {len(files_to_process)}")
    typer.echo(f"{'='*70}\n")

    if files_already_exist > 0:
        typer.echo(f"⚠ {files_already_exist}/{total_files} files already exist in project. Skipping duplicates.")

    if not files_to_process:
        typer.echo("All files already exist in project. Nothing to move.")
        typer.echo("\nPrep complete. Project is ready for editing.")
        return

    # Move files from ingest to work SSD
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
    
    # Final summary
    typer.echo(f"\n{'='*70}")
    typer.echo(f"PREP COMPLETE")
    typer.echo(f"{'='*70}")
    typer.echo(f"Files moved: {moved_count}")
    typer.echo(f"Files skipped (already exist): {files_already_exist}")
    if error_count > 0:
        typer.echo(f"Errors: {error_count}", err=True)
    typer.echo(f"{'='*70}\n")
    typer.echo("Project is ready for editing.")

def pull_shoot(shoot_name: str, work_ssd_path: Path, archive_path: Path, source_type: str = "raw", files_filter: Optional[list[str]] = None):
    """
    Pulls files from archive to the work SSD for editing.
    Creates project structure and copies (doesn't move) files from archive.
    
    Args:
        shoot_name: Name of the shoot to pull
        work_ssd_path: Path to work SSD
        archive_path: Path to archive HDD
        source_type: What to pull - "raw", "selects", or "both"
        files_filter: Optional list of filenames or patterns to filter which files to pull
    """
    # Determine which sources to pull from
    pull_raw = source_type in ("raw", "both")
    pull_selects = source_type in ("selects", "both")
    
    if not pull_raw and not pull_selects:
        typer.echo(f"Invalid source type: {source_type}. Must be 'raw', 'selects', or 'both'.", err=True)
        raise typer.Exit(code=1)

    # Check if project already exists on work SSD
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

    # Create project structure on the work SSD
    try:
        if not project_exists:
            typer.echo(f"Creating project structure...")
        source_folder.mkdir(parents=True, exist_ok=True)
        resolve_folder.mkdir(exist_ok=True)
        exports_folder.mkdir(exist_ok=True)
        final_renders_folder.mkdir(exist_ok=True)
        graded_selects_folder.mkdir(exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create project directories on work SSD: {e}", err=True)
        raise typer.Exit(code=1)

    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    total_copied = 0
    total_skipped = 0
    total_errors = 0
    
    # Track what we're pulling
    sources_to_pull = []
    if pull_raw:
        archive_raw_dir = archive_path / "Video" / "RAW" / shoot_name
        if archive_raw_dir.exists() and archive_raw_dir.is_dir():
            sources_to_pull.append(("RAW", archive_raw_dir, source_folder))
        else:
            typer.echo(f"⚠ Warning: RAW directory not found: {archive_raw_dir}", err=True)
    
    if pull_selects:
        archive_selects_dir = archive_path / "Video" / "Graded_Selects" / shoot_name
        if archive_selects_dir.exists() and archive_selects_dir.is_dir():
            sources_to_pull.append(("Graded Selects", archive_selects_dir, graded_selects_folder))
        else:
            typer.echo(f"⚠ Warning: Graded Selects directory not found: {archive_selects_dir}", err=True)
    
    if not sources_to_pull:
        typer.echo(f"No source directories found in archive for shoot '{shoot_name}'.", err=True)
        raise typer.Exit(code=1)
    
    # Process each source
    for source_label, archive_dir, dest_folder in sources_to_pull:
        typer.echo(f"\n{'='*70}")
        typer.echo(f"PULLING FROM {source_label.upper()}")
        typer.echo(f"{'='*70}")
        
        # Find files to copy from this archive location
        all_files = [p for p in archive_dir.iterdir() if p.is_file() and p.suffix.lower() in video_extensions]
        
        if not all_files:
            typer.echo(f"No video files found in {source_label} directory: {archive_dir}")
            continue
        
        # Apply filter if provided
        if files_filter:
            files_to_copy = []
            for pattern in files_filter:
                # Use smart matching that handles ranges and zero-padding
                matching = [f for f in all_files if _matches_pattern(pattern, f.name)]
                files_to_copy.extend(matching)
            # Remove duplicates while preserving order
            files_to_copy = list(dict.fromkeys(files_to_copy))
        else:
            files_to_copy = all_files

        if not files_to_copy:
            if files_filter:
                typer.echo(f"⚠ No files found matching filter in {source_label}: {', '.join(files_filter)}")
                typer.echo(f"   Searched {len(all_files)} file(s) in: {archive_dir}")
                if len(all_files) <= 10:
                    typer.echo(f"   Available files: {', '.join([f.name for f in all_files[:10]])}")
                else:
                    typer.echo(f"   Sample files: {', '.join([f.name for f in all_files[:5]])}...")
            else:
                typer.echo(f"No video files found in {source_label} directory.")
            continue

        # Pre-check: count files that already exist
        existing_files = []
        if dest_folder.exists():
            existing_files = [f.name for f in dest_folder.iterdir() if f.is_file()]
        
        files_already_exist = 0
        files_to_process = []
        
        for f in files_to_copy:
            if f.name in existing_files:
                # Check if it's actually the same file (by size)
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
        
        # Summary for this source
        typer.echo(f"Archive source: {archive_dir}")
        typer.echo(f"Destination: {dest_folder}")
        typer.echo(f"Total files available: {total_files}")
        typer.echo(f"Files already exist: {files_already_exist}")
        typer.echo(f"Files to copy: {len(files_to_process)}")
        if files_filter:
            typer.echo(f"Filter applied: {', '.join(files_filter)}")
        
        if files_already_exist > 0:
            typer.echo(f"⚠ {files_already_exist}/{total_files} files already exist. Skipping duplicates.")

        if not files_to_process:
            typer.echo(f"All files already exist in {dest_folder}. Skipping.")
            continue

        # Copy files from archive to work SSD (copy, don't move)
        typer.echo(f"\nCopying {len(files_to_process)} files from {source_label}...")
        copied_count = 0
        error_count = 0
        
        with typer.progressbar(files_to_process, label=f"Pulling {source_label}") as progress:
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
                    typer.echo(f"\n[ERROR] Could not copy {f.name}: {e}", err=True)
                    error_count += 1
                    total_errors += 1
        
        typer.echo(f"✓ {source_label}: {copied_count} copied, {files_already_exist} skipped")
        total_skipped += files_already_exist
    
    # Final summary
    typer.echo(f"\n{'='*70}")
    typer.echo(f"PULL COMPLETE")
    typer.echo(f"{'='*70}")
    typer.echo(f"Total files copied: {total_copied}")
    typer.echo(f"Total files skipped: {total_skipped}")
    if total_errors > 0:
        typer.echo(f"Errors: {total_errors}", err=True)
    typer.echo(f"{'='*70}\n")
    typer.echo("Project is ready for editing.")

def _copy_metadata_from_file(source_file: Path, target_file: Path) -> bool:
    """
    Copy metadata from a source file to a target file using ffmpeg.
    Preserves video/audio streams from target, adds metadata from source.
    Returns True if successful, False otherwise.
    """
    if not source_file.exists() or not target_file.exists():
        return False
    
    # Temporary file to avoid read/write conflicts
    temp_output = target_file.with_name(f"{target_file.stem}_temp_meta{target_file.suffix}")
    
    try:
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', str(target_file),      # Input 0: Target video/audio streams
            '-i', str(source_file),      # Input 1: Source metadata
            '-map', '0:v',               # Map video from input 0
            '-map', '0:a',               # Map audio from input 0
            '-map_metadata', '1',        # Map all metadata from input 1
            '-c:v', 'copy',              # Copy video stream without re-encoding
            '-c:a', 'copy',              # Copy audio stream without re-encoding
            '-y',                        # Overwrite temp file if it exists
            str(temp_output)
        ]
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        
        # Replace the original target file with the new file with metadata
        shutil.move(str(temp_output), str(target_file))
        return True
        
    except FileNotFoundError:
        typer.echo("\nError: ffmpeg not found. Please install it and ensure it's in your PATH.", err=True)
        return False
    except subprocess.CalledProcessError as e:
        typer.echo(f"\nWarning: Could not copy metadata: {e.stderr}", err=True)
        # Clean up temp file on error
        if temp_output.exists():
            temp_output.unlink()
        return False

def _tag_media_file(source_file: Path, tags_str: str) -> Path:
    """
    Helper function to tag a media file with metadata.
    Returns the path to the tagged file.
    """
    tags_list = [tag.strip() for tag in tags_str.split(',')]
    
    # Temporary file for ffmpeg processing
    tagged_file_path = source_file.with_name(f"{source_file.stem}_tagged{source_file.suffix}")

    # Universal metadata with ffmpeg
    typer.echo("Embedding universal metadata with ffmpeg...")
    try:
        ffmpeg_cmd = [
            'ffmpeg', '-i', str(source_file),
            '-metadata', f'comment={tags_str}',
            '-metadata', f'keywords={tags_str}',
            '-codec', 'copy',
            str(tagged_file_path)
        ]
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        typer.echo(f"Error with ffmpeg: {e}", err=True)
        typer.echo("Please ensure ffmpeg is installed and in your PATH.", err=True)
        raise typer.Exit(code=1)

    # macOS Finder tags
    typer.echo("Applying macOS Finder tags...")
    try:
        # A more correct way to set multiple tags:
        tag_plist = ''.join([f'<string>{tag}</string>' for tag in tags_list])
        bplist_cmd = f'xattr -w com.apple.metadata:_kMDItemUserTags \'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><array>{tag_plist}</array></plist>\' "{str(tagged_file_path)}"'
        subprocess.run(bplist_cmd, shell=True, check=True, capture_output=True)

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        typer.echo(f"Could not apply macOS tags: {e}", err=True)
        # This is a non-critical error, so we can continue.
        pass
    
    return tagged_file_path

def archive_file(shoot_name: str, file_name: str, tags_str: str, keep_log: bool, work_ssd_path: Path, archive_path: Path):
    """
    Tags, archives, and cleans up a final rendered file.
    """
    # Define paths
    export_file_path = work_ssd_path / shoot_name / "03_Exports" / file_name
    archive_graded_dir = archive_path / "Video" / "Graded"
    
    # 1. Verify the source file exists
    if not export_file_path.exists():
        typer.echo(f"Export file not found: {export_file_path}", err=True)
        raise typer.Exit(code=1)
        
    # 2. Create destination directories
    try:
        archive_graded_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create destination directories: {e}", err=True)
        raise typer.Exit(code=1)

    # 3. Metadata Tagging
    tagged_file_path = _tag_media_file(export_file_path, tags_str)

    # 4. Archive Copy
    typer.echo(f"Copying tagged file to archive: {archive_graded_dir}")
    if not copy_and_verify(tagged_file_path, archive_graded_dir):
        typer.echo("Aborting cleanup due to copy failure.", err=True)
        tagged_file_path.unlink()  # Clean up temp file
        raise typer.Exit(code=1)
    
    # 5. Cleanup
    # Delete the temporary tagged file
    tagged_file_path.unlink()
    
    # 6. Clean up source files (if keep_log is False)
    if not keep_log:
        try:
            source_folder = work_ssd_path / shoot_name / "01_Source"
            if source_folder.exists():
                typer.echo(f"Cleaning up source files from {source_folder}...")
                video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
                for video_file in source_folder.iterdir():
                    if video_file.is_file() and video_file.suffix.lower() in video_extensions:
                        video_file.unlink()
                        typer.echo(f"Deleted: {video_file.name}")
        except Exception as e:
            typer.echo(f"Warning: Could not clean up source files: {e}", err=True)
    
    typer.echo("\nArchive complete.")

def copy_metadata_folder(source_folder: Path, target_folder: Path):
    """
    Copies metadata from files in source_folder to matching files in target_folder.
    """
    if not target_folder.exists() or not target_folder.is_dir():
        typer.echo(f"Target folder not found: {target_folder}", err=True)
        raise typer.Exit(code=1)
    
    if not source_folder.exists() or not source_folder.is_dir():
        typer.echo(f"Source folder not found: {source_folder}", err=True)
        raise typer.Exit(code=1)
    
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    target_files = [f for f in target_folder.iterdir() if f.is_file() and f.suffix.lower() in video_extensions]
    
    if not target_files:
        typer.echo("No files found in the target directory.")
        return

    success_count = 0
    fail_count = 0

    with typer.progressbar(target_files, label="Processing files") as progress:
        for target_file in progress:
            # Find a source file with the same stem, regardless of extension
            source_files = list(source_folder.glob(f"{target_file.stem}.*"))
            
            if not source_files:
                typer.echo(f"\nWarning: No matching source file found for '{target_file.name}'. Skipping.", err=True)
                fail_count += 1
                continue
            
            source_file = source_files[0] # Use the first match found

            # Temporary file to avoid read/write conflicts
            temp_output = target_file.with_name(f"{target_file.stem}_temp_meta{target_file.suffix}")

            try:
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', str(target_file),      # Input 0: Target video/audio streams
                    '-i', str(source_file),      # Input 1: Source metadata
                    '-map', '0:v',               # Map video from input 0
                    '-map', '0:a',               # Map audio from input 0
                    '-map_metadata', '1',        # Map all metadata from input 1
                    '-c:v', 'copy',              # Copy video stream without re-encoding
                    '-c:a', 'copy',              # Copy audio stream without re-encoding
                    str(temp_output)
                ]
                # Use -y to automatically overwrite the temp file if it exists
                subprocess.run(ffmpeg_cmd + ['-y'], check=True, capture_output=True, text=True)
                
                # Replace the original target file with the new tagged file
                shutil.move(str(temp_output), str(target_file))
                success_count += 1

            except FileNotFoundError:
                typer.echo("\nError: ffmpeg not found. Please install it and ensure it's in your PATH.", err=True)
                raise typer.Exit(code=1)
            except subprocess.CalledProcessError as e:
                typer.echo(f"\nError processing '{target_file.name}': {e.stderr}", err=True)
                fail_count += 1
                # Clean up temp file on error
                if temp_output.exists():
                    temp_output.unlink()

    typer.echo(f"\nMetadata copy complete. {success_count} files updated, {fail_count} files skipped.")

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
):
    """
    Finds unique files from a source directory and copies them to the archive.
    
    Args:
        source_dir: Source directory to scan for files
        output_folder_name: Name of folder to create at archive root (used if destination_path is None)
        archive_path: Path to archive root
        destination_path: Optional path relative to archive root (e.g., "Video/Graded"). If provided, uses this instead of output_folder_name.
        file_filter: Optional list of file/folder names to process. If None, processes all files.
        tags: Optional metadata tags to add to copied files
        preserve_structure: If True, maintains relative paths from source. If False, flattens to destination.
    """
    source_path = Path(source_dir)
    
    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)

    # Determine output path
    if destination_path:
        output_path = archive_path / destination_path
    elif output_folder_name:
        output_path = archive_path / output_folder_name
    else:
        typer.echo("Either --output-folder or --destination must be provided.", err=True)
        raise typer.Exit(code=1)

    # For dry-run we don't actually create anything on disk
    if not dry_run:
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            typer.echo(f"Could not create output directory: {e}", err=True)
            raise typer.Exit(code=1)

    # --- 1. Build index of the archive ---
    typer.echo("Building index of existing archive files (this may take a moment)...")
    archive_index = set()
    all_archive_files = list(archive_path.rglob("*.*")) # Simple glob, can be refined
    with typer.progressbar(all_archive_files, label="Indexing archive") as progress:
        for file in progress:
            if file.is_file():
                try:
                    archive_index.add((file.name, file.stat().st_size))
                except FileNotFoundError:
                    continue # Ignore broken symlinks

    # --- 2. Scan source and filter files ---
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v', '.braw', '.r3d', '.crm'}
    typer.echo(f"Scanning source directory...")
    all_source_files = list(source_path.rglob("*.*"))
    
    # Filter to only video files
    source_files = [f for f in all_source_files if f.is_file() and f.suffix.lower() in video_extensions]
    
    # Apply file_filter if provided
    if file_filter:
        filtered_files = []
        for pattern in file_filter:
            # Check if pattern matches a file or folder in the source
            pattern_path = source_path / pattern
            if pattern_path.exists():
                # It's a specific file or folder - process it
                if pattern_path.is_file() and pattern_path.suffix.lower() in video_extensions:
                    filtered_files.append(pattern_path)
                elif pattern_path.is_dir():
                    # Add all video files in this folder
                    for file_path in pattern_path.rglob('*'):
                        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                            filtered_files.append(file_path)
            else:
                # Use smart matching that handles ranges and zero-padding
                # Check filename and relative path
                for f in source_files:
                    rel_path_str = str(f.relative_to(source_path))
                    # Check if pattern matches filename or any part of the path
                    if (_matches_pattern(pattern, f.name) or 
                        _matches_pattern(pattern, rel_path_str) or
                        any(_matches_pattern(pattern, part) for part in f.relative_to(source_path).parts)):
                        filtered_files.append(f)
        # Remove duplicates while preserving order
        source_files = list(dict.fromkeys(filtered_files))
        
        if not source_files:
            typer.echo(f"⚠ No files found matching filter: {', '.join(file_filter)}", err=True)
            typer.echo(f"   Searched {len(all_source_files)} file(s) in: {source_path}")
            raise typer.Exit(code=1)
        
        typer.echo(f"Found {len(source_files)} file(s) matching filter (out of {len([f for f in all_source_files if f.is_file()])} total).")
    else:
        typer.echo(f"Found {len(source_files)} video file(s) to process.")

    typer.echo(f"{'Dry-run: would copy unique files to' if dry_run else 'Copying unique files to'}: {output_path}")

    copied_count = 0
    skipped_count = 0
    error_count = 0
    copied_sources: list[Path] = []

    if dry_run:
        with typer.progressbar(source_files, label="Analyzing for backup") as progress:
            for file in progress:
                try:
                    # Determine destination path
                    if preserve_structure:
                        rel_path = file.relative_to(source_path)
                        dest_file = output_path / rel_path
                    else:
                        dest_file = output_path / file.name

                    file_id = (file.name, file.stat().st_size)

                    # Check archive-wide duplicates
                    if file_id in archive_index:
                        skipped_count += 1
                        typer.echo(f"SKIP (already in archive): {file}")
                        continue

                    # Check if destination file already exists (by size)
                    if dest_file.exists():
                        try:
                            source_size = file.stat().st_size
                            dest_size = dest_file.stat().st_size
                            if source_size == dest_size:
                                skipped_count += 1
                                typer.echo(f"SKIP (already at destination): {file}")
                                continue
                        except Exception:
                            pass  # If we can't check, treat as would-copy

                    copied_count += 1
                    typer.echo(f"WOULD COPY: {file} -> {dest_file}")
                    if delete_source:
                        typer.echo(f"WOULD DELETE AFTER COPY (after manual confirmation): {file}")

                except FileNotFoundError:
                    continue  # Ignore broken symlinks
                except Exception as e:
                    typer.echo(f"\n[ERROR] Could not analyze {file.name}: {e}", err=True)
                    error_count += 1

        typer.echo("\nBackup dry-run complete.")
        typer.echo(f"{copied_count} file(s) would be copied.")
        typer.echo(f"{skipped_count} file(s) would be skipped as duplicates.")
        if error_count > 0:
            typer.echo(f"Errors during analysis: {error_count}", err=True)
        return

    # Real copy mode with logs
    copied_log_path = output_path / "copied_files.txt"
    skipped_log_path = output_path / "skipped_duplicates.txt"

    with copied_log_path.open("w") as copied_log, skipped_log_path.open("w") as skipped_log:
        with typer.progressbar(source_files, label="Consolidating") as progress:
            for file in progress:
                try:
                    # Determine destination path
                    if preserve_structure:
                        # Maintain relative path from source
                        rel_path = file.relative_to(source_path)
                        dest_file = output_path / rel_path
                        dest_dir = dest_file.parent
                    else:
                        # Flatten to destination root
                        dest_file = output_path / file.name
                        dest_dir = output_path
                    
                    # Ensure destination directory exists
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Check for duplicates
                    file_id = (file.name, file.stat().st_size)
                    if file_id in archive_index:
                        skipped_log.write(f"{file}\n")
                        skipped_count += 1
                        continue
                    
                    # Check if destination file already exists (by size)
                    if dest_file.exists():
                        try:
                            source_size = file.stat().st_size
                            dest_size = dest_file.stat().st_size
                            if source_size == dest_size:
                                skipped_log.write(f"{file}\n")
                                skipped_count += 1
                                continue
                        except Exception:
                            pass  # If we can't check, we'll copy anyway
                    
                    # Copy the file
                    if copy_and_verify(file, dest_dir):
                        copied_log.write(f"{file}\n")
                        # Add to index to handle duplicates within the source itself
                        archive_index.add(file_id)
                        copied_count += 1
                        
                        # Tag the file if tags are provided
                        if tags:
                            try:
                                tagged_file = _tag_media_file(dest_file, tags)
                                # Replace the original with the tagged version
                                shutil.move(str(tagged_file), str(dest_file))
                            except Exception as e:
                                typer.echo(f"\n⚠ Warning: Could not tag {dest_file.name}: {e}", err=True)
                        
                        # Track for potential deletion after all copies complete
                        if delete_source:
                            copied_sources.append(file)
                    else:
                        error_count += 1
                        
                except FileNotFoundError:
                    continue # Ignore broken symlinks
                except Exception as e:
                    typer.echo(f"\n[ERROR] Could not process {file.name}: {e}", err=True)
                    error_count += 1

    typer.echo("\nConsolidation complete.")
    typer.echo(f"{copied_count} unique files copied.")
    typer.echo(f"{skipped_count} duplicate files skipped.")
    if error_count > 0:
        typer.echo(f"Errors: {error_count}", err=True)
    typer.echo(f"See log files in {output_path} for details.")

    # Optional post-copy delete flow with explicit confirmation
    if delete_source and copied_sources:
        typer.echo("\nBackup step finished.")
        typer.echo(f"{len(copied_sources)} source file(s) are eligible for deletion (only files that were actually copied).")
        confirm = typer.confirm("Do you want to delete these source files from the backup source folder now?")
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
                    typer.echo(f"⚠ Warning: Could not delete source file {src}: {e}", err=True)
            typer.echo(f"\nSource cleanup complete. Deleted {deleted} file(s).")
            if delete_errors:
                typer.echo(f"{delete_errors} file(s) could not be deleted. See warnings above.", err=True)
        else:
            typer.echo("\nNo source files were deleted. You can safely inspect the archive and rerun backup with --delete-source later if desired.")


def verify_backup(
    source_dir: str,
    dest_dir: str,
    allow_delete: bool = False,
    archive_wide: bool = False,
) -> None:
    """
    Verify that all files in source_dir exist in dest_dir with the same relative path and size.

    This is a generic "did my backup work?" checker for any two folders.
    Optionally offers to delete the source files if everything matches.
    """
    source_path = Path(source_dir)
    dest_path = Path(dest_dir)

    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)
    if not dest_path.is_dir():
        typer.echo(f"Destination is not a valid directory: {dest_path}", err=True)
        raise typer.Exit(code=1)

    scope_desc = "archive-wide (by name+size anywhere under destination)" if archive_wide else "by relative path"
    typer.echo(
        f"Verifying backup from:\n"
        f"  Source:      {source_path}\n"
        f"  Destination: {dest_path}\n"
        f"  Scope:       {scope_desc}"
    )

    # Build index of destination files
    if archive_wide:
        # Archive-wide: (name, size) anywhere under dest_dir
        dest_index_name_size: set[tuple[str, int]] = set()
        for f in dest_path.rglob("*"):
            if f.is_file():
                try:
                    dest_index_name_size.add((f.name, f.stat().st_size))
                except (OSError, FileNotFoundError):
                    continue
    else:
        # Exact mirror: relative path -> size
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
        typer.echo("\nFiles with size mismatch (relative path | source size -> dest size):")
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

    typer.echo("\nBackup verification PASSED. All source files exist in destination with matching sizes.")

    if not allow_delete:
        return

    # Offer to delete source files now that verification passed
    confirm = typer.confirm(
        f"\nDo you want to delete all files under the source folder now?\n  Source: {source_path}\n"
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
                typer.echo(f"⚠ Warning: Could not delete file {f}: {e}", err=True)

    # Optionally try to remove empty directories
    for d in sorted(source_path.rglob("*"), key=lambda p: len(str(p)), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                # Not empty; leave it
                pass

    typer.echo(f"\nSource cleanup complete. Deleted {deleted} file(s).")
    if delete_errors:
        typer.echo(f"{delete_errors} file(s) could not be deleted. See warnings above.", err=True)


def list_backups(archive_path: Path, subpath: str) -> None:
    """
    List backup folders under a given subpath of the archive with file counts and sizes.

    Example: subpath = "Video/RAW/Desktop_Ingest"
    """
    base = archive_path / subpath

    if not base.exists() or not base.is_dir():
        typer.echo(f"No backup directory found at: {base}")
        return

    typer.echo(f"Listing backups under: {base}")

    backups: list[tuple[str, int, int, float]] = []  # (name, file_count, total_size, latest_mtime)

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

    # Sort by latest_mtime descending (most recently touched first)
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


def restore_folder(source_dir: str, dest_dir: str, dry_run: bool = False, overwrite: bool = False) -> None:
    """
    Restore (copy) a folder tree from source_dir to dest_dir.

    This is the inverse of backup for arbitrary folders: it recreates the directory structure
    and copies files that are missing or (optionally) different in size.
    """
    source_path = Path(source_dir)
    dest_path = Path(dest_dir)

    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)

    try:
        dest_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create destination directory: {dest_path} ({e})", err=True)
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

                    # Sizes differ
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

                    # Overwrite existing file
                    if copy_and_verify(src, dest_dir_path):
                        copied += 1
                    else:
                        errors += 1
                    continue

                # Destination file doesn't exist
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
                typer.echo(f"\n[ERROR] Could not process {src}: {e}", err=True)

    typer.echo("\nRestore summary")
    typer.echo("---------------")
    typer.echo(f"Files considered: {len(files)}")
    typer.echo(f"Copied{' (simulated)' if dry_run else ''}: {copied}")
    typer.echo(f"Skipped (already same): {skipped}")
    typer.echo(f"Conflicts (different, not overwritten): {conflicts}")
    if errors:
        typer.echo(f"Errors: {errors}", err=True)

def create_select_file(shoot_name: str, file_name: str, tags_str: str, work_ssd_path: Path, archive_path: Path):
    """
    Tags a graded select, copies metadata from source, and copies it to the archive and the local SSD selects folder.
    """
    # Define paths
    export_file_path = work_ssd_path / shoot_name / "03_Exports" / file_name
    source_folder = work_ssd_path / shoot_name / "01_Source"
    archive_selects_dir = archive_path / "Video" / "Graded_Selects" / shoot_name
    ssd_selects_dir = work_ssd_path / shoot_name / "05_Graded_Selects"
    
    # 1. Verify the source file exists
    if not export_file_path.exists():
        typer.echo(f"Export file not found: {export_file_path}", err=True)
        raise typer.Exit(code=1)
        
    # 2. Create destination directories
    try:
        archive_selects_dir.mkdir(parents=True, exist_ok=True)
        ssd_selects_dir.mkdir(parents=True, exist_ok=True) # Should already exist from prep
    except Exception as e:
        typer.echo(f"Could not create destination directories: {e}", err=True)
        raise typer.Exit(code=1)

    # 3. Metadata Tagging (add new tags)
    typer.echo("Tagging file with new metadata...")
    tagged_file_path = _tag_media_file(export_file_path, tags_str)
    
    # 4. Copy metadata from source file (01_Source) if available
    source_file = None
    if source_folder.exists():
        # Try to find matching source file by stem (filename without extension)
        source_files = list(source_folder.glob(f"{export_file_path.stem}.*"))
        if source_files:
            source_file = source_files[0]
            typer.echo(f"Copying metadata from source file: {source_file.name}")
            if _copy_metadata_from_file(source_file, tagged_file_path):
                typer.echo("✓ Metadata copied successfully from source file.")
            else:
                typer.echo("⚠ Warning: Could not copy metadata from source file. Continuing with tags only.")
        else:
            typer.echo(f"⚠ No matching source file found in 01_Source for '{export_file_path.stem}'. Skipping metadata copy.")
    else:
        typer.echo(f"⚠ Source folder not found: {source_folder}. Skipping metadata copy.")
    
    # 5. Copy to Archive (with duplicate check)
    typer.echo(f"\nCopying tagged select to archive: {archive_selects_dir}")
    archive_dest_file = archive_selects_dir / tagged_file_path.name
    should_copy_to_archive = True
    if archive_dest_file.exists():
        # Check if it's a duplicate by size
        try:
            if tagged_file_path.stat().st_size == archive_dest_file.stat().st_size:
                typer.echo(f"⚠ File already exists in archive (same size). Skipping archive copy.")
                should_copy_to_archive = False
            else:
                typer.echo(f"⚠ File exists in archive but with different size. Copying anyway.")
        except Exception:
            typer.echo(f"⚠ Could not check size of existing file in archive. Copying anyway.")

    if should_copy_to_archive:
        if not copy_and_verify(tagged_file_path, archive_selects_dir):
            typer.echo("Aborting due to archive copy failure.", err=True)
            tagged_file_path.unlink() # Clean up temp file
            raise typer.Exit(code=1)
        else:
            typer.echo("✓ File copied to archive.")
        
    # 6. Copy to SSD Selects folder (with duplicate check)
    typer.echo(f"Copying tagged select to SSD: {ssd_selects_dir}")
    ssd_dest_file = ssd_selects_dir / tagged_file_path.name
    should_copy_to_ssd = True
    if ssd_dest_file.exists():
        # Check if it's a duplicate by size
        try:
            if tagged_file_path.stat().st_size == ssd_dest_file.stat().st_size:
                typer.echo(f"⚠ File already exists in SSD selects folder (same size). Skipping SSD copy.")
                should_copy_to_ssd = False
            else:
                typer.echo(f"⚠ File exists in SSD selects but with different size. Copying anyway.")
        except Exception:
            typer.echo(f"⚠ Could not check size of existing file on SSD. Copying anyway.")

    if should_copy_to_ssd:
        if not copy_and_verify(tagged_file_path, ssd_selects_dir):
            # This is not a critical failure, the file is archived. Warn the user.
            typer.echo("Warning: Could not copy select to SSD. It is safely in the archive.", err=True)
        else:
            typer.echo("✓ File copied to SSD selects folder.")
    
    # 7. Cleanup
    tagged_file_path.unlink()
    
    typer.echo("\n✓ Create select complete.")
