import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

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


def _shoot(archive: Path, name: str) -> Path:
    return archive / "Video" / "RAW" / name


def _collection(archive: Path, name: str) -> Path:
    return archive / "Photo" / "RAW" / name


def _manifest(directory: Path) -> dict:
    return json.loads((directory / ".vflow-manifest.json").read_text())


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def _a7iv_card(root: Path) -> None:
    """One Sony card carrying a day of footage and a day of frames."""
    _write(root / "PRIVATE" / "M4ROOT" / "CLIP" / "C6634.MP4", b"first-clip")
    _write(root / "PRIVATE" / "M4ROOT" / "CLIP" / "C6635.MP4", b"second-clip")
    _write(root / "DCIM" / "100MSDCF" / "DSC00811.ARW", b"first-frame")
    _write(root / "DCIM" / "100MSDCF" / "DSC00811.ARW.pp3", b"edits-for-811")
    _write(root / "DCIM" / "100MSDCF" / "DSC00812.ARW", b"second-frame")


def test_one_card_lands_footage_in_a_shoot_and_photos_in_a_collection(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _a7iv_card(source)

    result = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "2026-08-02_Stockholm", "--import-batch", "card-a"],
    )

    assert result.exit_code == 0, result.output
    shoot = _shoot(archive, "2026-08-02_Stockholm")
    collection = _collection(archive, "2026-08-02_Stockholm")
    assert _names(shoot) == [".vflow-manifest.json", "C6634.MP4", "C6635.MP4"]
    assert _names(collection) == [
        ".vflow-manifest.json",
        "DSC00811.ARW",
        "DSC00811.ARW.pp3",
        "DSC00812.ARW",
    ]
    assert _manifest(shoot)["shoot"] == "2026-08-02_Stockholm"
    assert _manifest(collection)["collection"] == "2026-08-02_Stockholm"
    photo_entries = {entry["name"] for entry in _manifest(collection)["files"]}
    assert photo_entries == {"DSC00811.ARW", "DSC00811.ARW.pp3", "DSC00812.ARW"}
    assert {entry["name"] for entry in _manifest(shoot)["files"]} == {
        "C6634.MP4",
        "C6635.MP4",
    }


def test_a_mixed_card_reports_each_kind_of_media_separately(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _a7iv_card(source)

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Stockholm"])

    assert result.exit_code == 0, result.output
    assert "Archiving footage into Shoot 'Stockholm'..." in result.output
    assert "Archiving photos into Collection 'Stockholm'..." in result.output
    assert f"Shoot folder: {_shoot(archive, 'Stockholm')}" in result.output
    assert f"Collection folder: {_collection(archive, 'Stockholm')}" in result.output
    assert "2 copied, 0 already verified, 0 deduplicated, 3 excluded, 2 in Shoot." in result.output
    assert "3 copied, 0 already verified, 0 deduplicated, 2 excluded, 3 in Collection." in result.output
    assert result.output.count("Retained copies: 1 (Archive only)") == 1


def test_a_collection_name_overrides_the_shoot_name_for_photos(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _a7iv_card(source)

    result = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "2026-08-02_Stockholm", "-c", "Stockholm Stills"],
    )

    assert result.exit_code == 0, result.output
    assert _names(_shoot(archive, "2026-08-02_Stockholm")) == [
        ".vflow-manifest.json",
        "C6634.MP4",
        "C6635.MP4",
    ]
    assert (_collection(archive, "Stockholm Stills") / "DSC00811.ARW").is_file()
    assert not _collection(archive, "2026-08-02_Stockholm").exists()


def test_auto_names_the_shoot_and_the_collection_alike(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _a7iv_card(source)

    result = runner.invoke(app, ["ingest", "-s", str(source), "--auto"])

    assert result.exit_code == 0, result.output
    shoots = list((archive / "Video" / "RAW").iterdir())
    collections = list((archive / "Photo" / "RAW").iterdir())
    assert len(shoots) == 1 and len(collections) == 1
    assert shoots[0].name == collections[0].name
    assert shoots[0].name.endswith("_Ingest")


def test_a_card_without_photos_creates_no_collection(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "CLIP" / "C0001.MP4", b"clip-one")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Footage Only"])

    assert result.exit_code == 0, result.output
    assert (_shoot(archive, "Footage Only") / "C0001.MP4").is_file()
    assert not (archive / "Photo" / "RAW").exists()
    assert "Collection" not in result.output


def test_a_card_without_footage_creates_no_shoot(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "DCIM" / "DSC00811.ARW", b"first-frame")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Photos Only"])

    assert result.exit_code == 0, result.output
    assert (_collection(archive, "Photos Only") / "DSC00811.ARW").is_file()
    assert not (archive / "Video" / "RAW").exists()
    assert "Shoot" not in result.output


def test_a_source_holding_neither_footage_nor_photos_stops_the_ingest(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "MEDIAPRO.XML", b"card-database")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Nothing"])

    assert result.exit_code == 1
    assert "No footage or photos found in the source directory." in result.output
    assert not (archive / "Video").exists()
    assert not (archive / "Photo").exists()


def test_a_files_filter_selects_across_both_kinds_and_keeps_sidecars(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _a7iv_card(source)

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(source),
            "-n",
            "Selects",
            "--files",
            "C6634",
            "--files",
            "DSC00811",
        ],
    )

    assert result.exit_code == 0, result.output
    assert _names(_shoot(archive, "Selects")) == [".vflow-manifest.json", "C6634.MP4"]
    assert _names(_collection(archive, "Selects")) == [
        ".vflow-manifest.json",
        "DSC00811.ARW",
        "DSC00811.ARW.pp3",
    ]
    entries = {entry["name"]: entry for entry in _manifest(_collection(archive, "Selects"))["files"]}
    assert entries["DSC00811.ARW.pp3"]["sidecar_for"] == "DSC00811.ARW"


def test_repeating_a_mixed_ingest_copies_nothing_twice(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _a7iv_card(source)
    args = ["ingest", "-s", str(source), "-n", "Stockholm"]

    assert runner.invoke(app, args).exit_code == 0
    repeat = runner.invoke(app, args)

    assert repeat.exit_code == 0, repeat.output
    assert "0 copied, 2 already verified, 0 deduplicated, 3 excluded, 2 in Shoot." in repeat.output
    assert "0 copied, 3 already verified, 0 deduplicated, 2 excluded, 3 in Collection." in repeat.output
    assert len(_manifest(_shoot(archive, "Stockholm"))["files"]) == 2
    assert len(_manifest(_collection(archive, "Stockholm"))["files"]) == 3


def test_each_kind_deduplicates_against_what_is_already_archived(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "C0001.MP4", b"same-clip")
    _write(first / "DSC00001.ARW", b"same-frame")
    _write(second / "C0009.MP4", b"same-clip")
    _write(second / "DSC00009.ARW", b"same-frame")
    _write(second / "C0010.MP4", b"fresh-clip")

    assert runner.invoke(app, ["ingest", "-s", str(first), "-n", "Monday"]).exit_code == 0
    result = runner.invoke(app, ["ingest", "-s", str(second), "-n", "Tuesday"])

    assert result.exit_code == 0, result.output
    assert "1 copied, 0 already verified, 1 deduplicated, 1 excluded, 1 in Shoot." in result.output
    assert "0 copied, 0 already verified, 1 deduplicated, 2 excluded, 0 in Collection." in result.output
    assert _names(_shoot(archive, "Tuesday")) == [".vflow-manifest.json", "C0010.MP4"]
    assert _names(_collection(archive, "Tuesday")) == [".vflow-manifest.json"]
    clip = _manifest(_shoot(archive, "Tuesday"))["deduplicated"][0]
    frame = _manifest(_collection(archive, "Tuesday"))["deduplicated"][0]
    assert clip["existing_location"] == "Video/RAW/Monday/C0001.MP4"
    assert frame["existing_location"] == "Photo/RAW/Monday/DSC00001.ARW"
