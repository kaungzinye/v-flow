import datetime
import json
import os
import time
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import prompts as vflow_prompts
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


def _stamp(path: Path, day: int) -> None:
    """Give one file a capture date in August 2026."""
    when = time.mktime(datetime.datetime(2026, 8, day, 12, 0).timetuple())
    os.utime(path, (when, when))


def _clip(source: Path, name: str, day: int) -> Path:
    path = source / "PRIVATE" / "M4ROOT" / "CLIP" / f"{name}.MP4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"footage-{name}".encode() * 8)
    _stamp(path, day)
    return path


def _frame(source: Path, name: str, day: int) -> Path:
    path = source / "DCIM" / "100MSDCF" / f"{name}.ARW"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"frame-{name}".encode() * 8)
    _stamp(path, day)
    return path


def _card(tmp_path: Path, name: str, days: list[int]) -> Path:
    source = tmp_path / name
    for day in days:
        _clip(source, f"{name}_{day}", day)
    return source


def _shoot(archive: Path, name: str) -> Path:
    return archive / "Video" / "RAW" / name


def _collection(archive: Path, name: str) -> Path:
    return archive / "Photo" / "RAW" / name


def _manifest(folder: Path) -> dict:
    return json.loads((folder / ".vflow-manifest.json").read_text())


def _shoot_names(archive: Path) -> list[str]:
    return sorted(path.name for path in (archive / "Video" / "RAW").iterdir())


def _at_a_terminal(monkeypatch) -> None:
    """Answer the run's questions the way a person at the keyboard would."""
    monkeypatch.setattr(vflow_prompts, "stdin_is_tty", lambda: True)


def test_ingest_records_the_media_date_range_of_both_kinds(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _clip(source, "C0001", 2)
    _clip(source, "C0002", 4)
    _frame(source, "DSC00811", 3)

    result = runner.invoke(
        app, ["ingest", "-s", str(source), "-n", "2026-08-02_Stockholm"]
    )

    assert result.exit_code == 0, result.output
    shoot = _manifest(_shoot(archive, "2026-08-02_Stockholm"))
    assert shoot["media_dates"] == {"start": "2026-08-02", "end": "2026-08-04"}
    collection = _manifest(_collection(archive, "2026-08-02_Stockholm"))
    assert collection["media_dates"] == {"start": "2026-08-03", "end": "2026-08-03"}


def test_one_overlapping_shoot_is_offered_and_merged_on_confirmation(
    tmp_path, monkeypatch
):
    archive = _configure(tmp_path, monkeypatch)
    _at_a_terminal(monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        ["ingest", "-s", str(_card(tmp_path, "B", [2, 3])), "--auto"],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "2026-08-02_Ingest" in result.output
    assert "overlaps these files" in result.output
    assert _shoot_names(archive) == ["2026-08-02_Ingest"]
    shoot = _shoot(archive, "2026-08-02_Ingest")
    assert sorted(path.name for path in shoot.glob("*.MP4")) == [
        "A_2.MP4",
        "B_2.MP4",
        "B_3.MP4",
    ]


def test_declining_the_suggestion_creates_the_derived_shoot(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    _at_a_terminal(monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        ["ingest", "-s", str(_card(tmp_path, "B", [2, 3])), "--auto"],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert _shoot_names(archive) == [
        "2026-08-02_Ingest",
        "2026-08-02_to_2026-08-03_Ingest",
    ]
    assert (_shoot(archive, "2026-08-02_Ingest") / "B_2.MP4").exists() is False


def test_merging_expands_the_recorded_range_without_renaming_the_folder(
    tmp_path, monkeypatch
):
    archive = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(_card(tmp_path, "B", [2, 9])),
            "--auto",
            "--merge-into",
            "2026-08-02_Ingest",
        ],
    )

    assert result.exit_code == 0, result.output
    shoot = _shoot(archive, "2026-08-02_Ingest")
    assert _shoot_names(archive) == ["2026-08-02_Ingest"]
    assert _manifest(shoot)["media_dates"] == {
        "start": "2026-08-02",
        "end": "2026-08-09",
    }


def test_several_overlapping_shoots_are_listed_and_none_is_chosen(
    tmp_path, monkeypatch
):
    archive = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "A", [2])), "-n", "Part1"])
    runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "B", [3])), "-n", "Part2"])

    result = runner.invoke(
        app, ["ingest", "-s", str(_card(tmp_path, "C", [2, 3])), "--auto"]
    )

    assert result.exit_code == 0, result.output
    assert "Part1 (2026-08-02)" in result.output
    assert "Part2 (2026-08-03)" in result.output
    assert "?" not in result.output
    assert _shoot_names(archive) == [
        "2026-08-02_to_2026-08-03_Ingest",
        "Part1",
        "Part2",
    ]


def test_an_explicit_name_never_prompts(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "A", [2])), "--auto"])

    source = tmp_path / "CARD"
    _clip(source, "C0009", 2)
    _frame(source, "DSC00811", 2)
    result = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "2026-08-02_Stockholm"],
    )

    assert result.exit_code == 0, result.output
    assert "overlaps" not in result.output
    assert _shoot_names(archive) == ["2026-08-02_Ingest", "2026-08-02_Stockholm"]


def test_an_explicit_collection_name_never_prompts(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    first = tmp_path / "FIRST"
    _frame(first, "DSC00811", 2)
    runner.invoke(app, ["ingest", "-s", str(first), "-n", "2026-08-02_Stills"])

    second = tmp_path / "SECOND"
    _frame(second, "DSC00812", 2)
    result = runner.invoke(
        app, ["ingest", "-s", str(second), "--auto", "-c", "Stockholm Stills"]
    )

    assert result.exit_code == 0, result.output
    assert "Collection '2026-08-02_Stills'" not in result.output
    assert (_collection(archive, "Stockholm Stills") / "DSC00812.ARW").is_file()


def test_an_overlapping_collection_is_offered_on_its_own(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    _at_a_terminal(monkeypatch)
    first = tmp_path / "FIRST"
    _frame(first, "DSC00811", 2)
    runner.invoke(app, ["ingest", "-s", str(first), "-n", "2026-08-02_Stills"])

    second = tmp_path / "SECOND"
    _frame(second, "DSC00812", 2)
    result = runner.invoke(app, ["ingest", "-s", str(second), "--auto"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "Collection '2026-08-02_Stills'" in result.output
    assert (_collection(archive, "2026-08-02_Stills") / "DSC00812.ARW").is_file()


def test_an_unmanifested_folder_matches_by_the_dates_in_its_name(
    tmp_path, monkeypatch
):
    archive = _configure(tmp_path, monkeypatch)
    _at_a_terminal(monkeypatch)
    existing = _shoot(archive, "2026-08-01_to_2026-08-05_Stockholm")
    existing.mkdir(parents=True)
    (existing / "OLD.MP4").write_bytes(b"older-footage")

    result = runner.invoke(
        app, ["ingest", "-s", str(_card(tmp_path, "A", [3])), "--auto"], input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert "2026-08-01_to_2026-08-05_Stockholm" in result.output
    assert (existing / "A_3.MP4").is_file()
    assert _shoot_names(archive) == ["2026-08-01_to_2026-08-05_Stockholm"]


def test_an_event_named_folder_without_a_manifest_never_matches(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    existing = _shoot(archive, "Stockholm_Trip")
    existing.mkdir(parents=True)
    (existing / "OLD.MP4").write_bytes(b"older-footage")

    result = runner.invoke(app, ["ingest", "-s", str(_card(tmp_path, "A", [3])), "--auto"])

    assert result.exit_code == 0, result.output
    assert "overlaps" not in result.output
    assert _shoot_names(archive) == ["2026-08-03_Ingest", "Stockholm_Trip"]


def test_index_records_the_range_of_the_folders_it_indexes(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    existing = _shoot(archive, "Stockholm_Trip")
    existing.mkdir(parents=True)
    for day, name in ((4, "OLD_A.MP4"), (6, "OLD_B.MP4")):
        clip = existing / name
        clip.write_bytes(name.encode() * 8)
        _stamp(clip, day)

    result = runner.invoke(app, ["index", "--all"])

    assert result.exit_code == 0, result.output
    assert _manifest(existing)["media_dates"] == {
        "start": "2026-08-04",
        "end": "2026-08-06",
    }


def test_an_indexed_folder_matches_by_its_recorded_range(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    _at_a_terminal(monkeypatch)
    existing = _shoot(archive, "Stockholm_Trip")
    existing.mkdir(parents=True)
    clip = existing / "OLD.MP4"
    clip.write_bytes(b"older-footage")
    _stamp(clip, 6)
    runner.invoke(app, ["index", "--all"])

    result = runner.invoke(
        app, ["ingest", "-s", str(_card(tmp_path, "A", [6])), "--auto"], input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert "Stockholm_Trip" in result.output
    assert (existing / "A_6.MP4").is_file()
