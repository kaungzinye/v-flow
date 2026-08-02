from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import export_archive
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    archive = tmp_path / "archive"
    exports = tmp_path / "local-exports" / "Exports"
    working = tmp_path / "working"
    for path in (archive, exports, working):
        path.mkdir(parents=True)
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "locations": {
                    "archive": str(archive),
                    "exports": str(exports),
                    "working": {"work_ssd": str(working)},
                },
            }
        )
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    return archive, exports, working


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_archives_final_video_by_project_and_retains_every_local_file(tmp_path, monkeypatch):
    archive, exports, working = _configure(tmp_path, monkeypatch)
    source = exports / "Final Videos" / "Stockholm Stories" / "episode.mov"
    camera_original = archive / "Camera Originals" / "Shoot" / "card" / "contents" / "A.mov"
    working_copy = working / "Shoot" / "A.mov"
    _write(source, b"final-video")
    _write(camera_original, b"camera-original")
    _write(working_copy, b"working-copy")

    result = runner.invoke(
        app,
        ["archive", "--type", "final-video", "--project", "Stockholm Stories", "--file", "episode.mov"],
    )

    assert result.exit_code == 0, result.output
    assert (archive / "Exports" / "Final Videos" / "Stockholm Stories" / "episode.mov").read_bytes() == b"final-video"
    assert source.read_bytes() == b"final-video"
    assert camera_original.read_bytes() == b"camera-original"
    assert working_copy.read_bytes() == b"working-copy"
    assert "Copied: 1" in result.output
    assert "Verified: 1" in result.output
    assert "Retained local files: 1" in result.output


def test_archives_graded_select_by_shoot(tmp_path, monkeypatch):
    archive, exports, _ = _configure(tmp_path, monkeypatch)
    source = exports / "Graded Selects" / "2026-08-02_Stockholm" / "A001.mov"
    _write(source, b"graded-select")

    result = runner.invoke(
        app,
        ["archive", "--type", "graded-select", "--shoot", "2026-08-02_Stockholm", "--file", "A001.mov"],
    )

    assert result.exit_code == 0, result.output
    destination = archive / "Exports" / "Graded Selects" / "2026-08-02_Stockholm" / "A001.mov"
    assert destination.read_bytes() == b"graded-select"
    assert source.read_bytes() == b"graded-select"


def test_archive_dry_run_reports_copy_without_creating_archive_directories(tmp_path, monkeypatch):
    archive, exports, _ = _configure(tmp_path, monkeypatch)
    source = exports / "Final Videos" / "Project" / "final.mp4"
    _write(source, b"render")

    result = runner.invoke(
        app,
        ["archive", "--type", "final-video", "--project", "Project", "--file", "final.mp4", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run: no files changed" in result.output
    assert "Would copy: 1" in result.output
    assert not (archive / "Exports").exists()
    assert source.read_bytes() == b"render"


def test_repeated_archive_verifies_and_skips_identical_content(tmp_path, monkeypatch):
    archive, exports, _ = _configure(tmp_path, monkeypatch)
    source = exports / "Final Videos" / "Project" / "final.mp4"
    _write(source, b"render")
    args = ["archive", "--type", "final-video", "--project", "Project", "--file", "final.mp4"]

    first = runner.invoke(app, args)
    retry = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert retry.exit_code == 0, retry.output
    assert "Copied: 0" in retry.output
    assert "Verified: 1" in retry.output
    assert "Skipped: 1" in retry.output


def test_archive_conflict_stops_without_changing_either_file(tmp_path, monkeypatch):
    archive, exports, _ = _configure(tmp_path, monkeypatch)
    source = exports / "Final Videos" / "Project" / "same-size.mp4"
    destination = archive / "Exports" / "Final Videos" / "Project" / "same-size.mp4"
    _write(source, b"AAAA")
    _write(destination, b"BBBB")

    result = runner.invoke(
        app,
        ["archive", "--type", "final-video", "--project", "Project", "--file", "same-size.mp4"],
    )

    assert result.exit_code == 1
    assert "Archive conflict" in result.output
    assert source.read_bytes() == b"AAAA"
    assert destination.read_bytes() == b"BBBB"


def test_verification_failure_cleans_partial_copy_and_allows_retry(tmp_path, monkeypatch):
    archive, exports, _ = _configure(tmp_path, monkeypatch)
    source = exports / "Graded Selects" / "Shoot" / "select.mov"
    destination = archive / "Exports" / "Graded Selects" / "Shoot" / "select.mov"
    _write(source, b"select")
    real_checksum = export_archive._checksum
    checks = 0

    def fail_copied_file(path):
        nonlocal checks
        checks += 1
        if checks == 2:
            return "not-the-source-checksum"
        return real_checksum(path)

    monkeypatch.setattr(export_archive, "_checksum", fail_copied_file)
    args = ["archive", "--type", "graded-select", "--shoot", "Shoot", "--file", "select.mov"]
    failed = runner.invoke(app, args)

    assert failed.exit_code == 1
    assert "checksum verification failed" in failed.output
    assert source.read_bytes() == b"select"
    assert not destination.exists()
    assert not destination.with_name(".select.mov.vflow-part").exists()

    monkeypatch.setattr(export_archive, "_checksum", real_checksum)
    retry = runner.invoke(app, args)
    assert retry.exit_code == 0, retry.output
    assert destination.read_bytes() == b"select"
