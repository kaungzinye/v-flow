import shutil
import typer
from pathlib import Path
import subprocess

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

def ingest_shoot(source_dir: str, shoot_name: str, laptop_dest: Path, archive_dest: Path):
    """
    The core logic for the ingest command.
    """
    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(f"Source directory not found: {source_path}")
        raise typer.Exit(code=1)

    # Create destination directories
    laptop_shoot_dir = laptop_dest / shoot_name
    archive_shoot_dir = archive_dest / "Video" / "RAW" / shoot_name
    
    try:
        laptop_shoot_dir.mkdir(parents=True, exist_ok=True)
        archive_shoot_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create destination directories: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Copying files to laptop: {laptop_shoot_dir}")
    typer.echo(f"Copying files to archive: {archive_shoot_dir}")

    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'} # Add more as needed
    files_to_copy = [p for p in source_path.iterdir() if p.is_file() and p.suffix.lower() in video_extensions]

    if not files_to_copy:
        typer.echo("No video files found in the source directory.")
        return

    with typer.progressbar(files_to_copy, label="Ingesting") as progress:
        for f in progress:
            typer.echo(f"\nProcessing {f.name}...")
            
            # Copy to laptop
            typer.echo(f"  -> Laptop")
            if not copy_and_verify(f, laptop_shoot_dir):
                # Decide on error handling: stop or continue? For now, we'll continue.
                pass

            # Copy to archive
            typer.echo(f"  -> Archive")
            if not copy_and_verify(f, archive_shoot_dir):
                pass
    
    typer.echo("\nIngest complete.")
    # TODO: Add a final verification step to count files.

def prep_shoot(shoot_name: str, laptop_ingest_path: Path, work_ssd_path: Path):
    """
    Moves a shoot from the ingest area to the working SSD and creates the project structure.
    """
    source_shoot_dir = laptop_ingest_path / shoot_name
    if not source_shoot_dir.exists() or not source_shoot_dir.is_dir():
        typer.echo(f"Shoot directory not found at ingest location: {source_shoot_dir}")
        raise typer.Exit(code=1)

    # Create project structure on the work SSD
    project_dir = work_ssd_path / shoot_name
    source_folder = project_dir / "01_Source"
    resolve_folder = project_dir / "02_Resolve"
    exports_folder = project_dir / "03_Exports"
    final_renders_folder = project_dir / "04_FinalRenders"

    try:
        typer.echo(f"Creating project structure at: {project_dir}")
        source_folder.mkdir(parents=True, exist_ok=True)
        resolve_folder.mkdir(exist_ok=True)
        exports_folder.mkdir(exist_ok=True)
        final_renders_folder.mkdir(exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create project directories on work SSD: {e}", err=True)
        raise typer.Exit(code=1)

    # Move files from ingest to work SSD
    video_extensions = {'.mp4', '.mov', '.mxf', '.mts', '.avi', '.m4v'}
    files_to_move = [p for p in source_shoot_dir.iterdir() if p.is_file() and p.suffix.lower() in video_extensions]

    if not files_to_move:
        typer.echo("No video files found in the source shoot directory to move.")
        return

    typer.echo(f"Moving {len(files_to_move)} video files to {source_folder}...")
    with typer.progressbar(files_to_move, label="Prepping") as progress:
        for f in progress:
            try:
                shutil.move(str(f), str(source_folder))
            except Exception as e:
                typer.echo(f"\n[ERROR] Could not move {f.name}: {e}", err=True)
                # Decide on error handling. For now, we continue.
    
    typer.echo("\nPrep complete. Project is ready for editing.")

def archive_file(shoot_name: str, file_name: str, tags_str: str, keep_log: bool, work_ssd_path: Path, archive_path: Path):
    """
    Tags, archives, and cleans up a final rendered file.
    """
    # Define paths
    export_file_path = work_ssd_path / shoot_name / "03_Exports" / file_name
    archive_graded_dir = archive_path / "Video" / "Graded" / shoot_name
    
    # 1. Verify the source file exists
    if not export_file_path.exists():
        typer.echo(f"Export file not found: {export_file_path}", err=True)
        raise typer.Exit(code=1)
        
    # 2. Create archive destination directory
    try:
        archive_graded_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(f"Could not create archive directory: {e}", err=True)
        raise typer.Exit(code=1)

    # 3. Metadata Tagging
    tags_list = [tag.strip() for tag in tags_str.split(',')]
    
    # Temporary file for ffmpeg processing
    tagged_file_path = export_file_path.with_name(f"{export_file_path.stem}_tagged{export_file_path.suffix}")

    # Universal metadata with ffmpeg
    typer.echo("Embedding universal metadata with ffmpeg...")
    try:
        ffmpeg_cmd = [
            'ffmpeg', '-i', str(export_file_path),
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
        # The xattr command requires the tags to be in a specific format.
        # This is a simplified approach. A more robust solution might be needed.
        for tag in tags_list:
            xattr_cmd = ['xattr', '-w', 'com.apple.metadata:_kMDItemUserTags', f'"{tag}"', str(tagged_file_path)]
            # This is a simplified example. Real implementation would need to handle list formatting for xattr.
            # For now, we'll just apply the whole string as one tag for demonstration.
        
        # A more correct, but complex way to set multiple tags:
        tag_plist = ''.join([f'<string>{tag}</string>' for tag in tags_list])
        bplist_cmd = f'xattr -w com.apple.metadata:_kMDItemUserTags \'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><array>{tag_plist}</array></plist>\' "{str(tagged_file_path)}"'
        subprocess.run(bplist_cmd, shell=True, check=True, capture_output=True)

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        typer.echo(f"Could not apply macOS tags: {e}", err=True)
        # This is a non-critical error, so we can continue.
        pass

    # 4. Archive Copy
    typer.echo(f"Copying tagged file to archive: {archive_graded_dir}")
    if not copy_and_verify(tagged_file_path, archive_graded_dir):
        typer.echo("Aborting cleanup due to copy failure.", err=True)
        raise typer.Exit(code=1)
    
    # 5. Cleanup
    # Delete the temporary tagged file
    tagged_file_path.unlink()

    if not keep_log:
        original_source_file = work_ssd_path / shoot_name / "01_Source" / export_file_path.name
        # This assumes the source file has the same name as the export, which might not be true.
        # A more robust solution would be to match by stem (filename without extension).
        
        source_files = list((work_ssd_path / shoot_name / "01_Source").glob(f"{export_file_path.stem}.*"))
        if source_files:
            original_source_file = source_files[0]
            typer.echo(f"Cleaning up original source file: {original_source_file}")
            try:
                original_source_file.unlink()
            except Exception as e:
                typer.echo(f"Could not delete source file: {e}", err=True)
        else:
            typer.echo(f"Warning: Could not find a matching source file for '{export_file_path.name}' to clean up.")

    typer.echo("\nArchive complete.")

def copy_metadata_folder(source_folder: Path, target_folder: Path):
    """
    Copies metadata from files in a source folder to files with matching names in a target folder.
    """
    if not source_folder.is_dir() or not target_folder.is_dir():
        typer.echo("Source and target must be directories.", err=True)
        raise typer.Exit(code=1)

    target_files = [p for p in target_folder.iterdir() if p.is_file()]
    
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
