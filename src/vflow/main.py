import typer
import yaml
from pathlib import Path
from . import config

app = typer.Typer()

from . import actions

@app.command()
def ingest(
    source: str = typer.Option(..., "--source", "-s", help="Source directory (e.g., SD card)"),
    shoot: str = typer.Option(..., "--shoot", "-n", help="Name of the shoot (e.g., '2025-09-15_Stockholm_Broll')"),
):
    """
    Ingests footage from a source to the laptop and archive.
    """
    typer.echo(f"Starting ingest for shoot '{shoot}'...")
    
    # Load configuration
    app_config = config.load_config()
    
    # Get locations
    laptop_dest = config.get_location(app_config, "laptop")
    archive_dest = config.get_location(app_config, "archive_hdd")
    
    actions.ingest_shoot(source, shoot, laptop_dest, archive_dest)

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
