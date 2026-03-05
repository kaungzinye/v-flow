import typer
import yaml
from pathlib import Path
from typing import Optional
from . import config

app = typer.Typer()

from . import actions

@app.command()
def ingest(
    source: str = typer.Option(..., "--source", "-s", help="Exact folder path where videos are located (e.g., '/Volumes/Kaung 128GB/private/M4ROOT/CLIP')"),
    shoot: str = typer.Option(None, "--shoot", "-n", help="Name of the shoot (e.g., '2025-09-15_Stockholm_Broll'). Optional if --auto is used."),
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically infer shoot folder name from file dates. Creates date range if spanning multiple days."),
    force: bool = typer.Option(False, "--force", "-f", help="Force ingest even if shoot name conflicts with existing date ranges."),
    skip_laptop: bool = typer.Option(False, "--skip-laptop", help="Skip copying files to the laptop ingest folder (saves space)."),
    workspace: bool = typer.Option(False, "--workspace", "-w", help="Also ingest directly to the Workspace SSD."),
    split_by_gap: int = typer.Option(0, "--split-by-gap", help="Automatically split footage into multiple shoots if a time gap of X hours is detected."),
    files: list[str] = typer.Option(None, "--files", help="Optional: Specific filenames, patterns, or ranges to ingest (e.g., 'C3317' or 'C3317-C3351'). Can specify multiple times. If omitted, ingests all files."),
):
    """
    Ingests footage from a source to the laptop and archive.
    
    The source should be the exact folder path where your video files are located
    (e.g., '/Volumes/Kaung 128GB/private/M4ROOT/CLIP' for Sony cameras).
    Videos will be searched recursively from this folder.
    """
    if not auto and not shoot:
        typer.echo("Either --shoot or --auto must be provided.", err=True)
        raise typer.Exit(code=1)
    
    # Load configuration
    app_config = config.load_config()
    
    # Get locations
    laptop_dest = config.get_location(app_config, "laptop")
    archive_dest = config.get_location(app_config, "archive_hdd")
    
    workspace_dest = None
    if workspace:
        workspace_dest = config.get_location(app_config, "work_ssd")
        
    # Check for default split gap if not provided via flag
    if split_by_gap == 0:
        split_by_gap = config.get_setting(app_config, "default_split_gap", 0)
    
    actions.ingest_shoot(source, shoot, laptop_dest, archive_dest, auto=auto, force=force, skip_laptop=skip_laptop, workspace_dest=workspace_dest, split_threshold=split_by_gap, files_filter=files)

@app.command("ingest-report")
def ingest_report_cmd(
    source: str = typer.Option(..., "--source", "-s", help="SD card CLIP folder (e.g., '/Volumes/Untitled/private/M4ROOT/CLIP')"),
    priority_day: int = typer.Option(28, "--priority-day", help="Day of month to highlight as priority (e.g. 28 for the 28th)"),
    priority_month: Optional[int] = typer.Option(None, "--priority-month", help="Month for priority day (optional; if omitted, any 28th on card is highlighted)"),
):
    """
    Report what on the SD card has not been ingested yet.
    Compares source to BOTH laptop ingest and archive (duplicate = same name+size in either).
    Highlights a priority day (default 28th) for editing.
    """
    app_config = config.load_config()
    archive_dest = config.get_location(app_config, "archive_hdd")
    laptop_dest = config.get_location(app_config, "laptop")
    actions.ingest_report(source, archive_dest, laptop_path=laptop_dest, priority_day=priority_day, priority_month=priority_month)

@app.command("list-duplicates")
def list_duplicates_cmd(
    location: str = typer.Option("archive", "--location", "-l", help="Where to scan: 'archive', 'laptop', or 'both'"),
    past_hours: Optional[int] = typer.Option(None, "--past-hours", "-H", help="Only consider files modified in the last N hours (e.g. 24 for newly ingested)"),
):
    """
    List duplicate files (same name + size in multiple places) in archive and/or laptop.
    Use --past-hours 24 to only check files ingested in the last 24 hours.
    """
    app_config = config.load_config()
    archive_dest = config.get_location(app_config, "archive_hdd")
    laptop_dest = config.get_location(app_config, "laptop")

    def report_duplicates(label: str, root: Path) -> None:
        if not root.exists():
            typer.echo(f"{label}: path not found ({root})")
            return
        dupes = actions.list_duplicates(root, max_age_hours=past_hours)
        typer.echo(f"\n{'='*70}")
        typer.echo(f"{label}")
        typer.echo(f"{'='*70}")
        typer.echo(f"Scanned: {root}" + (f" (only files modified in last {past_hours}h)" if past_hours else ""))
        typer.echo(f"Duplicate groups: {len(dupes)}")
        total_extra = sum(len(paths) - 1 for _, paths in dupes)
        typer.echo(f"Extra copies (could be removed): {total_extra}")
        typer.echo("")
        for (name, size), paths in sorted(dupes, key=lambda x: (x[0][0], x[0][1])):
            paths_sorted = sorted(paths, key=lambda p: str(p))
            typer.echo(f"  {name}  ({size} bytes)  appears {len(paths_sorted)} times:")
            for p in paths_sorted:
                try:
                    rel = p.relative_to(root)
                except ValueError:
                    rel = p
                typer.echo(f"    - {rel}")
            typer.echo("")

    if location in ("archive", "both"):
        archive_raw = archive_dest / "Video" / "RAW"
        report_duplicates("ARCHIVE (Video/RAW)", archive_raw)
    if location in ("laptop", "both"):
        report_duplicates("LAPTOP (Ingest)", laptop_dest)
    if location not in ("archive", "laptop", "both"):
        typer.echo("Invalid --location. Use 'archive', 'laptop', or 'both'.", err=True)
        raise typer.Exit(code=1)

@app.command("remove-duplicates")
def remove_duplicates_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Only report what would be removed"),
    past_hours: Optional[int] = typer.Option(None, "--past-hours", "-H", help="Only consider files modified in the last N hours (e.g. 24 for newly ingested)"),
):
    """
    Remove duplicate files (same name + size in multiple shoot folders) from
    archive Video/RAW and laptop ingest. Keeps one copy per file, deletes the rest.
    Use --past-hours 24 to only remove duplicates among recently ingested files.
    """
    app_config = config.load_config()
    archive_dest = config.get_location(app_config, "archive_hdd")
    laptop_dest = config.get_location(app_config, "laptop")
    archive_raw = archive_dest / "Video" / "RAW"
    suffix = f" (only files modified in last {past_hours}h)" if past_hours else ""
    typer.echo("Scanning archive for duplicates...")
    if archive_raw.exists():
        n_archive = actions.remove_duplicates(archive_raw, dry_run=dry_run, max_age_hours=past_hours)
        typer.echo(f"Archive: {n_archive} duplicate(s) {'would be ' if dry_run else ''}removed.{suffix}")
    else:
        typer.echo("Archive Video/RAW not found.")
    typer.echo("Scanning laptop ingest for duplicates...")
    if laptop_dest.exists():
        n_laptop = actions.remove_duplicates(laptop_dest, dry_run=dry_run, max_age_hours=past_hours)
        typer.echo(f"Laptop: {n_laptop} duplicate(s) {'would be ' if dry_run else ''}removed.{suffix}")
    else:
        typer.echo("Laptop ingest folder not found.")
    typer.echo("Done.")

@app.command()
def prep(
    shoot: str = typer.Option(..., "--shoot", "-n", help="Name of the shoot to prepare for editing"),
):
    """
    Prepares a shoot for editing by moving it to the work SSD.
    """
    typer.echo(f"Preparing '{shoot}' for editing...")
    
    # Load configuration
    app_config = config.load_config()
    
    # Get locations
    laptop_dest = config.get_location(app_config, "laptop")
    work_ssd_dest = config.get_location(app_config, "work_ssd")
    
    actions.prep_shoot(shoot, laptop_dest, work_ssd_dest)

@app.command()
def pull(
    shoot: str = typer.Option(..., "--shoot", "-n", help="Name of the shoot to pull from archive"),
    source: str = typer.Option("raw", "--source", "-s", help="What to pull: 'raw' (default), 'selects', or 'both'. Raw files go to 01_Source, graded selects go to 05_Graded_Selects."),
    files: list[str] = typer.Option(None, "--files", "-f", help="Optional: Specific filenames, patterns, or ranges to pull (e.g., 'C3317' or 'C3317-C3351'). Can specify multiple times. If omitted, pulls all files."),
):
    """
    Pulls files from archive to the work SSD for editing.
    
    Useful when you want to work with archived footage. Creates the standard
    project structure and copies (doesn't move) files from archive to your work SSD.
    
    Source options:
    - 'raw': Pull raw files from Video/RAW/ to 01_Source/ (default)
    - 'selects': Pull graded selects from Video/Graded_Selects/ to 05_Graded_Selects/
    - 'both': Pull both raw files and graded selects to their respective folders
    
    You can optionally specify specific files or partial filenames to pull only
    selected clips.
    """
    if source not in ("raw", "selects", "both"):
        typer.echo(f"Invalid source type: {source}. Must be 'raw', 'selects', or 'both'.", err=True)
        raise typer.Exit(code=1)
    
    typer.echo(f"Pulling '{shoot}' from archive to work SSD (source: {source})...")
    
    # Load configuration
    app_config = config.load_config()
    
    # Get locations
    work_ssd_dest = config.get_location(app_config, "work_ssd")
    archive_dest = config.get_location(app_config, "archive_hdd")
    
    actions.pull_shoot(shoot, work_ssd_dest, archive_dest, source_type=source, files_filter=files)

@app.command()
def archive(
    shoot: str = typer.Option(..., "--shoot", "-n", help="Name of the shoot"),
    file: str = typer.Option(..., "--file", "-f", help="Filename of the exported video to archive"),
    tags: str = typer.Option(..., "--tags", "-t", help="Comma-separated metadata tags"),
    keep_log: bool = typer.Option(False, "--keep-log", help="Do not delete the original S-LOG file from the source folder"),
):
    """
    Archives a final render, tags it, and cleans up the source file.
    """
    typer.echo(f"Archiving '{file}' from shoot '{shoot}'...")
    
    app_config = config.load_config()
    work_ssd_dest = config.get_location(app_config, "work_ssd")
    archive_hdd_dest = config.get_location(app_config, "archive_hdd")
    
    
    actions.archive_file(shoot, file, tags, keep_log, work_ssd_dest, archive_hdd_dest)

@app.command()
def create_select(
    shoot: str = typer.Option(..., "--shoot", "-n", help="Name of the shoot"),
    file: str = typer.Option(..., "--file", "-f", help="Filename of the exported video to create a select from"),
    tags: str = typer.Option(..., "--tags", "-t", help="Comma-separated metadata tags"),
):
    """
    Creates a graded select, archiving it and copying it to the local SSD for reuse.
    """
    typer.echo(f"Creating select for '{file}' from shoot '{shoot}'...")
    
    app_config = config.load_config()
    work_ssd_dest = config.get_location(app_config, "work_ssd")
    archive_hdd_dest = config.get_location(app_config, "archive_hdd")
    
    actions.create_select_file(shoot, file, tags, work_ssd_dest, archive_hdd_dest)

@app.command()
def consolidate(
    source: str = typer.Option(..., "--source", "-s", help="Source directory to scan for unique files"),
    output_folder: str = typer.Option(None, "--output-folder", "-o", help="Name of the folder to create in the archive for unique media (required if --destination not provided)"),
    destination: str = typer.Option(None, "--destination", "-d", help="Path relative to archive root (e.g., 'Video/Graded'). If provided, uses this instead of --output-folder."),
    files: list[str] = typer.Option(None, "--files", "-f", help="Optional: Specific filenames, patterns, or ranges to process (e.g., 'C3317' or 'project1'). Can specify multiple times. If omitted, processes all files."),
    tags: str = typer.Option(None, "--tags", "-t", help="Optional: Comma-separated metadata tags to add to copied files"),
):
    """
    Finds and copies unique media from a source drive into the archive.
    
    Can be used for general consolidation (with --output-folder) or for backing up exports
    to a specific location (with --destination, e.g., "Video/Graded").
    
    Examples:
    - Consolidate all files: consolidate --source "/path/to/source" --output-folder "NewFolder"
    - Backup specific projects: consolidate --source "/path/to/exports" --destination "Video/Graded" --files "project1" --files "project2"
    """
    if not output_folder and not destination:
        typer.echo("Either --output-folder or --destination must be provided.", err=True)
        raise typer.Exit(code=1)
    
    typer.echo(f"Consolidating unique files from '{source}'...")
    
    app_config = config.load_config()
    archive_hdd_dest = config.get_location(app_config, "archive_hdd")
    
    actions.consolidate_files(
        source,
        output_folder,
        archive_hdd_dest,
        destination_path=destination,
        file_filter=files,
        tags=tags,
        preserve_structure=True,
    )


@app.command()
def backup(
    source: str = typer.Option(..., "--source", "-s", help="Source directory to back up (e.g., '~/Desktop/Ingest')."),
    destination: str = typer.Option(..., "--destination", "-d", help="Path relative to archive root (e.g., 'Video/RAW/2025-10-12_Shoot')."),
    files: list[str] = typer.Option(None, "--files", "-f", help="Optional: Specific filenames, patterns, or ranges to back up (e.g., 'C3317' or 'C3317-C3351'). Can specify multiple times. If omitted, processes all files."),
    tags: str = typer.Option(None, "--tags", "-t", help="Optional: Comma-separated metadata tags to add to copied files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Analyze what would be backed up without copying any files."),
    delete_source: bool = typer.Option(
        False,
        "--delete-source",
        help="After copying, prompt to optionally delete source files that were successfully backed up.",
    ),
):
    """
    Backs up media from an arbitrary source folder into the archive with duplicate checks.

    This is a friendly wrapper around the consolidate logic, intended for backing up
    ingest folders or project folders (e.g., Desktop/Ingest) into your archive drive.

    Use --dry-run first to see which files are not already in the archive.
    """
    typer.echo(f"{'Dry-running' if dry_run else 'Backing up'} from '{source}' to archive destination '{destination}'...")
    if delete_source and dry_run:
        typer.echo(
            "Note: --delete-source is set; this dry-run will only report which files would be eligible for deletion after a real backup."
        )

    app_config = config.load_config()
    archive_hdd_dest = config.get_location(app_config, "archive_hdd")

    actions.consolidate_files(
        source,
        output_folder_name=None,
        archive_path=archive_hdd_dest,
        destination_path=destination,
        file_filter=files,
        tags=tags,
        preserve_structure=True,
        dry_run=dry_run,
        delete_source=delete_source,
    )


@app.command("verify-backup")
def verify_backup_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Source directory that was backed up."),
    destination: str = typer.Option(
        ..., "--destination", "-d", help="Destination directory where backup was written."
    ),
    allow_delete: bool = typer.Option(
        False,
        "--allow-delete",
        help="After successful verification, prompt to delete all files under the source folder.",
    ),
    archive_wide: bool = typer.Option(
        False,
        "--archive-wide",
        help="Treat destination as an archive root and verify that each source file exists "
        "anywhere under it by name+size, instead of requiring a path-for-path mirror.",
    ),
):
    """
    Verify that all files in a source folder exist in a destination folder with matching sizes.

    This is a general-purpose checker for any two folders (e.g. Desktop/Ingest vs archive).
    Use together with 'backup' or any other copy method to confirm that your backup is complete
    before optionally deleting the source files.
    """
    typer.echo(f"Verifying backup between source '{source}' and destination '{destination}'...")
    actions.verify_backup(source, destination, allow_delete=allow_delete, archive_wide=archive_wide)


@app.command("list-backups")
def list_backups_cmd(
    subpath: str = typer.Option(
        "Video/RAW/Desktop_Ingest",
        "--subpath",
        "-p",
        help="Subpath under archive root to scan for backups (e.g., 'Video/RAW/Desktop_Ingest').",
    ),
):
    """
    List backup folders under a given archive subpath with file counts and total sizes.

    Useful for quickly seeing what has been consolidated, and how large each backup folder is.
    """
    app_config = config.load_config()
    archive_hdd_dest = config.get_location(app_config, "archive_hdd")
    actions.list_backups(archive_hdd_dest, subpath)


@app.command("restore-folder")
def restore_folder_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Source folder to restore from (e.g., an archive backup folder)."),
    destination: str = typer.Option(
        ..., "--destination", "-d", help="Destination folder to restore into (e.g., a workspace or temp folder)."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate the restore without copying any files. Shows what would be copied/overwritten.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Allow overwriting destination files that differ in size. If false, such conflicts are reported and skipped.",
    ),
):
    """
    Restore (copy) an arbitrary folder tree from one location to another.

    This is the inverse of 'backup' for general folders and can be used to pull a
    backup folder from archive back to a workspace path.
    """
    actions.restore_folder(source, destination, dry_run=dry_run, overwrite=overwrite)

@app.command()
def copy_meta(
    source_folder: Path = typer.Option(..., "--source-folder", "-s", help="Path to the folder with original files"),
    target_folder: Path = typer.Option(..., "--target-folder", "-t", help="Path to the folder with exported files"),
):
    """
    Copies metadata from files in a source folder to files in a target folder based on matching filenames.
    """
    typer.echo(f"Copying metadata from '{source_folder}' to '{target_folder}'...")
    actions.copy_metadata_folder(source_folder, target_folder)



@app.command()
def make_config():
    """
    Creates a sample configuration file in your home directory.
    """
    if config.CONFIG_PATH.exists():
        typer.echo(f"Configuration file already exists at: {config.CONFIG_PATH}")
        overwrite = typer.confirm("Overwrite?")
        if not overwrite:
            typer.echo("Aborting.")
            raise typer.Exit()

    sample_config = {
        "locations": {
            "laptop": "/path/to/your/laptop/ingest/folder",
            "work_ssd": "/path/to/your/fast/ssd/projects",
            "archive_hdd": "/path/to/your/archive/hdd",
        }
    }
    
    with open(config.CONFIG_PATH, "w") as f:
        yaml.dump(sample_config, f, default_flow_style=False, sort_keys=False)
        
    typer.echo(f"Sample configuration file created at: {config.CONFIG_PATH}")
    typer.echo("Please edit this file with your actual folder paths.")


if __name__ == "__main__":
    app()
