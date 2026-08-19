from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app
from vflow import config as vflow_config


runner = CliRunner()


def _write_video(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_ingest_with_files_range_filter(tmp_path, monkeypatch):
    """
    Ingest only a numeric range from an SD-like source using --files C3300-C3349
    and confirm exactly 50 files land in the archive.
    """
    archive_root = tmp_path / "archive"
    laptop_root = tmp_path / "laptop"
    work_root = tmp_path / "work"
    archive_root.mkdir(parents=True, exist_ok=True)
    laptop_root.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    sd_root = tmp_path / "sd" / "CLIP"

    # SD contains a larger span of files C3280..C3370
    for n in range(3280, 3371):
        _write_video(sd_root / f"C{n:04d}.MP4", f"sd-{n}".encode("utf-8"))

    # Configure locations
    tmp_config = tmp_path / "config.yml"
    tmp_config.write_text(
        f"locations:\n"
        f"  archive: \"{archive_root}\"\n"
        f"  exports: \"{tmp_path / 'exports'}\"\n"
        f"  working:\n"
        f"    laptop: \"{laptop_root}\"\n"
        f"    work_ssd: \"{work_root}\"\n"
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", tmp_config)

    # Ingest only a subset using files filter
    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            str(sd_root),
            "--shoot",
            "TestShoot",
            "--files",
            "C3300-C3349",
        ],
    )

    assert result.exit_code == 0, result.output

    # The selected files land flat in the Shoot folder.
    shoot = archive_root / "Video" / "RAW" / "TestShoot"
    archived_files = sorted(
        p.name for p in shoot.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    assert len(archived_files) == 50
    assert archived_files[0] == "C3300.MP4"
    assert archived_files[-1] == "C3349.MP4"
