from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app
from vflow import config as vflow_config


runner = CliRunner()


def _write(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_backup_includes_braw_and_mov(tmp_path, monkeypatch):
    """
    Ensure that .braw files are treated as video alongside .mov/.mp4 and
    get picked up by backup.
    """
    archive_root = tmp_path / "archive"
    source = tmp_path / "source"
    archive_root.mkdir(parents=True, exist_ok=True)

    # Simulate a folder with a mix of Blackmagic RAW and ProRes/H.264 MOV/MP4 files
    _write(source / "A001_0001.braw", b"braw-data")
    _write(source / "A001_0001.mov", b"prores-data")
    _write(source / "clip0001.MP4", b"h264-data")
    # RED and Canon RAW containers
    _write(source / "A001C001_0101AB.R3D", b"red-raw")
    _write(source / "A001C001_0101AB.CRM", b"canon-raw")
    # Phone-style HEVC/H.264 filenames (iOS / Android) - still .mov/.mp4 containers
    _write(source / "IMG_1234.MOV", b"iphone-hevc")
    _write(source / "VID_20260305_123456.MP4", b"android-h264")

    tmp_config = tmp_path / "config.yml"
    tmp_config.write_text(
        f"locations:\n"
        f"  laptop: \"{tmp_path / 'laptop'}\"\n"
        f"  work_ssd: \"{tmp_path / 'work'}\"\n"
        f"  archive_hdd: \"{archive_root}\"\n"
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", tmp_config)

    result = runner.invoke(
        app,
        [
            "backup",
            "--source",
            str(source),
            "--destination",
            "Video/RAW/BrawTest",
        ],
    )

    assert result.exit_code == 0, result.output

    dest = archive_root / "Video" / "RAW" / "BrawTest"
    files = sorted(p.name for p in dest.rglob("*") if p.is_file())
    # Core formats
    assert "A001_0001.braw" in files
    assert "A001_0001.mov" in files
    assert "clip0001.MP4" in files
    # Exotic RAW containers
    assert "A001C001_0101AB.R3D" in files
    assert "A001C001_0101AB.CRM" in files
    # Phone naming patterns
    assert "IMG_1234.MOV" in files
    assert "VID_20260305_123456.MP4" in files

