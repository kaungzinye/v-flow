from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app
from vflow import config as vflow_config


runner = CliRunner()


def _write_video(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_ingest_report_classifies_missing_in_laptop_and_archive(tmp_path, monkeypatch):
    """
    Build a small SD card tree and partial laptop/archive trees, run ingest-report,
    and assert that counts for missing files make sense.
    """
    archive_root = tmp_path / "archive"
    laptop_root = tmp_path / "laptop"
    sd_root = tmp_path / "sd" / "CLIP"

    # SD has three files
    _write_video(sd_root / "C1000.MP4", b"on-sd-only")
    _write_video(sd_root / "C1001.MP4", b"in-laptop-and-sd")
    _write_video(sd_root / "C1002.MP4", b"in-archive-and-sd")

    # Laptop already has C1001
    _write_video(laptop_root / "SomeShoot" / "C1001.MP4", b"in-laptop-and-sd")

    # Archive RAW already has C1002
    _write_video(archive_root / "Video" / "RAW" / "SomeShoot" / "C1002.MP4", b"in-archive-and-sd")

    # Configure locations
    tmp_config = tmp_path / "config.yml"
    tmp_config.write_text(
        f"locations:\n"
        f"  laptop: \"{laptop_root}\"\n"
        f"  work_ssd: \"{tmp_path / 'work'}\"\n"
        f"  archive_hdd: \"{archive_root}\"\n"
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", tmp_config)

    result = runner.invoke(
        app,
        [
            "ingest-report",
            "--source",
            str(sd_root),
            "--priority-day",
            "1",
            "--priority-month",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output

    # Summary lines should classify SD files correctly:
    # - C1001: already in laptop
    # - C1002: already in archive
    # - C1000: in neither
    assert "On both laptop + archive: 0" in result.output or "On both laptop + archive: 0" in result.output
    assert "On laptop only:" in result.output
    assert "On archive only:" in result.output
    assert "On neither (not ingested): 1" in result.output

