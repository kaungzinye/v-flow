from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer

from .core.fs_ops import copy_and_verify
from .core.media_ops import tag_media_file, copy_metadata_between_files


def archive_file(
    shoot_name: str,
    file_name: str,
    tags_str: str,
    keep_log: bool,
    work_ssd_path: Path,
    archive_path: Path,
) -> None:
    """
    Tags a final rendered file, copies it to the archive Graded folder,
    and optionally cleans up source files.
    """
    export_file_path = work_ssd_path / shoot_name / "03_Exports" / file_name
    archive_graded_dir = archive_path / "Video" / "Graded"

    if not export_file_path.exists():
        typer.echo(f"Export file not found: {export_file_path}", err=True)
        raise typer.Exit(code=1)

    try:
        archive_graded_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(
            f"Could not create destination directories: {e}", err=True
        )
        raise typer.Exit(code=1)

    tagged_file_path = tag_media_file(export_file_path, tags_str)

    typer.echo(f"Copying tagged file to archive: {archive_graded_dir}")
    if not copy_and_verify(tagged_file_path, archive_graded_dir):
        typer.echo("Aborting cleanup due to copy failure.", err=True)
        tagged_file_path.unlink()
        raise typer.Exit(code=1)

    tagged_file_path.unlink()

    if not keep_log:
        try:
            source_folder = work_ssd_path / shoot_name / "01_Source"
            if source_folder.exists():
                typer.echo(
                    f"Cleaning up source files from {source_folder}..."
                )
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
                for video_file in source_folder.iterdir():
                    if (
                        video_file.is_file()
                        and video_file.suffix.lower() in video_extensions
                    ):
                        video_file.unlink()
                        typer.echo(f"Deleted: {video_file.name}")
        except Exception as e:
            typer.echo(
                f"Warning: Could not clean up source files: {e}", err=True
            )

    typer.echo("\nArchive complete.")


def copy_metadata_folder(source_folder: Path, target_folder: Path) -> None:
    """
    Copies metadata from files in source_folder to matching files in target_folder.
    Matches by filename stem (ignoring extension).
    """
    if not target_folder.exists() or not target_folder.is_dir():
        typer.echo(f"Target folder not found: {target_folder}", err=True)
        raise typer.Exit(code=1)

    if not source_folder.exists() or not source_folder.is_dir():
        typer.echo(f"Source folder not found: {source_folder}", err=True)
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
    target_files = [
        f
        for f in target_folder.iterdir()
        if f.is_file() and f.suffix.lower() in video_extensions
    ]

    if not target_files:
        typer.echo("No files found in the target directory.")
        return

    success_count = 0
    fail_count = 0

    with typer.progressbar(target_files, label="Processing files") as progress:
        for target_file in progress:
            source_files = list(source_folder.glob(f"{target_file.stem}.*"))

            if not source_files:
                typer.echo(
                    f"\nWarning: No matching source file found for '{target_file.name}'. Skipping.",
                    err=True,
                )
                fail_count += 1
                continue

            source_file = source_files[0]
            temp_output = target_file.with_name(
                f"{target_file.stem}_temp_meta{target_file.suffix}"
            )

            try:
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i",
                    str(target_file),
                    "-i",
                    str(source_file),
                    "-map",
                    "0:v",
                    "-map",
                    "0:a",
                    "-map_metadata",
                    "1",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    str(temp_output),
                ]
                subprocess.run(
                    ffmpeg_cmd + ["-y"],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                shutil.move(str(temp_output), str(target_file))
                success_count += 1

            except FileNotFoundError:
                typer.echo(
                    "\nError: ffmpeg not found. Please install it and ensure it's in your PATH.",
                    err=True,
                )
                raise typer.Exit(code=1)
            except subprocess.CalledProcessError as e:
                typer.echo(
                    f"\nError processing '{target_file.name}': {e.stderr}",
                    err=True,
                )
                fail_count += 1
                if temp_output.exists():
                    temp_output.unlink()

    typer.echo(
        f"\nMetadata copy complete. {success_count} files updated, {fail_count} files skipped."
    )


def create_select_file(
    shoot_name: str,
    file_name: str,
    tags_str: str,
    work_ssd_path: Path,
    archive_path: Path,
) -> None:
    """
    Tags a graded select, copies metadata from source, and distributes it to the
    archive and the local SSD selects folder.
    """
    export_file_path = work_ssd_path / shoot_name / "03_Exports" / file_name
    source_folder = work_ssd_path / shoot_name / "01_Source"
    archive_selects_dir = archive_path / "Video" / "Graded_Selects" / shoot_name
    ssd_selects_dir = work_ssd_path / shoot_name / "05_Graded_Selects"

    if not export_file_path.exists():
        typer.echo(f"Export file not found: {export_file_path}", err=True)
        raise typer.Exit(code=1)

    try:
        archive_selects_dir.mkdir(parents=True, exist_ok=True)
        ssd_selects_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(
            f"Could not create destination directories: {e}", err=True
        )
        raise typer.Exit(code=1)

    typer.echo("Tagging file with new metadata...")
    tagged_file_path = tag_media_file(export_file_path, tags_str)

    if source_folder.exists():
        source_files = list(source_folder.glob(f"{export_file_path.stem}.*"))
        if source_files:
            source_file = source_files[0]
            typer.echo(f"Copying metadata from source file: {source_file.name}")
            if copy_metadata_between_files(source_file, tagged_file_path):
                typer.echo("✓ Metadata copied successfully from source file.")
            else:
                typer.echo(
                    "⚠ Warning: Could not copy metadata from source file. Continuing with tags only."
                )
        else:
            typer.echo(
                f"⚠ No matching source file found in 01_Source for '{export_file_path.stem}'. Skipping metadata copy."
            )
    else:
        typer.echo(
            f"⚠ Source folder not found: {source_folder}. Skipping metadata copy."
        )

    typer.echo(f"\nCopying tagged select to archive: {archive_selects_dir}")
    archive_dest_file = archive_selects_dir / tagged_file_path.name
    should_copy_to_archive = True
    if archive_dest_file.exists():
        try:
            if (
                tagged_file_path.stat().st_size
                == archive_dest_file.stat().st_size
            ):
                typer.echo(
                    "⚠ File already exists in archive (same size). Skipping archive copy."
                )
                should_copy_to_archive = False
            else:
                typer.echo(
                    "⚠ File exists in archive but with different size. Copying anyway."
                )
        except Exception:
            typer.echo(
                "⚠ Could not check size of existing file in archive. Copying anyway."
            )

    if should_copy_to_archive:
        if not copy_and_verify(tagged_file_path, archive_selects_dir):
            typer.echo("Aborting due to archive copy failure.", err=True)
            tagged_file_path.unlink()
            raise typer.Exit(code=1)
        else:
            typer.echo("✓ File copied to archive.")

    typer.echo(f"Copying tagged select to SSD: {ssd_selects_dir}")
    ssd_dest_file = ssd_selects_dir / tagged_file_path.name
    should_copy_to_ssd = True
    if ssd_dest_file.exists():
        try:
            if (
                tagged_file_path.stat().st_size
                == ssd_dest_file.stat().st_size
            ):
                typer.echo(
                    "⚠ File already exists in SSD selects folder (same size). Skipping SSD copy."
                )
                should_copy_to_ssd = False
            else:
                typer.echo(
                    "⚠ File exists in SSD selects but with different size. Copying anyway."
                )
        except Exception:
            typer.echo(
                "⚠ Could not check size of existing file on SSD. Copying anyway."
            )

    if should_copy_to_ssd:
        if not copy_and_verify(tagged_file_path, ssd_selects_dir):
            typer.echo(
                "Warning: Could not copy select to SSD. It is safely in the archive.",
                err=True,
            )
        else:
            typer.echo("✓ File copied to SSD selects folder.")

    tagged_file_path.unlink()

    typer.echo("\n✓ Create select complete.")
