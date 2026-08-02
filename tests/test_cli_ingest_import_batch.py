import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import import_batch
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    archive = tmp_path / "archive"
    laptop = tmp_path / "laptop"
    exports = tmp_path / "exports"
    for path in (archive, laptop, exports):
        path.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "locations": {
                    "archive": str(archive),
                    "exports": str(exports),
                    "working": {"laptop": str(laptop)},
                },
            }
        )
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    return archive, laptop


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_ingest_preserves_hierarchy_and_writes_checksum_manifest(tmp_path, monkeypatch):
    archive, laptop = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "PRIVATE" / "CLIP" / "A001.MP4", b"camera-original")
    _write(source / "PRIVATE" / "CLIP" / "A001.XML", b"sidecar")
    _write(source / "MISC" / "INDEX.DAT", b"companion")

    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            str(source),
            "--shoot",
            "2026-08-02_Stockholm",
            "--import-batch",
            "card-a",
        ],
    )

    assert result.exit_code == 0, result.output
    batch = archive / "Camera Originals" / "2026-08-02_Stockholm" / "card-a"
    assert (batch / "contents" / "PRIVATE" / "CLIP" / "A001.MP4").read_bytes() == b"camera-original"
    assert (batch / "contents" / "PRIVATE" / "CLIP" / "A001.XML").read_bytes() == b"sidecar"
    assert (batch / "contents" / "MISC" / "INDEX.DAT").read_bytes() == b"companion"
    assert list(laptop.rglob("*")) == []

    manifest = json.loads((batch / "manifest.json").read_text())
    assert manifest["checksum_algorithm"] == "sha256"
    assert manifest["shoot_id"] == "2026-08-02_Stockholm"
    assert manifest["import_batch_id"] == "card-a"
    assert manifest["ingested_at"]
    entries = {entry["relative_path"]: entry for entry in manifest["files"]}
    assert entries["PRIVATE/CLIP/A001.MP4"]["byte_size"] == len(b"camera-original")
    assert len(entries["PRIVATE/CLIP/A001.MP4"]["checksum"]) == 64
    assert "Retained copies: 1 (Archive only)" in result.output


def test_repeated_camera_filenames_are_isolated_by_import_batch(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first / "CLIP" / "C0001.MP4", b"first-card")
    _write(second / "CLIP" / "C0001.MP4", b"second-card")

    for source, batch_id in ((first, "card-a"), (second, "card-b")):
        result = runner.invoke(
            app,
            ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", batch_id],
        )
        assert result.exit_code == 0, result.output

    shoot = archive / "Camera Originals" / "Shoot"
    assert (shoot / "card-a" / "contents" / "CLIP" / "C0001.MP4").read_bytes() == b"first-card"
    assert (shoot / "card-b" / "contents" / "CLIP" / "C0001.MP4").read_bytes() == b"second-card"


def test_same_name_and_size_with_different_content_is_rejected(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first / "C0001.MP4", b"AAAA")
    _write(second / "C0001.MP4", b"BBBB")

    initial = runner.invoke(
        app,
        ["ingest", "-s", str(first), "-n", "Shoot", "--import-batch", "card-a"],
    )
    conflict = runner.invoke(
        app,
        ["ingest", "-s", str(second), "-n", "Shoot", "--import-batch", "card-a"],
    )

    assert initial.exit_code == 0, initial.output
    assert conflict.exit_code == 1
    assert "immutable" in conflict.output
    archived = archive / "Camera Originals" / "Shoot" / "card-a" / "contents" / "C0001.MP4"
    assert archived.read_bytes() == b"AAAA"


def test_interrupted_ingest_retries_without_recopying_verified_files(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "card"
    _write(source / "A.MP4", b"first")
    _write(source / "nested" / "B.XML", b"second")

    original_copy = import_batch._copy_verified
    attempts = 0

    def fail_second_copy(source_file, destination, expected_checksum):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_copy(source_file, destination, expected_checksum)

    monkeypatch.setattr(import_batch, "_copy_verified", fail_second_copy)
    ingest_args = [
        "ingest",
        "-s",
        str(source),
        "-n",
        "Shoot",
        "--import-batch",
        "card-a",
    ]
    first = runner.invoke(
        app,
        ingest_args,
    )
    assert first.exit_code == 1

    batches = list((archive / "Camera Originals" / "Shoot").iterdir())
    assert len(batches) == 1
    batch = batches[0]
    first_copy = batch / "contents" / "A.MP4"
    assert first_copy.read_bytes() == b"first"
    assert not (batch / "manifest.json").exists()
    assert (batch / ".manifest.pending.json").exists()

    _write(source / "nested" / "B.XML", b"change")
    conflicting_retry = runner.invoke(
        app,
        ingest_args,
    )
    assert conflicting_retry.exit_code == 1
    assert "belongs to different source content" in conflicting_retry.output
    assert first_copy.read_bytes() == b"first"

    _write(source / "nested" / "B.XML", b"second")
    monkeypatch.setattr(import_batch, "_copy_verified", original_copy)
    retry = runner.invoke(
        app,
        ingest_args,
    )

    assert retry.exit_code == 0, retry.output
    assert "1 copied, 1 already verified" in retry.output
    assert (batch / "contents" / "nested" / "B.XML").read_bytes() == b"second"
    assert (batch / "manifest.json").exists()


def test_unavailable_working_location_does_not_block_archive_ingest(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    config = yaml.safe_load(vflow_config.CONFIG_PATH.read_text())
    config["locations"]["working"]["laptop"] = str(tmp_path / "unavailable-laptop")
    vflow_config.CONFIG_PATH.write_text(yaml.safe_dump(config))
    source = tmp_path / "card"
    _write(source / "C0001.MP4", b"original")

    result = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", "card-a"],
    )

    assert result.exit_code == 0, result.output
    archived = archive / "Camera Originals" / "Shoot" / "card-a" / "contents" / "C0001.MP4"
    assert archived.read_bytes() == b"original"


def test_generated_import_batch_identity_is_stable_for_retries(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "card"
    _write(source / "C0001.MP4", b"original")
    args = ["ingest", "-s", str(source), "-n", "Shoot"]

    first = runner.invoke(app, args)
    retry = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert retry.exit_code == 0, retry.output
    assert "0 copied, 1 already verified" in retry.output
    assert len(list((archive / "Camera Originals" / "Shoot").iterdir())) == 1
