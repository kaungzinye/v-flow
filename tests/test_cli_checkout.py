from __future__ import annotations

from collections import namedtuple
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import checkout_service
from vflow import config as vflow_config
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch, reserve_gb: float = 0) -> dict[str, Path]:
    locations = {
        "archive": tmp_path / "archive",
        "exports": tmp_path / "exports",
        "laptop": tmp_path / "laptop",
        "work_ssd": tmp_path / "work-ssd",
    }
    for path in locations.values():
        path.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "locations": {
                    "archive": str(locations["archive"]),
                    "exports": str(locations["exports"]),
                    "working": {
                        "laptop": str(locations["laptop"]),
                        "work_ssd": str(locations["work_ssd"]),
                    },
                },
                "settings": {"laptop_free_space_reserve_gb": reserve_gb},
            }
        )
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    return locations


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _ingest(tmp_path: Path) -> None:
    source_a = tmp_path / "card-a"
    source_b = tmp_path / "card-b"
    _write(source_a / "CLIP" / "A001.MP4", b"camera-original")
    _write(source_a / "CLIP" / "A001.XML", b"sidecar")
    _write(source_b / "CLIP" / "A001.MP4", b"second-card")
    for source, batch in ((source_a, "card-a"), (source_b, "card-b")):
        result = runner.invoke(
            app,
            ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", batch],
        )
        assert result.exit_code == 0, result.output


def test_ssd_checkout_dry_run_then_creates_verified_working_copy(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _ingest(tmp_path)
    args = ["checkout", "--shoot", "Shoot", "--working-location", "work_ssd"]

    preview = runner.invoke(app, [*args, "--dry-run"])

    assert preview.exit_code == 0, preview.output
    assert "Dry run: 3 files would be copied" in preview.output
    assert list(locations["work_ssd"].rglob("*")) == []

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert "Checkout complete: 3 copied, 0 already verified, 3 total" in result.output
    working = locations["work_ssd"] / "Shoot"
    assert (working / "card-a" / "contents" / "CLIP" / "A001.MP4").read_bytes() == b"camera-original"
    assert (working / "card-a" / "contents" / "CLIP" / "A001.XML").read_bytes() == b"sidecar"
    assert (working / "card-b" / "contents" / "CLIP" / "A001.MP4").read_bytes() == b"second-card"


def test_laptop_checkout_previews_capacity_and_reuses_verified_files(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch, reserve_gb=1)
    _ingest(tmp_path)
    DiskUsage = namedtuple("DiskUsage", "total used free")
    monkeypatch.setattr(
        checkout_service.shutil,
        "disk_usage",
        lambda path: DiskUsage(4 * 1024**3, 1024**3, 3 * 1024**3),
    )
    args = ["checkout", "--shoot", "Shoot", "--working-location", "laptop"]

    first = runner.invoke(app, args)
    second = runner.invoke(app, [*args, "--dry-run"])

    assert first.exit_code == 0, first.output
    assert "Laptop free space:" in first.output
    assert "Laptop free-space reserve: 1.0 GB" in first.output
    assert second.exit_code == 0, second.output
    assert "Dry run: 0 files would be copied and 3 verified files would be reused" in second.output


def test_laptop_checkout_refuses_to_violate_free_space_reserve(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch, reserve_gb=1)
    _ingest(tmp_path)
    DiskUsage = namedtuple("DiskUsage", "total used free")
    monkeypatch.setattr(
        checkout_service.shutil,
        "disk_usage",
        lambda path: DiskUsage(2 * 1024**3, 1024**3, 1024**3),
    )

    result = runner.invoke(
        app,
        ["checkout", "--shoot", "Shoot", "--working-location", "laptop", "--dry-run"],
    )

    assert result.exit_code == 1
    assert "Additional space required:" in result.output
    assert "Free-space reserve: 1.0 GB" in result.output
    assert "Laptop capacity gate failed" in result.output
    assert "would violate the configured reserve" in result.output
    assert list(locations["laptop"].rglob("*")) == []


def test_interrupted_checkout_retries_and_reuses_verified_files(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _ingest(tmp_path)
    original_copy = checkout_service._copy_verified
    attempts = 0

    def fail_second_copy(entry):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_copy(entry)

    monkeypatch.setattr(checkout_service, "_copy_verified", fail_second_copy)
    args = ["checkout", "--shoot", "Shoot", "--working-location", "work_ssd"]
    interrupted = runner.invoke(app, args)

    assert interrupted.exit_code == 1
    assert "retry the same Checkout to resume" in interrupted.output
    copied_files = [path for path in locations["work_ssd"].rglob("*") if path.is_file()]
    assert len(copied_files) == 1

    monkeypatch.setattr(checkout_service, "_copy_verified", original_copy)
    retry = runner.invoke(app, args)

    assert retry.exit_code == 0, retry.output
    assert "2 copied, 1 already verified, 3 total" in retry.output


def test_checkout_conflict_stops_without_overwriting_content(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _ingest(tmp_path)
    conflict = locations["work_ssd"] / "Shoot" / "card-b" / "contents" / "CLIP" / "A001.MP4"
    _write(conflict, b"different-content")

    result = runner.invoke(
        app,
        ["checkout", "--shoot", "Shoot", "--working-location", "work_ssd"],
    )

    assert result.exit_code == 1
    assert "Working Copy conflict" in result.output
    assert conflict.read_bytes() == b"different-content"
    assert not (locations["work_ssd"] / "Shoot" / "card-a").exists()


def test_direct_archive_access_reports_source_and_creates_no_working_copy(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _ingest(tmp_path)

    result = runner.invoke(
        app,
        ["checkout", "--shoot", "Shoot", "--direct-archive-access"],
    )

    assert result.exit_code == 0, result.output
    assert "Direct Archive Access" in result.output
    assert f"Archived Shoot: {locations['archive'] / 'Camera Originals' / 'Shoot'}" in result.output
    assert f"Archived source: {locations['archive'] / 'Camera Originals' / 'Shoot' / 'card-a' / 'contents'}" in result.output
    assert f"Archived source: {locations['archive'] / 'Camera Originals' / 'Shoot' / 'card-b' / 'contents'}" in result.output
    assert "Working Copy created: no" in result.output
    assert list(locations["laptop"].rglob("*")) == []
    assert list(locations["work_ssd"].rglob("*")) == []


def test_checkout_requires_one_explicit_mode_and_never_falls_back(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _ingest(tmp_path)

    missing = runner.invoke(app, ["checkout", "--shoot", "Shoot"])
    unavailable = runner.invoke(
        app,
        ["checkout", "--shoot", "Shoot", "--working-location", "travel_ssd"],
    )

    assert missing.exit_code == 1
    assert "Choose exactly one mode" in missing.output
    assert unavailable.exit_code == 1
    assert "Location 'travel_ssd' is not defined" in unavailable.output
    assert list(locations["laptop"].rglob("*")) == []
    assert list(locations["work_ssd"].rglob("*")) == []
