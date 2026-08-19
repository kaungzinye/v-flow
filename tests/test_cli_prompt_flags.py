import datetime
import os
import time
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    working = tmp_path / "working"
    for path in (archive, exports, working):
        path.mkdir()
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
    return {"archive": archive, "working": working, "config": config_path}


def _stamp(path: Path, day: int) -> None:
    when = time.mktime(datetime.datetime(2026, 8, day, 12, 0).timetuple())
    os.utime(path, (when, when))


def _clip(source: Path, name: str, day: int) -> None:
    path = source / "PRIVATE" / "M4ROOT" / "CLIP" / f"{name}.MP4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"footage-{name}".encode() * 8)
    _stamp(path, day)


def _frame(source: Path, name: str, day: int) -> None:
    path = source / "DCIM" / "100MSDCF" / f"{name}.ARW"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"frame-{name}".encode() * 8)
    _stamp(path, day)


def _footage_card(tmp_path: Path, name: str, days: list[int]) -> Path:
    source = tmp_path / name
    for day in days:
        _clip(source, f"{name}_{day}", day)
    return source


def _mixed_card(tmp_path: Path, name: str, days: list[int]) -> Path:
    source = tmp_path / name
    for day in days:
        _clip(source, f"{name}_{day}", day)
        _frame(source, f"DSC_{name}_{day}", day)
    return source


def _shoot_names(archive: Path) -> list[str]:
    return sorted(path.name for path in (archive / "Video" / "RAW").iterdir())


def _collection_names(archive: Path) -> list[str]:
    return sorted(path.name for path in (archive / "Photo" / "RAW").iterdir())


def test_an_overlap_without_an_answer_names_the_flags_and_copies_nothing(
    tmp_path, monkeypatch
):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_footage_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app, ["ingest", "-s", str(_footage_card(tmp_path, "B", [2, 3])), "--auto"]
    )

    assert result.exit_code == 1
    assert (
        "Shoot '2026-08-02_Ingest' (2026-08-02) overlaps these files "
        "(2026-08-02 to 2026-08-03). Pass --merge-into '2026-08-02_Ingest' "
        "or --no-merge." in result.output
    )
    assert _shoot_names(locations["archive"]) == ["2026-08-02_Ingest"]
    assert not (
        locations["archive"] / "Video" / "RAW" / "2026-08-02_Ingest" / "B_2.MP4"
    ).exists()


def test_no_merge_keeps_the_derived_name(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_footage_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        ["ingest", "-s", str(_footage_card(tmp_path, "B", [2, 3])), "--auto", "--no-merge"],
    )

    assert result.exit_code == 0, result.output
    assert _shoot_names(locations["archive"]) == [
        "2026-08-02_Ingest",
        "2026-08-02_to_2026-08-03_Ingest",
    ]


def test_merge_into_adds_the_card_to_the_named_shoot(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_footage_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(_footage_card(tmp_path, "B", [2, 3])),
            "--auto",
            "--merge-into",
            "2026-08-02_Ingest",
        ],
    )

    assert result.exit_code == 0, result.output
    assert _shoot_names(locations["archive"]) == ["2026-08-02_Ingest"]
    assert (
        locations["archive"] / "Video" / "RAW" / "2026-08-02_Ingest" / "B_3.MP4"
    ).is_file()


def test_merge_into_names_the_scope_when_both_kinds_suggest(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_mixed_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app, ["ingest", "-s", str(_mixed_card(tmp_path, "B", [2, 3])), "--auto"]
    )

    assert result.exit_code == 1
    assert "--merge-into 'shoot=2026-08-02_Ingest' or --no-merge" in result.output
    assert _shoot_names(locations["archive"]) == ["2026-08-02_Ingest"]


def test_one_bare_merge_into_is_ambiguous_across_two_kinds(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_mixed_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(_mixed_card(tmp_path, "B", [2, 3])),
            "--auto",
            "--merge-into",
            "2026-08-02_Ingest",
        ],
    )

    assert result.exit_code == 1
    assert "ambiguous" in result.output
    assert "--merge-into 'shoot=<name>'" in result.output
    assert _collection_names(locations["archive"]) == ["2026-08-02_Ingest"]


def test_scoped_merge_answers_each_kind_on_its_own(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_mixed_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(_mixed_card(tmp_path, "B", [2, 3])),
            "--auto",
            "--merge-into",
            "shoot=2026-08-02_Ingest",
            "--no-merge",
        ],
    )

    assert result.exit_code == 0, result.output
    assert _shoot_names(locations["archive"]) == ["2026-08-02_Ingest"]
    assert _collection_names(locations["archive"]) == [
        "2026-08-02_Ingest",
        "2026-08-02_to_2026-08-03_Ingest",
    ]


def test_merge_into_a_folder_that_does_not_overlap_stops_the_ingest(
    tmp_path, monkeypatch
):
    locations = _configure(tmp_path, monkeypatch)
    runner.invoke(app, ["ingest", "-s", str(_footage_card(tmp_path, "A", [2])), "--auto"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(_footage_card(tmp_path, "B", [2, 3])),
            "--auto",
            "--merge-into",
            "Stockholm_Trip",
        ],
    )

    assert result.exit_code == 1
    assert "No Shoot named 'Stockholm_Trip' overlaps these files" in result.output
    assert _shoot_names(locations["archive"]) == ["2026-08-02_Ingest"]


def test_merge_into_without_any_suggestion_stops_the_ingest(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)

    result = runner.invoke(
        app,
        [
            "ingest",
            "-s",
            str(_footage_card(tmp_path, "A", [2])),
            "--auto",
            "--merge-into",
            "2026-08-02_Ingest",
        ],
    )

    assert result.exit_code == 1
    assert "names no folder that overlaps these files" in result.output
    assert not (locations["archive"] / "Video" / "RAW").exists()


def _working_copy(tmp_path: Path) -> None:
    source = tmp_path / "card"
    (source / "CLIP").mkdir(parents=True)
    (source / "CLIP" / "A001.MP4").write_bytes(b"camera-original")
    ingest = runner.invoke(
        app, ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", "card"]
    )
    assert ingest.exit_code == 0, ingest.output
    checkout = runner.invoke(
        app, ["checkout", "--shoot", "Shoot", "--working-location", "work_ssd"]
    )
    assert checkout.exit_code == 0, checkout.output


def _cleanup_args(*extra: str) -> list[str]:
    return [
        "cleanup",
        "--shoot",
        "Shoot",
        "--working-location",
        "work_ssd",
        "--skip-resolve-validation",
        *extra,
    ]


def test_cleanup_without_confirmation_names_the_flag_and_deletes_nothing(
    tmp_path, monkeypatch
):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)

    result = runner.invoke(app, _cleanup_args())

    assert result.exit_code == 1
    assert "Cleanup deletes 1 verified file(s) from the Working Copy" in result.output
    assert "Pass --confirm." in result.output
    assert (locations["working"] / "Shoot" / "A001.MP4").is_file()


def test_cleanup_confirm_flag_answers_the_deletion_gate(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)

    result = runner.invoke(app, _cleanup_args("--confirm"))

    assert result.exit_code == 0, result.output
    assert "Working Copy files deleted: 1" in result.output
    assert not (locations["working"] / "Shoot").exists()


def test_make_config_without_overwrite_leaves_the_existing_file(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    before = locations["config"].read_text()

    result = runner.invoke(app, ["make-config"])

    assert result.exit_code == 1
    assert "Pass --overwrite." in result.output
    assert locations["config"].read_text() == before


def test_make_config_overwrite_flag_writes_the_sample(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["make-config", "--overwrite"])

    assert result.exit_code == 0, result.output
    saved = yaml.safe_load(locations["config"].read_text())
    assert saved["locations"]["archive"] == "/path/to/your/archive"
