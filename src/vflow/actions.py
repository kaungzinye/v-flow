import shutil
import typer
from pathlib import Path
import subprocess
from datetime import date
from typing import Optional
import re
from . import utils_date

def copy_and_verify(source: Path, dest: Path):
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

def _get_media_date(file_path: Path) -> date:
    """
    Extract the date from a media file.
    Uses filesystem creation date (birthtime) if available, else modification time.
    """
    try:
        # On macOS, try to get birthtime (creation date)
        stat = file_path.stat()
        creation_time = getattr(stat, 'st_birthtime', None)
        if creation_time:
            return date.fromtimestamp(creation_time)
        # Fallback to modification time
        return date.fromtimestamp(stat.st_mtime)
    except Exception:
        # Last resort: use current date
        return date.today()

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

def _extract_number_from_filename(filename: str) -> Optional[int]:
    """
    Extract the first numeric sequence from a filename.
    Returns the number as an integer, or None if no number found.
    Handles zero-padding by extracting the numeric value.
    """
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    return None

def _parse_range_pattern(pattern: str) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Parse a range pattern like "C3317-C3351" or "3317-3351" or "C3317-3351".
    Returns (prefix, start_num, end_num) or (None, None, None) if not a range.
    """
    # Pattern to match ranges like "C3317-C3351" or "3317-3351" or "C3317-3351"
    # The pattern can have a prefix before the first number, and optionally before the second
    pattern_upper = pattern.upper()
    
    # Try pattern with prefix on both sides: "C3317-C3351"
    range_match = re.match(r'^([A-Za-z]*?)(\d+)-([A-Za-z]*?)(\d+)$', pattern_upper)
    if range_match:
        prefix1 = range_match.group(1) if range_match.group(1) else None
        prefix2 = range_match.group(3) if range_match.group(3) else None
        
        # Use the prefix from the first number, but require both to match (or both be None)
        if (prefix1 is None and prefix2 is None) or (prefix1 and prefix2 and prefix1 == prefix2):
            prefix = prefix1
            start_num = int(range_match.group(2))
            end_num = int(range_match.group(4))
            
            if start_num <= end_num:
                return (prefix, start_num, end_num)
    
    # Try pattern with no prefix: "3317-3351" or with prefix only on first: "C3317-3351"
    # This regex allows digits after the dash, and will capture prefix from first number only
    range_match = re.match(r'^([A-Za-z]*?)(\d+)-(\d+)$', pattern_upper)
    if range_match:
        prefix = range_match.group(1) if range_match.group(1) else None
        start_num = int(range_match.group(2))
        end_num = int(range_match.group(3))
        
        if start_num <= end_num:
            return (prefix, start_num, end_num)
    
    return (None, None, None)  # Not a range

def _matches_pattern(pattern: str, filename: str) -> bool:
    """
    Check if a filename matches a pattern, handling both regular patterns and ranges.
    Uses numeric comparison to handle zero-padding.
    """
    filename_lower = filename.lower()
    pattern_lower = pattern.lower()
    
    # First, check if pattern is a range
    prefix, start_num, end_num = _parse_range_pattern(pattern)
    if start_num is not None and end_num is not None:
        # It's a range - extract number from filename and check if in range
        file_num = _extract_number_from_filename(filename)
        if file_num is None:
            return False
        
        # If prefix specified, check that filename contains the prefix
        if prefix:
            if prefix.lower() not in filename_lower:
                return False
        
        # Check if number is in range
        return start_num <= file_num <= end_num
    
    # Not a range - try numeric matching first (for better zero-padding handling)
    pattern_num = _extract_number_from_filename(pattern)
    file_num = _extract_number_from_filename(filename)
    
    if pattern_num is not None and file_num is not None:
        # Both have numbers - compare numerically and check prefix
        if pattern_num == file_num:
            # Numbers match - check if prefixes match (if pattern has a prefix)
            pattern_letters = re.sub(r'\d+', '', pattern_lower)
            if pattern_letters:
                # Pattern has letters - check if filename contains them
                return pattern_letters in filename_lower
            else:
                # Just a number pattern - match if filename contains this number
                return True
    
    # Fallback to substring matching for non-numeric patterns
    return pattern_lower in filename_lower

def ingest_shoot(source_dir: str, shoot_name: str, laptop_dest: Path, archive_dest: Path, auto: bool = False, force: bool = False):
    """
    The core logic for the ingest command with date-aware duplicate detection.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}", err=True)
        raise typer.Exit(code=1)

    # 1. Recursively find all video files
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'}
    files_to_ingest = []
    for file_path in source_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            files_to_ingest.append(file_path)

    if not files_to_ingest:
        typer.echo("No video files found in the source directory.", err=True)
        return

    typer.echo(f"\nFound {len(files_to_ingest)} video file(s) to ingest.")

    # 2. Extract dates from files
    file_dates = [_get_media_date(f) for f in files_to_ingest]
    min_date = min(file_dates)
    max_date = max(file_dates)
    
    typer.echo(f"Date range of files: {min_date} to {max_date}")

    # 3. Discover existing shoots and determine target shoot folder
    existing_shoots = _find_existing_shoots(laptop_dest, archive_dest)
    
    target_shoot_name = None
    
    if auto:
        # Auto mode: find matching shoot or create new one
        file_date_range = (min_date, max_date)
        matching_shoot = _find_matching_shoot(file_date_range, existing_shoots)
        
        if matching_shoot:
            target_shoot_name = matching_shoot
            typer.echo(f"\n✓ Using existing shoot: {target_shoot_name}")
        else:
            # Create new shoot name from date range
            target_shoot_name = utils_date.format_shoot_name(min_date, max_date, "Ingest")
            typer.echo(f"\n✓ Creating new shoot: {target_shoot_name}")
            if existing_shoots:
                typer.echo("\nOther shoots with similar dates:")
                for shoot, shoot_info in existing_shoots.items():
                    start, end = shoot_info['date_range']
                    if utils_date.date_in_range(min_date, start, end) or utils_date.date_in_range(max_date, start, end):
                        typer.echo(f"  - {shoot} ({start} to {end})")
    else:
        # Manual mode: use provided shoot name
        if not shoot_name:
            typer.echo("Shoot name is required when --auto is not used.", err=True)
            raise typer.Exit(code=1)
        
        target_shoot_name = shoot_name
        
        # Validate date range matches existing shoot if it exists
        if target_shoot_name in existing_shoots:
            shoot_info = existing_shoots[target_shoot_name]
            shoot_start, shoot_end = shoot_info['date_range']
            if not (shoot_start <= min_date and max_date <= shoot_end):
                typer.echo(f"\n⚠ WARNING: Shoot '{target_shoot_name}' exists with date range {shoot_start} to {shoot_end}", err=True)
                typer.echo(f"   But files have date range {min_date} to {max_date}", err=True)
                if not force:
                    typer.echo("   Use --force to proceed anyway.", err=True)
                    raise typer.Exit(code=1)
        else:
            # Check if shoot name date prefix matches file dates
            shoot_date_range = utils_date.parse_shoot_date_range(target_shoot_name)
            if shoot_date_range:
                shoot_start, shoot_end = shoot_date_range
                if not (shoot_start <= min_date and max_date <= shoot_end):
                    typer.echo(f"\n⚠ WARNING: Shoot name date prefix ({shoot_start} to {shoot_end}) doesn't match file dates ({min_date} to {max_date})", err=True)
                    if not force:
                        typer.echo("   Use --force to proceed anyway.", err=True)
                        raise typer.Exit(code=1)
            else:
                typer.echo(f"\n⚠ WARNING: Shoot name '{target_shoot_name}' doesn't follow date format.", err=True)
                if not force:
                    typer.echo("   Use --force to proceed anyway.", err=True)
                    raise typer.Exit(code=1)

    # Check where target shoot exists and determine copy strategy
    shoot_exists_info = existing_shoots.get(target_shoot_name, {
        'in_laptop': False,
        'in_archive': False
    })
    
    shoot_in_laptop = shoot_exists_info.get('in_laptop', False)
    shoot_in_archive = shoot_exists_info.get('in_archive', False)
    
    # Pre-check: Count how many files already exist in both locations
    laptop_shoot_dir = laptop_dest / target_shoot_name
    archive_shoot_dir = archive_dest / "Video" / "RAW" / target_shoot_name
    
    if shoot_in_laptop or shoot_in_archive:
        # Quick check: count files that already exist in the existing folders
        existing_in_laptop = 0
        existing_in_archive = 0
        
        if shoot_in_laptop and laptop_shoot_dir.exists():
            existing_in_laptop = sum(1 for f in files_to_ingest if _is_duplicate(f, laptop_shoot_dir))
        
        if shoot_in_archive and archive_shoot_dir.exists():
            existing_in_archive = sum(1 for f in files_to_ingest if _is_duplicate(f, archive_shoot_dir))
        
        total_files = len(files_to_ingest)
        
        # If all files already exist in both locations, skip entirely
        if shoot_in_laptop and shoot_in_archive and existing_in_laptop == total_files and existing_in_archive == total_files:
            typer.echo(f"\n⚠ WARNING: Shoot '{target_shoot_name}' already exists in both ingest and archive.", err=True)
            typer.echo(f"   All {total_files} files already exist in both locations. Skipping ingest.", err=True)
            typer.echo("\nIngest skipped.")
            return
        elif shoot_in_laptop and existing_in_laptop == total_files:
            typer.echo(f"\n⚠ WARNING: Shoot '{target_shoot_name}' already exists in ingest folder.", err=True)
            typer.echo(f"   All {total_files} files already exist in ingest. Skipping ingest.", err=True)
            typer.echo("\nIngest skipped.")
            return
        
        # Some files are missing, proceed but warn
        if shoot_in_laptop:
            typer.echo(f"\n⚠ WARNING: Shoot '{target_shoot_name}' already exists in ingest folder.", err=True)
            typer.echo(f"   {existing_in_laptop}/{total_files} files already exist. Will only copy missing files.")
        
        if shoot_in_archive:
            typer.echo(f"\n⚠ Shoot '{target_shoot_name}' exists in archive.", err=True)
            typer.echo(f"   {existing_in_archive}/{total_files} files already exist in archive. Will only copy missing files.")
    
    # Determine copy strategy based on where shoot exists
    copy_to_laptop = True
    copy_to_archive = True
    
    if shoot_in_archive and not shoot_in_laptop:
        typer.echo(f"\n✓ Shoot '{target_shoot_name}' exists in archive but not in ingest.", err=True)
        typer.echo("   Will ingest to laptop only (skipping archive copy since it's already archived).")
        copy_to_archive = False
    elif not shoot_in_laptop and not shoot_in_archive:
        typer.echo(f"\n✓ Shoot '{target_shoot_name}' is new. Will ingest to both laptop and archive.")

    # 4. Safety check: ensure destinations are correct (already defined above, just verify)
    # Verify paths are within expected locations
    try:
        laptop_shoot_dir.resolve().relative_to(laptop_dest.resolve())
        archive_shoot_dir.resolve().relative_to((archive_dest / "Video" / "RAW").resolve())
    except ValueError:
        typer.echo("ERROR: Invalid destination paths detected. This should not happen.", err=True)
        raise typer.Exit(code=1)

    # 5. Preflight summary
    typer.echo(f"\n{'='*70}")
    typer.echo(f"INGEST SUMMARY")
    typer.echo(f"{'='*70}")
    typer.echo(f"Source: {source_path}")
    typer.echo(f"Files: {len(files_to_ingest)}")
    typer.echo(f"Date range: {min_date} to {max_date}")
    typer.echo(f"Target shoot: {target_shoot_name}")
    typer.echo(f"Laptop destination: {laptop_shoot_dir} {'(existing)' if shoot_in_laptop else '(new)'}")
    typer.echo(f"Archive destination: {archive_shoot_dir} {'(existing)' if shoot_in_archive else '(new)'}")
    typer.echo(f"{'='*70}\n")

    # 6. Create destination directories (only if they don't exist)
    try:
        if not laptop_shoot_dir.exists():
            laptop_shoot_dir.mkdir(parents=True, exist_ok=True)
            typer.echo(f"Created laptop shoot directory: {laptop_shoot_dir}")
        else:
            typer.echo(f"Using existing laptop shoot directory: {laptop_shoot_dir}")
        
        if copy_to_archive and not archive_shoot_dir.exists():
            archive_shoot_dir.mkdir(parents=True, exist_ok=True)
            typer.echo(f"Created archive shoot directory: {archive_shoot_dir}")
        elif copy_to_archive:
            typer.echo(f"Using existing archive shoot directory: {archive_shoot_dir}")
    except Exception as e:
        typer.echo(f"Could not create destination directories: {e}", err=True)
        raise typer.Exit(code=1)

    # 7. Ingest files with duplicate detection
    copied_count = 0
    skipped_count = 0
    error_count = 0

    with typer.progressbar(files_to_ingest, label="Ingesting") as progress:
        for file_path in progress:
            # Check for duplicates (only check where we're actually copying)
            laptop_dup = _is_duplicate(file_path, laptop_shoot_dir) if copy_to_laptop else False
            archive_dup = _is_duplicate(file_path, archive_shoot_dir) if copy_to_archive else False
            
            # If both destinations would be skipped and both files exist, skip entirely
            if laptop_dup and archive_dup and not (copy_to_laptop and copy_to_archive):
                # This shouldn't happen often - both files exist but we're copying to one
                pass
            
            if laptop_dup and archive_dup:
                typer.echo(f"\n⚠ SKIPPING (duplicate): {file_path.name}")
                typer.echo(f"   Already exists in both laptop and archive for shoot '{target_shoot_name}'")
                skipped_count += 1
                continue
            elif laptop_dup or archive_dup:
                typer.echo(f"\n⚠ PARTIAL DUPLICATE: {file_path.name}")
                if laptop_dup and copy_to_laptop:
                    typer.echo(f"   File exists in laptop, {'copying to archive' if copy_to_archive and not archive_dup else 'skipped (already complete)'}")
                elif archive_dup and copy_to_archive:
                    typer.echo(f"   File exists in archive, {'copying to laptop' if copy_to_laptop and not laptop_dup else 'skipped (already complete)'}")
            
            typer.echo(f"\nProcessing {file_path.name}...")
            
            file_copied = False
            
            # Copy to laptop if enabled and not duplicate
            if copy_to_laptop and not laptop_dup:
                typer.echo(f"  -> Laptop: {laptop_shoot_dir}")
                if copy_and_verify(file_path, laptop_shoot_dir):
                    file_copied = True
                else:
                    error_count += 1
            elif not copy_to_laptop:
                typer.echo(f"  -> Laptop: SKIPPED (shoot already in ingest)")
            
            # Copy to archive if enabled and not duplicate
            if copy_to_archive and not archive_dup:
                typer.echo(f"  -> Archive: {archive_shoot_dir}")
                if copy_and_verify(file_path, archive_shoot_dir):
                    file_copied = True
                else:
                    error_count += 1
            elif not copy_to_archive:
                typer.echo(f"  -> Archive: SKIPPED (shoot already in archive)")
            
            # Count this file as copied if at least one copy succeeded
            if file_copied:
                copied_count += 1

    # 8. Final summary
    typer.echo(f"\n{'='*70}")
    typer.echo(f"INGEST COMPLETE")
    typer.echo(f"{'='*70}")
    typer.echo(f"Files copied: {copied_count}")
    typer.echo(f"Files skipped (duplicates): {skipped_count}")
    if error_count > 0:
        typer.echo(f"Errors: {error_count}", err=True)
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
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'}
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

    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'}
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
                video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'}
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
    
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'}
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

def consolidate_files(source_dir: str, output_folder_name: str, archive_path: Path):
    """
    Finds unique files from a source directory and copies them to a new folder in the archive.
    """
    source_path = Path(source_dir)
    output_path = archive_path / output_folder_name
    
    if not source_path.is_dir():
        typer.echo(f"Source is not a valid directory: {source_path}", err=True)
        raise typer.Exit(code=1)

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

    # --- 2. Scan source and copy unique files ---
    typer.echo(f"Scanning source directory and copying unique files to: {output_path}")
    source_files = list(source_path.rglob("*.*"))
    copied_log_path = output_path / "copied_files.txt"
    skipped_log_path = output_path / "skipped_duplicates.txt"

    copied_count = 0
    skipped_count = 0

    with copied_log_path.open("w") as copied_log, skipped_log_path.open("w") as skipped_log:
        with typer.progressbar(source_files, label="Consolidating") as progress:
            for file in progress:
                if file.is_file():
                    try:
                        file_id = (file.name, file.stat().st_size)
                        if file_id in archive_index:
                            skipped_log.write(f"{file}\n")
                            skipped_count += 1
                        else:
                            # Copy the file
                            copy_and_verify(file, output_path)
                            copied_log.write(f"{file}\n")
                            # Add to index to handle duplicates within the source itself
                            archive_index.add(file_id)
                            copied_count += 1
                    except FileNotFoundError:
                        continue # Ignore broken symlinks

    typer.echo("\nConsolidation complete.")
    typer.echo(f"{copied_count} unique files copied.")
    typer.echo(f"{skipped_count} duplicate files skipped.")
    typer.echo(f"See log files in {output_path} for details.")

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
    if archive_dest_file.exists():
        # Check if it's a duplicate by size
        try:
            if tagged_file_path.stat().st_size == archive_dest_file.stat().st_size:
                typer.echo(f"⚠ File already exists in archive (same size). Skipping archive copy.")
            else:
                typer.echo(f"⚠ File exists in archive but with different size. Copying anyway.")
                if not copy_and_verify(tagged_file_path, archive_selects_dir):
                    typer.echo("Aborting due to archive copy failure.", err=True)
                    tagged_file_path.unlink() # Clean up temp file
                    raise typer.Exit(code=1)
        except Exception:
            # If we can't check size, copy anyway
            if not copy_and_verify(tagged_file_path, archive_selects_dir):
                typer.echo("Aborting due to archive copy failure.", err=True)
                tagged_file_path.unlink() # Clean up temp file
                raise typer.Exit(code=1)
    elif not copy_and_verify(tagged_file_path, archive_selects_dir):
        typer.echo("Aborting due to archive copy failure.", err=True)
        tagged_file_path.unlink() # Clean up temp file
        raise typer.Exit(code=1)
    else:
        typer.echo("✓ File copied to archive.")
        
    # 6. Copy to SSD Selects folder (with duplicate check)
    typer.echo(f"Copying tagged select to SSD: {ssd_selects_dir}")
    ssd_dest_file = ssd_selects_dir / tagged_file_path.name
    if ssd_dest_file.exists():
        # Check if it's a duplicate by size
        try:
            if tagged_file_path.stat().st_size == ssd_dest_file.stat().st_size:
                typer.echo(f"⚠ File already exists in SSD selects folder (same size). Skipping SSD copy.")
            else:
                typer.echo(f"⚠ File exists in SSD selects but with different size. Copying anyway.")
                if not copy_and_verify(tagged_file_path, ssd_selects_dir):
                    typer.echo("Warning: Could not copy select to SSD. It is safely in the archive.", err=True)
        except Exception:
            # If we can't check size, copy anyway if not exists
            if not copy_and_verify(tagged_file_path, ssd_selects_dir):
                typer.echo("Warning: Could not copy select to SSD. It is safely in the archive.", err=True)
    elif not copy_and_verify(tagged_file_path, ssd_selects_dir):
        # This is not a critical failure, the file is archived. Warn the user.
        typer.echo("Warning: Could not copy select to SSD. It is safely in the archive.", err=True)
    else:
        typer.echo("✓ File copied to SSD selects folder.")
    
    # 7. Cleanup
    tagged_file_path.unlink()
    
    typer.echo("\n✓ Create select complete.")
