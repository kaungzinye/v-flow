import typer
import yaml
from pathlib import Path
from typing import Optional
from . import config
from .checkout_service import checkout_shoot, report_checkout
from .export_archive import archive_export, report_archive
from .finish_service import finish_project, report_finish
from .resolve_adapter import ResolveUnavailableError, get_resolve_adapter

app = typer.Typer()

from . import actions

@app.command()
def ingest(
    source: str = typer.Option(..., "--source", "-s", help="Camera card or source folder to preserve as received."),
    shoot: str = typer.Option(None, "--shoot", "-n", help="Name of the shoot (e.g., '2025-09-15_Stockholm_Broll'). Optional if --auto is used."),
    import_batch: str = typer.Option(None, "--import-batch", help="Stable Import Batch identity. By default, v-flow derives one from the source hierarchy and content."),
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically infer shoot folder name from file dates. Creates date range if spanning multiple days."),
    force: bool = typer.Option(False, "--force", "-f", help="Accepted for legacy scripts; immutable batches never overwrite conflicts."),
    skip_laptop: bool = typer.Option(False, "--skip-laptop", help="Accepted for legacy scripts; ingest never creates a Working Copy."),
    workspace: bool = typer.Option(False, "--workspace", "-w", help="Unsupported for ingest; create a Working Copy with Checkout."),
    split_by_gap: int = typer.Option(0, "--split-by-gap", help="Unsupported for immutable Import Batches, which preserve one received source hierarchy."),
    files: list[str] = typer.Option(None, "--files", help="Optional: Specific filenames, patterns, or ranges to ingest (e.g., 'C3317' or 'C3317-C3351'). Can specify multiple times. If omitted, ingests all files."),
):
    """
    Archives a camera card or source folder as an immutable Import Batch.

    The received hierarchy and companion files remain intact. A SHA-256 manifest
    proves every archived file. Ingest leaves the source untouched and does not
    create a Working Copy.
    """
    if not auto and not shoot:
        typer.echo("Either --shoot or --auto must be provided.", err=True)
        raise typer.Exit(code=1)
    
    # Load configuration
    app_config = config.load_config()
    
    # Ingest depends only on protected Archive storage.
    archive_dest = config.get_location(app_config, "archive")
        
    actions.ingest_shoot(
        source,
        shoot,
        archive_dest,
        auto=auto,
        force=force,
        skip_laptop=skip_laptop,
        workspace=workspace,
        split_threshold=split_by_gap,
        files_filter=files,
        import_batch_id=import_batch,
    )


@app.command()
def checkout(
    shoot: str = typer.Option(..., "--shoot", "-n", help="Shoot identity to make available for editing."),
    working_location: Optional[str] = typer.Option(
        None,
        "--working-location",
        "-l",
        help="Explicit named Working Location for the Working Copy.",
    ),
    direct_archive_access: bool = typer.Option(
        False,
        "--direct-archive-access",
        help="Use the archived Camera Originals in place and create no Working Copy.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Verify and preview the Checkout without copying files.",
    ),
):
    """Create a Working Copy, or report paths for Direct Archive Access."""
    app_config = config.load_config()
    archive_path = config.get_location(app_config, "archive")
    try:
        result = checkout_shoot(
            app_config,
            archive_path,
            shoot,
            working_location,
            direct_archive_access,
            dry_run,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)
    report_checkout(result)

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
    archive_dest = config.get_location(app_config, "archive")
    laptop_dest = config.get_location(app_config, "laptop")
    actions.ingest_report(source, archive_dest, laptop_path=laptop_dest, priority_day=priority_day, priority_month=priority_month)

@app.command("photo-ingest")
def photo_ingest_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Folder containing RAW photo files (e.g., '/Volumes/Untitled/DCIM/100MSDCF')."),
    shoot: str = typer.Option(..., "--shoot", "-n", help="Name of the shoot folder to create/add to in Photo/RAW (e.g., 'Iceland Trip')."),
):
    """
    Copies new RAW photos from a card or folder into the photo archive.

    Files are compared against the specific shoot folder only (not archive-wide) to
    avoid Sony filename-recycling false positives. Timestamps are preserved.
    Supported formats: ARW, CR2, CR3, NEF, DNG, ORF, RW2.
    """
    app_config = config.load_config()
    archive_dest = config.get_location(app_config, "archive")
    actions.photo_ingest(source, shoot, archive_dest)


@app.command("card-report")
def card_report_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Card root directory (e.g., '/Volumes/Untitled')."),
):
    """
    Shows what's on a card, grouped by date.

    Auto-detects the video folder (private/M4ROOT/CLIP) and photo folder (DCIM/100MSDCF).
    For each section, shows date, first/last filename, count, and whether video files
    are already in the archive.
    """
    app_config = config.load_config()
    archive_dest = config.get_location(app_config, "archive")
    actions.card_report(source, archive_dest)


@app.command("card-verify")
def card_verify_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Card root directory (e.g., '/Volumes/Untitled')."),
    photo_shoot: Optional[str] = typer.Option(None, "--photo-shoot", help="Name of the photo shoot in Photo/RAW to verify photos against (required if card has photos)."),
):
    """
    Verifies card contents are safely in the archive before formatting.

    Videos are checked archive-wide (Video/RAW) by name+size.
    Photos are checked against a specific shoot folder only (Photo/RAW/<photo-shoot>),
    avoiding Sony filename-recycling false positives across shoots.
    Reports PASS or FAIL separately for videos and photos.
    """
    app_config = config.load_config()
    archive_dest = config.get_location(app_config, "archive")
    actions.card_verify(source, archive_dest, photo_shoot=photo_shoot)


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
    archive_dest = config.get_location(app_config, "archive")
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
    archive_dest = config.get_location(app_config, "archive")
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
    archive_dest = config.get_location(app_config, "archive")
    
    actions.pull_shoot(shoot, work_ssd_dest, archive_dest, source_type=source, files_filter=files)

@app.command()
def archive(
    export_type: str = typer.Option(
        ...,
        "--type",
        help="Export type: 'final-video' or 'graded-select'.",
    ),
    file: str = typer.Option(
        ...,
        "--file",
        "-f",
        help="Filename beneath the selected local Exports category.",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project identity for a Final Video.",
    ),
    shoot: Optional[str] = typer.Option(
        None,
        "--shoot",
        "-n",
        help="Shoot identity for a Graded Select.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Verify and preview the archive operation without copying.",
    ),
):
    """Copy and verify a retained export without deleting any local files."""
    app_config = config.load_config()
    exports = config.get_location(app_config, "exports")
    archive_path = config.get_location(app_config, "archive")
    try:
        result = archive_export(
            exports,
            archive_path,
            export_type,
            file,
            project=project,
            shoot=shoot,
            dry_run=dry_run,
        )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)
    report_archive(result)


@app.command()
def finish(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project identity whose retained outputs and Project Backup must verify.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Verify retained outputs and preview the Project Backup export.",
    ),
):
    """Finish a Project through Resolve without removing local files."""
    app_config = config.load_config()
    exports = config.get_location(app_config, "exports")
    archive_path = config.get_location(app_config, "archive")
    try:
        adapter = None if dry_run else get_resolve_adapter()
        result = finish_project(
            exports,
            archive_path,
            project,
            adapter,
            dry_run=dry_run,
        )
    except (OSError, ResolveUnavailableError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)
    report_finish(result)

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
    archive_hdd_dest = config.get_location(app_config, "archive")
    
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
    archive_hdd_dest = config.get_location(app_config, "archive")
    
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
    archive_hdd_dest = config.get_location(app_config, "archive")

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
    archive_hdd_dest = config.get_location(app_config, "archive")
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
def locations():
    """Show storage roles and whether each configured location is available."""
    app_config = config.load_config()
    locs = app_config.get("locations", {})
    settings = app_config.get("settings", {})

    archive_path = config.resolve_location(app_config, "archive")
    typer.echo("Storage roles:")
    if archive_path:
        typer.echo(f"  Archive: {archive_path} [{config.location_status(archive_path)}]")
    else:
        typer.echo("  Archive: not configured")

    exports_path = config.resolve_location(app_config, "exports")
    if exports_path:
        typer.echo(f"  Exports: {exports_path} [{config.location_status(exports_path)}]")
    else:
        typer.echo("  Exports: not configured")

    typer.echo("Working locations:")
    working = locs.get("working", {})
    if isinstance(working, dict) and working:
        for name, path in working.items():
            typer.echo(f"  {name}: {path} [{config.location_status(path)}]")
    else:
        for name in ("laptop", "work_ssd"):
            path = config.resolve_location(app_config, name)
            if path:
                typer.echo(f"  {name}: {path} [{config.location_status(path)}]")

    if settings:
        typer.echo("Settings:")
        for key, val in settings.items():
            typer.echo(f"  {key}: {val}")


@app.command("set")
def set_config(
    key: str = typer.Argument(help="Config key: archive, exports, working.<name>, or settings.<name>."),
    value: str = typer.Argument(help="New value for the key."),
):
    """Update a single config value without re-running setup.

    Examples:
      v-flow set archive "/Volumes/Archive/Media"
      v-flow set exports "/Volumes/Work/Exports"
      v-flow set working.travel_ssd "/Volumes/Travel/Working Copies"
    """
    app_config = config.load_config()

    if key in {"archive", "exports"}:
        app_config.setdefault("locations", {})[key] = value
        typer.echo(f"Set locations.{key} = {value}")
    elif key.startswith("working.") and key[len("working."):]:
        working_name = key[len("working."):]
        app_config.setdefault("locations", {}).setdefault("working", {})[working_name] = value
        typer.echo(f"Set locations.working.{working_name} = {value}")
    elif key.startswith("settings."):
        setting_key = key[len("settings."):]
        app_config.setdefault("settings", {})[setting_key] = value
        typer.echo(f"Set settings.{setting_key} = {value}")
    else:
        typer.echo(
            f"Unknown key '{key}'. Use archive, exports, working.<name>, or settings.<name>.",
            err=True,
        )
        raise typer.Exit(code=1)

    config.save_config(app_config)
    typer.echo(f"Config saved to {config.CONFIG_PATH}")


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
        "version": config.CONFIG_VERSION,
        "locations": {
            "archive": "/path/to/your/archive",
            "exports": "/path/to/your/exports",
            "working": {
                "laptop": "/path/to/your/laptop/working/copies",
                "work_ssd": "/path/to/your/fast/working/drive",
            },
        },
        "settings": {
            "laptop_free_space_reserve_gb": config.DEFAULT_LAPTOP_FREE_SPACE_RESERVE_GB,
        },
    }
    
    with open(config.CONFIG_PATH, "w") as f:
        yaml.dump(sample_config, f, default_flow_style=False, sort_keys=False)
        
    typer.echo(f"Sample configuration file created at: {config.CONFIG_PATH}")
    typer.echo("Please edit this file with your actual folder paths.")


if __name__ == "__main__":
    app()
