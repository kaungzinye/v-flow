from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import index_service
from vflow import progress as vflow_progress
from vflow.main import app
from vflow.progress import Progress


runner = CliRunner()


def _every_line(monkeypatch) -> None:
    """Report every file, so a fast test sees what a slow transfer reports over hours."""
    monkeypatch.setattr(vflow_progress, "INTERVAL_SECONDS", 0)


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
    return {"archive": archive, "working": working}


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _card(tmp_path: Path, count: int = 3) -> Path:
    source = tmp_path / "card"
    for number in range(1, count + 1):
        _write(source / "CLIP" / f"C000{number}.MP4", f"clip-{number}".encode() * 4)
    return source


class _Clock:
    """A monotonic clock a test drives, so throttling is tested without waiting."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_progress_throttles_to_one_line_every_few_seconds():
    clock = _Clock()
    lines: list[str] = []
    reporter = Progress("Copying", 3, 30, clock=clock, emit=lines.append)

    reporter.start("a.mov", 10)
    reporter.settled(10)
    reporter.start("b.mov", 10)
    reporter.settled(10)
    clock.now = vflow_progress.INTERVAL_SECONDS
    reporter.start("c.mov", 10)
    reporter.settled(10)

    assert lines == [
        "Copying 1/3 files, 0.0 B/30.0 B: a.mov",
        "Copying 3/3 files, 20.0 B/30.0 B: c.mov",
    ]


def test_progress_states_what_the_manifest_already_covers():
    lines: list[str] = []
    reporter = Progress("Copying", 88, 880, clock=_Clock(), emit=lines.append)

    reporter.resuming(212, 300)

    assert lines == ["212 of 300 files verified; resuming."]


def test_progress_says_nothing_about_resuming_a_first_run():
    lines: list[str] = []
    reporter = Progress("Copying", 300, 3000, clock=_Clock(), emit=lines.append)

    reporter.resuming(0, 300)

    assert lines == []


def test_only_a_large_file_reports_from_inside_itself():
    reporter = Progress("Copying", 1, 1, clock=_Clock(), emit=lambda _: None)

    assert reporter.within_file(1024) is None
    assert reporter.within_file(vflow_progress.LARGE_FILE_BYTES) is not None


def test_ingest_reports_each_file_as_plain_text(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _every_line(monkeypatch)

    result = runner.invoke(
        app, ["ingest", "-s", str(_card(tmp_path)), "-n", "Shoot", "--import-batch", "card"]
    )

    assert result.exit_code == 0, result.output
    assert "Archiving 1/3 files, 0.0 B/72.0 B: CLIP/C0001.MP4" in result.output
    assert "Archiving 3/3 files, 48.0 B/72.0 B: CLIP/C0003.MP4" in result.output
    assert "\r" not in result.output
    assert "\x1b" not in result.output


def test_a_resumed_ingest_states_its_starting_point_and_copies_the_remainder(
    tmp_path, monkeypatch
):
    locations = _configure(tmp_path, monkeypatch)
    _every_line(monkeypatch)
    source = _card(tmp_path, count=2)
    from vflow import card_ingest

    original_place = card_ingest.place_verified
    attempts = 0

    def fail_second_copy(source_file, destination, expected=None, on_bytes=None):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_place(source_file, destination, expected, on_bytes)

    monkeypatch.setattr(card_ingest, "place_verified", fail_second_copy)
    args = ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", "card"]
    assert runner.invoke(app, args).exit_code == 1

    monkeypatch.setattr(card_ingest, "place_verified", original_place)
    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert "1 of 2 files verified; resuming." in result.output
    assert "1 copied, 1 already verified" in result.output
    shoot = locations["archive"] / "Video" / "RAW" / "Shoot"
    assert sorted(path.name for path in shoot.glob("*.MP4")) == ["C0001.MP4", "C0002.MP4"]


def test_checkout_reports_progress_and_what_it_reuses(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _every_line(monkeypatch)
    runner.invoke(
        app,
        ["ingest", "-s", str(_card(tmp_path, count=2)), "-n", "Shoot", "--import-batch", "card"],
    )
    args = ["checkout", "--shoot", "Shoot", "--working-location", "work_ssd"]
    first = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert "Copying 1/2 files, 0.0 B/48.0 B: C0001.MP4" in first.output

    second = runner.invoke(app, args)

    assert second.exit_code == 0, second.output
    assert "2 of 2 files verified; resuming." in second.output


def test_restore_reports_progress_and_what_it_skips(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _every_line(monkeypatch)
    archived = locations["archive"] / "Video" / "RAW" / "Shoot"
    _write(archived / "a.mov", b"first-file")
    _write(archived / "b.mov", b"second-file")
    destination = tmp_path / "restored"
    args = ["restore", "--source", str(archived), "--destination", str(destination)]

    first = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert "Restoring 1/2 files, 0.0 B/21.0 B: a.mov" in first.output

    second = runner.invoke(app, args)

    assert second.exit_code == 0, second.output
    assert "2 of 2 files verified; resuming." in second.output


def test_index_reports_hashing_and_resumes_from_a_partial_manifest(
    tmp_path, monkeypatch
):
    locations = _configure(tmp_path, monkeypatch)
    _every_line(monkeypatch)
    folder = locations["archive"] / "Video" / "RAW" / "2019_Handmade"
    for name in ("C0001.MP4", "C0002.MP4", "C0003.MP4"):
        _write(folder / name, f"legacy-{name}".encode())
    original_entry = index_service.indexed_entry
    attempts = 0

    def fail_on_the_second_file(path, on_bytes=None):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_entry(path, on_bytes)

    monkeypatch.setattr(index_service, "indexed_entry", fail_on_the_second_file)
    interrupted = runner.invoke(app, ["index", "--all"])

    assert interrupted.exit_code == 1
    assert "Hashing 1/3 files, 0.0 B/48.0 B: C0001.MP4" in interrupted.output

    monkeypatch.setattr(index_service, "indexed_entry", original_entry)
    result = runner.invoke(app, ["index", "--all"])

    assert result.exit_code == 0, result.output
    assert "1 of 3 files hashed; resuming." in result.output
