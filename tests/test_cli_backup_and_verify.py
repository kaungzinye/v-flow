import os
from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app
from vflow import config as vflow_config


runner = CliRunner()


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_backup_and_verify_archive_wide(tmp_path, monkeypatch):
    """
    End-to-end test:
    - creates a fake archive root and a fake ingest folder
    - runs `backup` into a subfolder under the archive
    - runs `verify-backup` in archive-wide mode to confirm coverage
    """
    # Arrange archive + source structure
    archive_root = tmp_path / "archive"
    archive_root.mkdir()

    # Simulate some files already in archive (different shoot folder)
    existing_shoot = archive_root / "Video" / "RAW" / "2025-12-23_Ingest_Part2"
    _write_file(existing_shoot / "C4228.MP4", b"already archived")

    # Ingest folder on desktop with mix of already-archived + many new files
    ingest = tmp_path / "Desktop" / "Ingest"
    # duplicate of existing archive file
    _write_file(ingest / "2025-12-23_Ingest_Part2" / "C4228.MP4", b"already archived")
    # create a bunch of new files across a couple of ingest folders
    new_files = []
    for i in range(50):
        folder = "2026-01-01_Ingest" if i < 25 else "2026-01-02_Ingest"
        stem = f"C5{i:03d}"
        path = ingest / folder / f"{stem}.MP4"
        _write_file(path, f"file-{i}".encode("utf-8"))
        new_files.append(path)

    # Point CONFIG_PATH to our fake config
    tmp_config = tmp_path / "config.yml"
    tmp_config.write_text(
        f"locations:\n"
        f"  laptop: \"{ingest}\"\n"
        f"  work_ssd: \"{tmp_path / 'work'}\"\n"
        f"  archive_hdd: \"{archive_root}\"\n"
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", tmp_config)

    # Act: run backup
    result_backup = runner.invoke(
        app,
        [
            "backup",
            "--source",
            str(ingest),
            "--destination",
            "Video/RAW/Desktop_Ingest",
        ],
    )

    assert result_backup.exit_code == 0, result_backup.output
    assert "unique files copied" in result_backup.output

    # Verify that all new files are present at the expected destination
    backup_folder = archive_root / "Video" / "RAW" / "Desktop_Ingest"
    for nf in new_files:
        rel = nf.relative_to(ingest)
        assert (backup_folder / rel).exists()

    # Act: archive-wide verify that ingest is fully safe in archive
    result_verify = runner.invoke(
        app,
        [
            "verify-backup",
            "--source",
            str(ingest),
            "--destination",
            str(archive_root),
            "--archive-wide",
        ],
    )

    assert result_verify.exit_code == 0, result_verify.output
    assert "Backup verification PASSED" in result_verify.output

