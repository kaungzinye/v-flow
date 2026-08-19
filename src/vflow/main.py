import typer
import yaml
from pathlib import Path
from typing import Optional
from . import config
from .checkout_service import checkout_shoot, report_checkout
from .cleanup_service import delete_working_copy, prepare_cleanup, report_cleanup
from .export_archive import archive_export, report_archive
from .finish_service import finish_project, report_finish
from .index_service import index_archive, report_index
from .resolve_adapter import ResolveUnavailableError, get_resolve_adapter
from .restore_service import report_restore, restore_archive_asset

app = typer.Typer()

from . import actions

@app.command()
def ingest(
    source: str = typer.Option(..., "--source", "-s", help="Camera card or source folder to copy footage and photos from."),
    shoot: str = typer.Option(None, "--shoot", "-n", help="Name of the shoot (e.g., '2025-09-15_Stockholm_Broll'). Optional if --auto is used."),
    collection: str = typer.Option(None, "--collection", "-c", help="Name of the photo Collection in Photo/RAW. Defaults to the Shoot name."),
    import_batch: str = typer.Option(None, "--import-batch", help="Stable Import Batch identity. By default, v-flow derives one from the source name, card paths, and file sizes."),
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically infer the Shoot and Collection name from file dates. Creates date range if spanning multiple days."),
    files: list[str] = typer.Option(None, "--files", help="Optional: Specific filenames, patterns, or ranges to ingest (e.g., 'C3317' or 'DSC00811-DSC00842'). Can specify multiple times. If omitted, ingests all files."),
    include_all: bool = typer.Option(False, "--include-all", help="Also preserve non-footage card files inside a hidden folder in the Shoot."),
):
    """
    Copies one card's footage into a flat Shoot and its photos into a flat Collection.

    Footage lands directly in Video/RAW/<shoot>, photos in Photo/RAW/<collection>, which
    carries the Shoot name unless --collection names it. A card without footage creates no
    Shoot, and a card without photos creates no Collection. Editing sidecars (.pp3, .xmp)
    ride into the Collection beside the photo they belong to, including when --files selects
    the photo. Each folder carries a hidden SHA-256 manifest recording every archived file,
    its card path, exclusions, and deduplicated originals. A skip needs checksum identity, so
    recycled camera filenames stay distinct. Ingest leaves the source untouched and creates
    no Working Copy.
    """
    if not auto and not shoot:
        typer.echo("Either --shoot or --auto must be provided.", err=True)
        raise typer.Exit(code=1)
    
    # Load configuration
    app_config = config.load_config()
    
    # Ingest depends only on protected Archive storage.
    archive_dest = config.get_location(app_config, "archive")
        
    actions.ingest_media(
        source,
        shoot,
        archive_dest,
        auto=auto,
        collection_name=collection,
        files_filter=files,
        import_batch_id=import_batch,
        include_all=include_all,
    )


@app.command()
def index(
    folder: list[str] = typer.Option(
        None,
        "--folder",
        "-f",
        help="Shoot or Collection to index, by folder name or Archive-relative path "
        "such as 'Photo/RAW/2019 Trip'. Repeatable.",
    ),
    all_folders: bool = typer.Option(
        False,
        "--all",
        help="Index every Shoot and Collection that lacks a complete Shoot Manifest.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report the folder count and total bytes to read without hashing anything.",
    ),
):
    """Give existing folders a complete Shoot Manifest by hashing them in place.

    Indexing walks flat folders under Video/RAW and Photo/RAW, hashes every file a
    manifest does not cover yet, and writes the checksums into the folder's hidden
    Shoot Manifest. It is purely additive: nothing moves, nothing is renamed, and the
    folder's visible contents stay byte-for-byte identical. A Partial Shoot Manifest
    left by ingest is completed rather than recomputed, and an interrupted run resumes
    where it stopped. Indexing runs only when you ask for it; v-flow never schedules it.
    """
    app_config = config.load_config()
    archive_path = config.get_location(app_config, "archive")
    try:
        result = index_archive(
            archive_path,
            names=folder or [],
            all_folders=all_folders,
            dry_run=dry_run,
        )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)
    report_index(result)


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
        help="Use the archived Shoot folder in place and create no Working Copy.",
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


@app.command()
def restore(
    source: str = typer.Option(
        ...,
        "--source",
        "-s",
        help="Explicit archived file or directory, as an Archive-relative or absolute path.",
    ),
    destination: str = typer.Option(
        ...,
        "--destination",
        "-d",
        help="Exact destination file for a file source, or destination root for a directory source.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Verify and preview paths, sizes, conflicts, and copies without changing files.",
    ),
):
    """Create a verified copy of an archived asset at a chosen destination."""
    app_config = config.load_config()
    archive_path = config.get_location(app_config, "archive")
    try:
        result = restore_archive_asset(
            archive_path,
            source,
            destination,
            dry_run=dry_run,
        )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)
    report_restore(result)
    if result["conflicts"]:
        raise typer.Exit(code=1)

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
def cleanup(
    shoot: str = typer.Option(
        ...,
        "--shoot",
        "-n",
        help="Shoot identity whose Working Copy is eligible for removal.",
    ),
    working_location: str = typer.Option(
        ...,
        "--working-location",
        "-l",
        help="Named Working Location containing the Working Copy.",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Resolve Project whose media links must remain valid.",
    ),
    skip_resolve_validation: bool = typer.Option(
        False,
        "--skip-resolve-validation",
        "--skip-resolve",
        help="Explicitly bypass only the Resolve validation gate.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run every non-mutating gate and preview deletion.",
    ),
):
    """Remove a Working Copy only after every Cleanup safety gate passes."""
    app_config = config.load_config()
    archive_path = config.get_location(app_config, "archive")
    try:
        if not skip_resolve_validation and not project:
            raise ValueError(
                "Resolve validation gate failed: --project is required unless --skip-resolve-validation is supplied"
            )
        adapter = None if skip_resolve_validation else get_resolve_adapter
        plan = prepare_cleanup(
            app_config,
            archive_path,
            shoot,
            working_location,
            project,
            adapter,
            skip_resolve_validation=skip_resolve_validation,
            dry_run=dry_run,
        )
        report_cleanup(plan)
        if dry_run:
            return
        if not typer.confirm(
            f"Delete {len(plan['files'])} verified files from this Working Copy?"
        ):
            typer.echo("Confirmation gate declined; no files were deleted.", err=True)
            raise typer.Exit(code=1)
        result = delete_working_copy(plan)
        report_cleanup(result)
        if result["failures"]:
            raise typer.Exit(code=1)
    except (OSError, ResolveUnavailableError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1)

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
):
    """
    Backs up media from an arbitrary source folder into the archive with duplicate checks.

    This is a friendly wrapper around the consolidate logic, intended for backing up
    ingest folders or project folders (e.g., Desktop/Ingest) into your archive drive.

    Use --dry-run first to see which files are not already in the archive.
    """
    typer.echo(f"{'Dry-running' if dry_run else 'Backing up'} from '{source}' to archive destination '{destination}'...")

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
    )


@app.command("verify-backup")
def verify_backup_cmd(
    source: str = typer.Option(..., "--source", "-s", help="Source directory that was backed up."),
    destination: str = typer.Option(
        ..., "--destination", "-d", help="Destination directory where backup was written."
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
    Use together with 'backup' or any other copy method to confirm that your backup is complete.
    """
    typer.echo(f"Verifying backup between source '{source}' and destination '{destination}'...")
    actions.verify_backup(source, destination, archive_wide=archive_wide)


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
