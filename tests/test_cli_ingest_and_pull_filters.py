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
        f"  laptop: \"{laptop_root}\"\n"
        f"  work_ssd: \"{work_root}\"\n"
        f"  archive_hdd: \"{archive_root}\"\n"
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

    # Archive RAW for this shoot should contain exactly those 50 files
    raw_shoot = archive_root / "Video" / "RAW" / "TestShoot"
    assert raw_shoot.exists()
    archived_files = sorted(p.name for p in raw_shoot.iterdir() if p.is_file())
    assert len(archived_files) == 50
    assert archived_files[0] == "C3300.MP4"
    assert archived_files[-1] == "C3349.MP4"


def test_pull_with_mixed_patterns(tmp_path, monkeypatch):
    """
    Pull from archive using a mix of numeric range and plain substring patterns
    and confirm only matching files are copied to 01_Source.
    """
    archive_root = tmp_path / "archive"
    work_root = tmp_path / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    raw_shoot = archive_root / "Video" / "RAW" / "TestShoot"

    # Archive has a mixture of camera clips and IMG* exports
    for n in range(3300, 3350):
        _write_video(raw_shoot / f"C{n:04d}.MP4", f"raw-{n}".encode("utf-8"))
    _write_video(raw_shoot / "IMG_0001.MOV", b"img-1")
    _write_video(raw_shoot / "IMG_0002.MOV", b"img-2")

    # Configure locations
    tmp_config = tmp_path / "config.yml"
    tmp_config.write_text(
        f"locations:\n"
        f"  laptop: \"{tmp_path / 'laptop'}\"\n"
        f"  work_ssd: \"{work_root}\"\n"
        f"  archive_hdd: \"{archive_root}\"\n"
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", tmp_config)

    # Pull only a numeric range and a specific IMG file
    result = runner.invoke(
        app,
        [
            "pull",
            "--shoot",
            "TestShoot",
            "--source",
            "raw",
            "--files",
            "C3310-C3319",
            "--files",
            "IMG_0002",
        ],
    )

    assert result.exit_code == 0, result.output

    project_dir = work_root / "TestShoot"
    source_dir = project_dir / "01_Source"
    assert source_dir.exists()

    pulled = sorted(p.name for p in source_dir.iterdir() if p.is_file())
    # 10 C-clips + 1 IMG file
    assert len(pulled) == 11
    assert "IMG_0002.MOV" in pulled
    assert "IMG_0001.MOV" not in pulled
    assert pulled[0] == "C3310.MP4"
    assert "C3319.MP4" in pulled

