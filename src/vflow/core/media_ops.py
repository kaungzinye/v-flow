from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer


def tag_media_file(source_file: Path, tags_str: str) -> Path:
    """
    Embed metadata tags into a media file via ffmpeg and apply macOS Finder tags.
    Returns the path to the new tagged copy (caller is responsible for cleanup).
    """
    tags_list = [tag.strip() for tag in tags_str.split(",")]

    tagged_file_path = source_file.with_name(
        f"{source_file.stem}_tagged{source_file.suffix}"
    )

    typer.echo("Embedding universal metadata with ffmpeg...")
    try:
        ffmpeg_cmd = [
            "ffmpeg",
            "-i",
            str(source_file),
            "-metadata",
            f"comment={tags_str}",
            "-metadata",
            f"keywords={tags_str}",
            "-codec",
            "copy",
            str(tagged_file_path),
        ]
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        typer.echo(f"Error with ffmpeg: {e}", err=True)
        typer.echo(
            "Please ensure ffmpeg is installed and in your PATH.", err=True
        )
        raise typer.Exit(code=1)

    typer.echo("Applying macOS Finder tags...")
    try:
        tag_plist = "".join(f"<string>{tag}</string>" for tag in tags_list)
        bplist_cmd = (
            "xattr -w com.apple.metadata:_kMDItemUserTags "
            '\'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0">'
            f"<array>{tag_plist}</array></plist>' "
            f'"{str(tagged_file_path)}"'
        )
        subprocess.run(
            bplist_cmd, shell=True, check=True, capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        typer.echo(f"Could not apply macOS tags: {e}", err=True)

    return tagged_file_path


def copy_metadata_between_files(source_file: Path, target_file: Path) -> bool:
    """
    Copy metadata from a source file to a target file using ffmpeg.
    Preserves video/audio streams from target, adds metadata from source.
    Returns True if successful, False otherwise.
    """
    if not source_file.exists() or not target_file.exists():
        return False

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
            "-y",
            str(temp_output),
        ]
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)

        shutil.move(str(temp_output), str(target_file))
        return True

    except FileNotFoundError:
        typer.echo(
            "\nError: ffmpeg not found. Please install it and ensure it's in your PATH.",
            err=True,
        )
        return False
    except subprocess.CalledProcessError as e:
        typer.echo(f"\nWarning: Could not copy metadata: {e.stderr}", err=True)
        if temp_output.exists():
            temp_output.unlink()
        return False
