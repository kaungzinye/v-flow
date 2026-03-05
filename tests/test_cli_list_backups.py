from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app
from vflow import config as vflow_config


runner = CliRunner()


def test_list_backups_on_simple_tree(tmp_path, monkeypatch):
    """
    Create a fake archive structure with two backup folders and ensure list-backups
    reports them in the output.
    """
    archive_root = tmp_path / "archive"
    base = archive_root / "Video" / "RAW" / "Desktop_Ingest"
    (base / "BackupA").mkdir(parents=True)
    (base / "BackupB").mkdir(parents=True)

    (base / "BackupA" / "file1.txt").write_text("one")
    (base / "BackupB" / "file2.txt").write_text("two")

    # Configure CONFIG_PATH to point at our fake root
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
            "list-backups",
            "--subpath",
            "Video/RAW/Desktop_Ingest",
        ],
    )

    assert result.exit_code == 0, result.output
    # Both backup folders should be mentioned
    assert "BackupA" in result.output
    assert "BackupB" in result.output

