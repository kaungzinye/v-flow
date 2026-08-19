import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow.main import app


runner = CliRunner()

CUSTOM_LAYOUT = {"footage_raw": "Media/Footage", "photo_raw": "Media/Stills"}


def _configure(tmp_path: Path, monkeypatch, layout: dict | None = None) -> Path:
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    laptop = tmp_path / "laptop"
    for path in (archive, exports, laptop):
        path.mkdir()
    settings = {
        "version": 2,
        "locations": {
            "archive": str(archive),
            "exports": str(exports),
            "working": {"laptop": str(laptop)},
        },
    }
    if layout is not None:
        settings["layout"] = layout
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.safe_dump(settings))
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    return archive


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _manifest(directory: Path) -> dict:
    return json.loads((directory / ".vflow-manifest.json").read_text())


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def test_a_configured_layout_routes_both_kinds_to_their_roots(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    source = tmp_path / "CARD"
    _write(source / "CLIP" / "C0001.MP4", b"clip-one")
    _write(source / "DCIM" / "DSC00001.ARW", b"first-frame")
    _write(source / "DCIM" / "DSC00001.ARW.pp3", b"edits")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Stockholm"])

    assert result.exit_code == 0, result.output
    shoot = archive / "Media" / "Footage" / "Stockholm"
    collection = archive / "Media" / "Stills" / "Stockholm"
    assert _names(shoot) == [".vflow-manifest.json", "C0001.MP4"]
    assert _names(collection) == [
        ".vflow-manifest.json",
        "DSC00001.ARW",
        "DSC00001.ARW.pp3",
    ]
    assert not (archive / "Video").exists()
    assert not (archive / "Photo").exists()


def test_dedup_under_a_configured_layout_points_at_the_configured_root(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "C0001.MP4", b"same-clip")
    _write(first / "DSC00001.ARW", b"same-frame")
    _write(second / "C0009.MP4", b"same-clip")
    _write(second / "DSC00009.ARW", b"same-frame")

    assert runner.invoke(app, ["ingest", "-s", str(first), "-n", "Monday"]).exit_code == 0
    result = runner.invoke(app, ["ingest", "-s", str(second), "-n", "Tuesday"])

    assert result.exit_code == 0, result.output
    assert "1 deduplicated" in result.output
    clip = _manifest(archive / "Media" / "Footage" / "Tuesday")["deduplicated"][0]
    frame = _manifest(archive / "Media" / "Stills" / "Tuesday")["deduplicated"][0]
    assert clip["existing_location"] == "Media/Footage/Monday/C0001.MP4"
    assert frame["existing_location"] == "Media/Stills/Monday/DSC00001.ARW"


def test_indexing_walks_the_configured_roots(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    _write(archive / "Media" / "Footage" / "Handmade" / "C0001.MP4", b"hand-placed")
    _write(archive / "Media" / "Stills" / "Trip" / "DSC00001.ARW", b"hand-placed-frame")

    result = runner.invoke(app, ["index", "--all"])

    assert result.exit_code == 0, result.output
    assert "Media/Footage/Handmade" in result.output
    assert "Media/Stills/Trip" in result.output
    assert len(_manifest(archive / "Media" / "Footage" / "Handmade")["files"]) == 1
    assert len(_manifest(archive / "Media" / "Stills" / "Trip")["files"]) == 1


def test_indexing_names_a_folder_under_its_configured_root(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    _write(archive / "Media" / "Stills" / "Trip" / "DSC00001.ARW", b"hand-placed-frame")

    result = runner.invoke(app, ["index", "-f", "Media/Stills/Trip"])

    assert result.exit_code == 0, result.output
    assert len(_manifest(archive / "Media" / "Stills" / "Trip")["files"]) == 1


def test_indexing_refuses_a_folder_outside_the_configured_roots(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    _write(archive / "Video" / "RAW" / "Handmade" / "C0001.MP4", b"hand-placed")

    result = runner.invoke(app, ["index", "-f", "Video/RAW/Handmade"])

    assert result.exit_code == 1
    assert "Media/Footage or Media/Stills" in result.output


def test_a_layout_key_leaving_the_archive_stops_the_command(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"footage_raw": "../elsewhere"})
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 1
    assert "layout.footage_raw must stay inside the Archive: ../elsewhere" in result.output


def test_an_absolute_layout_key_stops_the_command(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"photo_raw": "/Volumes/Elsewhere"})

    result = runner.invoke(app, ["index", "--all"])

    assert result.exit_code == 1
    assert "layout.photo_raw must stay inside the Archive" in result.output


def test_setting_a_layout_key_records_it(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["set", "layout.footage_raw", "Media/Footage"])

    assert result.exit_code == 0, result.output
    assert "Set layout.footage_raw = Media/Footage" in result.output
    saved = yaml.safe_load(vflow_config.CONFIG_PATH.read_text())
    assert saved["layout"] == {"footage_raw": "Media/Footage"}


def test_setting_an_unsafe_layout_key_saves_nothing(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["set", "layout.photo_raw", "../outside"])

    assert result.exit_code == 1
    assert "layout.photo_raw must stay inside the Archive" in result.output
    assert "layout" not in yaml.safe_load(vflow_config.CONFIG_PATH.read_text())


def test_locations_shows_the_layout_in_force(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"footage_raw": "Media/Footage"})

    result = runner.invoke(app, ["locations"])

    assert result.exit_code == 0, result.output
    assert "Archive layout:" in result.output
    assert "footage_raw: Media/Footage" in result.output
    assert "photo_raw: Photo/RAW" in result.output


def test_a_config_without_a_layout_section_keeps_the_defaults(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    assert (archive / "Video" / "RAW" / "Shoot" / "C0001.MP4").is_file()


def test_one_configured_key_leaves_the_other_at_its_default(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, {"photo_raw": "Media/Stills"})
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")
    _write(source / "DSC00001.ARW", b"first-frame")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    assert (archive / "Video" / "RAW" / "Shoot" / "C0001.MP4").is_file()
    assert (archive / "Media" / "Stills" / "Shoot" / "DSC00001.ARW").is_file()


def test_checkout_reads_the_shoot_from_the_configured_root(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    saved = yaml.safe_load(vflow_config.CONFIG_PATH.read_text())
    saved["settings"] = {"laptop_free_space_reserve_gb": 0}
    vflow_config.CONFIG_PATH.write_text(yaml.safe_dump(saved))
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")
    assert runner.invoke(app, ["ingest", "-s", str(source), "-n", "Stockholm"]).exit_code == 0

    result = runner.invoke(
        app, ["checkout", "-n", "Stockholm", "-l", "laptop"]
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "laptop" / "Stockholm" / "C0001.MP4").read_bytes() == b"clip-one"


def test_list_backups_defaults_under_the_configured_footage_root(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch, CUSTOM_LAYOUT)
    _write(archive / "Media" / "Footage" / "Desktop_Ingest" / "Trip" / "C0001.MP4", b"clip")

    result = runner.invoke(app, ["list-backups"])

    assert result.exit_code == 0, result.output
    assert "Trip" in result.output
