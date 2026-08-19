import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import shoot_manifest
from vflow import config as vflow_config
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch) -> Path:
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    laptop = tmp_path / "laptop"
    for path in (archive, exports, laptop):
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
    return archive


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _collection(archive: Path, name: str) -> Path:
    return archive / "Photo" / "RAW" / name


def _manifest(collection: Path) -> dict:
    return json.loads((collection / ".vflow-manifest.json").read_text())


def test_photo_ingest_lands_flat_with_sidecars_and_a_hidden_manifest(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "DCIM" / "100MSDCF" / "DSC00811.ARW", b"first-frame")
    _write(source / "DCIM" / "100MSDCF" / "DSC00811.ARW.pp3", b"rawtherapee-edits")
    _write(source / "DCIM" / "100MSDCF" / "DSC00811.xmp", b"lightroom-edits")
    _write(source / "DCIM" / "100MSDCF" / "DSC00812.ARW", b"second-frame")
    _write(source / "DCIM" / "100MSDCF" / "DSC00811.JPG", b"camera-preview")
    _write(source / "._DSC00811.ARW", b"appledouble")

    result = runner.invoke(
        app,
        [
            "photo-ingest",
            "--source",
            str(source),
            "--collection",
            "20240920 THOR 2024",
            "--import-batch",
            "card-a",
        ],
    )

    assert result.exit_code == 0, result.output
    collection = _collection(archive, "20240920 THOR 2024")
    assert sorted(path.name for path in collection.iterdir()) == [
        ".vflow-manifest.json",
        "DSC00811.ARW",
        "DSC00811.ARW.pp3",
        "DSC00811.xmp",
        "DSC00812.ARW",
    ]
    assert (collection / "DSC00811.ARW.pp3").read_bytes() == b"rawtherapee-edits"

    manifest = _manifest(collection)
    assert manifest["manifest_version"] == 2
    assert manifest["checksum_algorithm"] == "sha256"
    assert manifest["collection"] == "20240920 THOR 2024"
    entries = {entry["name"]: entry for entry in manifest["files"]}
    frame = entries["DSC00811.ARW"]
    assert frame["byte_size"] == len(b"first-frame")
    assert len(frame["checksum"]) == 64
    assert frame["source_relative_path"] == "DCIM/100MSDCF/DSC00811.ARW"
    assert frame["source_name"] == "CARD"
    assert frame["batch_id"] == "card-a"
    assert entries["DSC00811.ARW.pp3"]["sidecar_for"] == "DSC00811.ARW"
    assert entries["DSC00811.xmp"]["sidecar_for"] == "DSC00811.ARW"
    assert len(entries["DSC00811.xmp"]["checksum"]) == 64

    excluded = {item["source_relative_path"]: item for item in manifest["excluded"]}
    assert excluded["DCIM/100MSDCF/DSC00811.JPG"]["reason"] == "non-photo file type"
    assert excluded["._DSC00811.ARW"]["reason"] == "AppleDouble sidecar"
    assert "Retained copies: 1 (Archive only)" in result.output


def test_same_name_and_size_photos_both_land_on_differing_content(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "DSC00001.ARW", b"AAAA")
    _write(second / "DSC00001.ARW", b"BBBB")

    assert runner.invoke(app, ["photo-ingest", "-s", str(first), "-c", "Event"]).exit_code == 0
    result = runner.invoke(app, ["photo-ingest", "-s", str(second), "-c", "Event"])

    assert result.exit_code == 0, result.output
    collection = _collection(archive, "Event")
    assert (collection / "DSC00001.ARW").read_bytes() == b"AAAA"
    assert (collection / "DSC00001_b.ARW").read_bytes() == b"BBBB"
    entries = {entry["name"]: entry for entry in _manifest(collection)["files"]}
    assert entries["DSC00001_b.ARW"]["original_name"] == "DSC00001.ARW"


def test_identical_content_under_another_name_deduplicates(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "DSC00001.ARW", b"one-and-only")
    _write(second / "DSC09999.ARW", b"one-and-only")
    _write(second / "DSC10000.ARW", b"fresh-frame")

    assert runner.invoke(app, ["photo-ingest", "-s", str(first), "-c", "Monday"]).exit_code == 0
    result = runner.invoke(app, ["photo-ingest", "-s", str(second), "-c", "Tuesday"])

    assert result.exit_code == 0, result.output
    assert "1 deduplicated" in result.output
    tuesday = _collection(archive, "Tuesday")
    assert sorted(path.name for path in tuesday.iterdir()) == [
        ".vflow-manifest.json",
        "DSC10000.ARW",
    ]
    skipped = _manifest(tuesday)["deduplicated"]
    assert len(skipped) == 1
    assert skipped[0]["original_name"] == "DSC09999.ARW"
    assert skipped[0]["existing_location"] == "Photo/RAW/Monday/DSC00001.ARW"


def test_sidecars_follow_their_photo_into_a_suffixed_name(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "DSC00001.ARW", b"first-frame")
    _write(second / "DSC00001.ARW", b"recycled-name-other-frame")
    _write(second / "DSC00001.ARW.pp3", b"edits-for-the-second")
    _write(second / "DSC00001.xmp", b"metadata-for-the-second")

    assert runner.invoke(app, ["photo-ingest", "-s", str(first), "-c", "Event"]).exit_code == 0
    result = runner.invoke(app, ["photo-ingest", "-s", str(second), "-c", "Event"])

    assert result.exit_code == 0, result.output
    collection = _collection(archive, "Event")
    assert (collection / "DSC00001_b.ARW").read_bytes() == b"recycled-name-other-frame"
    assert (collection / "DSC00001_b.ARW.pp3").read_bytes() == b"edits-for-the-second"
    assert (collection / "DSC00001_b.xmp").read_bytes() == b"metadata-for-the-second"
    entries = {entry["name"]: entry for entry in _manifest(collection)["files"]}
    assert entries["DSC00001_b.ARW.pp3"]["sidecar_for"] == "DSC00001_b.ARW"
    assert entries["DSC00001_b.xmp"]["sidecar_for"] == "DSC00001_b.ARW"


def test_a_deduplicated_photo_sends_its_sidecar_to_the_photo_it_matches(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "DSC00001.ARW", b"one-and-only")
    _write(second / "DSC09999.ARW", b"one-and-only")
    _write(second / "DSC09999.ARW.pp3", b"edits-made-later")

    assert runner.invoke(app, ["photo-ingest", "-s", str(first), "-c", "Monday"]).exit_code == 0
    result = runner.invoke(app, ["photo-ingest", "-s", str(second), "-c", "Tuesday"])

    assert result.exit_code == 0, result.output
    monday = _collection(archive, "Monday")
    assert (monday / "DSC00001.ARW.pp3").read_bytes() == b"edits-made-later"
    entries = {entry["name"]: entry for entry in _manifest(monday)["files"]}
    assert entries["DSC00001.ARW.pp3"]["sidecar_for"] == "DSC00001.ARW"
    assert entries["DSC00001.ARW.pp3"]["original_name"] == "DSC09999.ARW.pp3"
    assert list(_collection(archive, "Tuesday").iterdir()) == [
        _collection(archive, "Tuesday") / ".vflow-manifest.json"
    ]


def test_repeating_an_ingest_copies_nothing_twice(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "DSC00001.ARW", b"first-frame")
    _write(source / "DSC00001.ARW.pp3", b"edits")
    args = ["photo-ingest", "-s", str(source), "-c", "Event"]

    assert runner.invoke(app, args).exit_code == 0
    repeat = runner.invoke(app, args)

    assert repeat.exit_code == 0, repeat.output
    assert "0 copied, 2 already verified" in repeat.output
    collection = _collection(archive, "Event")
    assert sorted(path.name for path in collection.iterdir()) == [
        ".vflow-manifest.json",
        "DSC00001.ARW",
        "DSC00001.ARW.pp3",
    ]
    assert len(_manifest(collection)["files"]) == 2


def test_an_editing_sidecar_without_its_photo_stays_off_the_archive(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "DSC00001.ARW", b"first-frame")
    _write(source / "DSC00777.xmp", b"orphan-metadata")

    result = runner.invoke(app, ["photo-ingest", "-s", str(source), "-c", "Event"])

    assert result.exit_code == 0, result.output
    collection = _collection(archive, "Event")
    assert not (collection / "DSC00777.xmp").exists()
    excluded = {item["source_relative_path"]: item for item in _manifest(collection)["excluded"]}
    assert excluded["DSC00777.xmp"]["reason"] == "editing sidecar without its photo"


def test_photo_destination_is_verified_by_rehashing_the_archive_copy(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "DSC00001.ARW", b"first-frame")
    original_copy = shoot_manifest.copy_hashing

    def copy_then_corrupt(source_file, temporary):
        digest = original_copy(source_file, temporary)
        temporary.write_bytes(b"corrupted-on-arrival")
        return digest

    monkeypatch.setattr(shoot_manifest, "copy_hashing", copy_then_corrupt)
    result = runner.invoke(app, ["photo-ingest", "-s", str(source), "-c", "Event"])

    assert result.exit_code == 1
    assert "Checksum verification failed" in result.output
    assert not (_collection(archive, "Event") / "DSC00001.ARW").exists()


def test_photo_ingest_leaves_hand_placed_collection_files_alone(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    collection = _collection(archive, "20220612-20220619")
    _write(collection / "DSC00001.ARW", b"hand-placed")
    source = tmp_path / "CARD"
    _write(source / "DSC00001.ARW", b"from-the-card")

    result = runner.invoke(app, ["photo-ingest", "-s", str(source), "-c", "20220612-20220619"])

    assert result.exit_code == 0, result.output
    assert (collection / "DSC00001.ARW").read_bytes() == b"hand-placed"
    assert (collection / "DSC00001_b.ARW").read_bytes() == b"from-the-card"
    assert _manifest(collection)["collection"] == "20220612-20220619"
