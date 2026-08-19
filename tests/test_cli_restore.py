from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import restore_service
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    archive = tmp_path / "archive"
    destination = tmp_path / "restored"
    archive.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "locations": {
                    "archive": str(archive),
                    "exports": str(tmp_path / "exports"),
                    "working": {"work_ssd": str(tmp_path / "working")},
                },
            }
        )
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    return archive, destination


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_restore_requires_explicit_source_and_destination():
    missing_source = runner.invoke(app, ["restore", "--destination", "/tmp/output"])
    missing_destination = runner.invoke(app, ["restore", "--source", "asset"])

    assert missing_source.exit_code != 0
    assert "--source" in missing_source.output
    assert missing_destination.exit_code != 0
    assert "--destination" in missing_destination.output


def test_restore_dry_run_reports_paths_sizes_copies_skips_and_conflicts(
    tmp_path, monkeypatch
):
    archive, destination = _configure(tmp_path, monkeypatch)
    source = archive / "Camera Originals" / "Shoot" / "Batch" / "contents"
    _write(source / "copy.mov", b"copy")
    _write(source / "nested" / "skip.xml", b"same")
    _write(source / "conflict.wav", b"archive")
    _write(destination / "nested" / "skip.xml", b"same")
    _write(destination / "conflict.wav", b"locally")

    result = runner.invoke(
        app,
        [
            "restore",
            "--source",
            str(source),
            "--destination",
            str(destination),
            "--dry-run",
        ],
    )

    assert result.exit_code == 1, result.output
    assert f"Archived source: {source}" in result.output
    assert f"Destination: {destination}" in result.output
    assert "COPY:" in result.output and "copy.mov" in result.output
    assert "SKIP:" in result.output and "skip.xml" in result.output
    assert "CONFLICT:" in result.output and "conflict.wav" in result.output
    assert "Source: 3 files, 15 bytes" in result.output
    assert "Expected copies: 1 files, 4 bytes" in result.output
    assert "Verified skips: 1" in result.output
    assert "Conflicts: 1" in result.output
    assert not (destination / "copy.mov").exists()


def test_restore_directory_copies_and_verifies_files_without_changing_archive(
    tmp_path, monkeypatch
):
    archive, destination = _configure(tmp_path, monkeypatch)
    source = archive / "Exports" / "Final Videos" / "Project"
    _write(source / "final.mov", b"final-video")
    _write(source / "notes" / "delivery.txt", b"approved")
    before = {
        path.relative_to(archive): path.read_bytes()
        for path in archive.rglob("*")
        if path.is_file()
    }

    result = runner.invoke(
        app,
        ["restore", "--source", str(source), "--destination", str(destination)],
    )

    assert result.exit_code == 0, result.output
    assert (destination / "final.mov").read_bytes() == b"final-video"
    assert (destination / "notes" / "delivery.txt").read_bytes() == b"approved"
    assert "Restore complete: 2 copied, 0 already verified, 2 total" in result.output
    assert "Archive changed: no" in result.output
    after = {
        path.relative_to(archive): path.read_bytes()
        for path in archive.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_restore_file_to_explicit_file_destination_and_skips_verified_content(
    tmp_path, monkeypatch
):
    archive, destination_root = _configure(tmp_path, monkeypatch)
    source = archive / "Exports" / "Graded Selects" / "Shoot" / "A001.mov"
    destination = destination_root / "chosen-name.mov"
    _write(source, b"graded-select")
    _write(destination, b"graded-select")

    result = runner.invoke(
        app,
        ["restore", "--source", str(source), "--destination", str(destination)],
    )

    assert result.exit_code == 0, result.output
    assert "Restore complete: 0 copied, 1 already verified, 1 total" in result.output
    assert destination.read_bytes() == b"graded-select"
    assert source.read_bytes() == b"graded-select"


def test_restore_conflict_stops_before_copying_any_file(tmp_path, monkeypatch):
    archive, destination = _configure(tmp_path, monkeypatch)
    source = archive / "asset"
    _write(source / "a-copy.mov", b"copy-me")
    _write(source / "z-conflict.mov", b"archive")
    _write(destination / "z-conflict.mov", b"different")

    result = runner.invoke(
        app,
        ["restore", "--source", str(source), "--destination", str(destination)],
    )

    assert result.exit_code == 1
    assert "Restore conflict" in result.output
    assert not (destination / "a-copy.mov").exists()
    assert (destination / "z-conflict.mov").read_bytes() == b"different"
    assert (source / "a-copy.mov").read_bytes() == b"copy-me"


def test_interrupted_restore_cleans_partial_file_and_resumes(tmp_path, monkeypatch):
    archive, destination = _configure(tmp_path, monkeypatch)
    source = archive / "asset"
    _write(source / "a.mov", b"first")
    _write(source / "b.mov", b"second")
    original_copy = restore_service._copy_verified
    attempts = 0

    def interrupt_second_copy(entry, on_bytes=None):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_copy(entry, on_bytes)

    monkeypatch.setattr(restore_service, "_copy_verified", interrupt_second_copy)
    args = ["restore", "--source", str(source), "--destination", str(destination)]
    interrupted = runner.invoke(app, args)

    assert interrupted.exit_code == 1
    assert "retry the same Restore to resume" in interrupted.output
    assert (destination / "a.mov").read_bytes() == b"first"
    assert not (destination / "b.mov").exists()
    assert not (destination / ".b.mov.vflow-part").exists()

    monkeypatch.setattr(restore_service, "_copy_verified", original_copy)
    retry = runner.invoke(app, args)

    assert retry.exit_code == 0, retry.output
    assert "Restore complete: 1 copied, 1 already verified, 2 total" in retry.output
    assert (destination / "b.mov").read_bytes() == b"second"
    assert (source / "a.mov").read_bytes() == b"first"
    assert (source / "b.mov").read_bytes() == b"second"


def test_restore_rejects_sources_outside_and_destinations_inside_archive(
    tmp_path, monkeypatch
):
    archive, destination = _configure(tmp_path, monkeypatch)
    outside = tmp_path / "outside.mov"
    source = archive / "asset.mov"
    _write(outside, b"outside")
    _write(source, b"archive")

    outside_source = runner.invoke(
        app,
        ["restore", "--source", str(outside), "--destination", str(destination)],
    )
    archive_destination = runner.invoke(
        app,
        [
            "restore",
            "--source",
            str(source),
            "--destination",
            str(archive / "copy.mov"),
        ],
    )

    assert outside_source.exit_code == 1
    assert "source must be inside the Archive" in outside_source.output
    assert archive_destination.exit_code == 1
    assert "destination must be outside the Archive" in archive_destination.output
    assert not (archive / "copy.mov").exists()
