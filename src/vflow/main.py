import typer
import yaml
from pathlib import Path
from . import config

app = typer.Typer()

from . import actions

@app.command()
def ingest(
    source: str = typer.Option(..., "--source", "-s", help="Exact folder path where videos are located (e.g., '/Volumes/Kaung 128GB/private/M4ROOT/CLIP')"),
    shoot: str = typer.Option(None, "--shoot", "-n", help="Name of the shoot (e.g., '2025-09-15_Stockholm_Broll'). Optional if --auto is used."),
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically infer shoot folder name from file dates. Creates date range if spanning multiple days."),
    force: bool = typer.Option(False, "--force", "-f", help="Force ingest even if shoot name conflicts with existing date ranges."),
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
    
    actions.ingest_shoot(source, shoot, laptop_dest, archive_dest, auto=auto, force=force)

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
    output_folder: str = typer.Option(..., "--output-folder", "-o", help="Name of the folder to create in the archive for unique media"),
):
    """
    Finds and copies unique media from a source drive into the archive.
    """
    typer.echo(f"Consolidating unique files from '{source}'...")
    
    app_config = config.load_config()
    archive_hdd_dest = config.get_location(app_config, "archive_hdd")
    
    actions.consolidate_files(source, output_folder, archive_hdd_dest)

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
