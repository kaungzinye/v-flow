def create_select_file(shoot_name: str, file_name: str, tags_str: str, work_ssd_path: Path, archive_path: Path):
    """
    Tags a graded select, copies it to the archive and the local SSD selects folder.
    """
    # Define paths
    export_file_path = work_ssd_path / shoot_name / "03_Exports" / file_name
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

    # 3. Metadata Tagging
    tagged_file_path = _tag_media_file(export_file_path, tags_str)

    # 4. Copy to Archive
    typer.echo(f"Copying tagged select to archive: {archive_selects_dir}")
    if not copy_and_verify(tagged_file_path, archive_selects_dir):
        typer.echo("Aborting due to archive copy failure.", err=True)
        tagged_file_path.unlink() # Clean up temp file
        raise typer.Exit(code=1)
        
    # 5. Copy to SSD Selects folder
    typer.echo(f"Copying tagged select to SSD: {ssd_selects_dir}")
    if not copy_and_verify(tagged_file_path, ssd_selects_dir):
        # This is not a critical failure, the file is archived. Warn the user.
        typer.echo("Warning: Could not copy select to SSD. It is safely in the archive.", err=True)

    # 6. Cleanup
    tagged_file_path.unlink()
    
    typer.echo("\nCreate select complete.")