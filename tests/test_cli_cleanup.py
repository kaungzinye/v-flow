from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import cleanup_service
from vflow import config as vflow_config
from vflow import main as vflow_main
from vflow.main import app
from vflow.resolve_adapter import ResolveUnavailableError


runner = CliRunner()


class FakeResolveAdapter:
    def __init__(self, unresolved=None, confirmed=0, relinked=2):
        self.unresolved = unresolved or []
        self.confirmed = confirmed
        self.relinked = relinked
        self.calls = []

    def validate_project_media(self, project_name, path_map, allow_relink=True):
        self.calls.append((project_name, path_map, allow_relink))
        return {
            "checked": len(path_map),
            "confirmed": self.confirmed,
            "relinked": self.relinked if allow_relink else 0,
            "pending_relinks": [] if allow_relink else [str(path) for path in path_map.values()],
            "unresolved": self.unresolved,
        }


def _configure(tmp_path: Path, monkeypatch, unsafe_working=False) -> dict[str, Path]:
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    working = archive / "Camera Originals" if unsafe_working else tmp_path / "working"
    for path in (archive, exports, working):
        path.mkdir(parents=True, exist_ok=True)
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


def _working_copy(tmp_path: Path) -> None:
    source = tmp_path / "card"
    _write(source / "CLIP" / "A001.MP4", b"camera-original")
    _write(source / "CLIP" / "A001.XML", b"sidecar")
    ingest = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", "card"],
    )
    assert ingest.exit_code == 0, ingest.output
    checkout = runner.invoke(
        app,
        ["checkout", "--shoot", "Shoot", "--working-location", "work_ssd"],
    )
    assert checkout.exit_code == 0, checkout.output


def _args(*extra: str) -> list[str]:
    return [
        "cleanup",
        "--shoot",
        "Shoot",
        "--working-location",
        "work_ssd",
        "--project",
        "Project",
        *extra,
    ]


def test_cleanup_refuses_a_target_inside_archive_storage(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch, unsafe_working=True)
    source = tmp_path / "card"
    _write(source / "A001.MP4", b"camera-original")
    ingest = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", "card"],
    )
    assert ingest.exit_code == 0, ingest.output
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: FakeResolveAdapter())

    result = runner.invoke(app, _args("--dry-run"))

    assert result.exit_code == 1
    assert "Archive safety gate failed" in result.output
    assert (locations["archive"] / "Camera Originals" / "Shoot").exists()


def test_cleanup_stops_when_an_archive_checksum_fails(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)
    archived = locations["archive"] / "Camera Originals" / "Shoot" / "card" / "contents" / "CLIP" / "A001.MP4"
    archived.write_bytes(b"different-content")
    adapter = FakeResolveAdapter()
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, _args("--dry-run"))

    assert result.exit_code == 1
    assert "Archive checksum gate failed" in result.output
    assert adapter.calls == []
    assert (locations["working"] / "Shoot").exists()


def test_cleanup_stops_for_unresolved_offline_media(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)
    adapter = FakeResolveAdapter(unresolved=["offline/A001.MP4"])
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, _args(), input="y\n")

    assert result.exit_code == 1
    assert "Resolve validation gate failed" in result.output
    assert "remain offline" in result.output
    assert (locations["working"] / "Shoot").exists()


def test_cleanup_relinks_then_deletes_after_confirmation(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)
    adapter = FakeResolveAdapter(relinked=2)
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, _args(), input="y\n")

    assert result.exit_code == 0, result.output
    assert "Resolve media relinked: 2" in result.output
    assert "Working Copy files deleted: 2" in result.output
    assert not (locations["working"] / "Shoot").exists()
    assert adapter.calls[0][0] == "Project"
    assert adapter.calls[0][2] is True


def test_cleanup_stops_when_resolve_is_unavailable(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)

    def unavailable():
        raise ResolveUnavailableError("Resolve access failed: unavailable in test")

    monkeypatch.setattr(vflow_main, "get_resolve_adapter", unavailable)
    result = runner.invoke(app, _args(), input="y\n")

    assert result.exit_code == 1
    assert "Resolve access failed" in result.output
    assert (locations["working"] / "Shoot").exists()


def test_skip_resolve_bypasses_only_that_gate(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)

    def unexpected_adapter():
        raise AssertionError("Resolve adapter was requested")

    monkeypatch.setattr(vflow_main, "get_resolve_adapter", unexpected_adapter)
    result = runner.invoke(
        app,
        _args("--skip-resolve-validation"),
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "Resolve validation: explicitly skipped" in result.output
    assert "Archive checksum verified: 2 files" in result.output
    assert "Working Copy files deleted: 2" in result.output
    assert not (locations["working"] / "Shoot").exists()


def test_cleanup_declined_confirmation_retains_every_file(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: FakeResolveAdapter())

    result = runner.invoke(app, _args(), input="n\n")

    assert result.exit_code == 1
    assert "Confirmation gate declined" in result.output
    assert (locations["working"] / "Shoot").exists()
    assert len(list((locations["working"] / "Shoot").rglob("*.*"))) == 2


def test_cleanup_dry_run_plans_relink_without_mutating(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)
    adapter = FakeResolveAdapter()
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, _args("--dry-run"))

    assert result.exit_code == 0, result.output
    assert "Resolve media that would be relinked: 2" in result.output
    assert "Dry run: 2 files would be deleted" in result.output
    assert adapter.calls[0][2] is False
    assert (locations["working"] / "Shoot").exists()


def test_cleanup_reports_partial_deletion_failure(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    _working_copy(tmp_path)
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: FakeResolveAdapter())
    original_unlink = cleanup_service.Path.unlink
    calls = 0

    def fail_second(path, *args, **kwargs):
        nonlocal calls
        if ".vflow-part" not in path.name:
            calls += 1
            if calls == 2:
                raise OSError("simulated deletion failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(cleanup_service.Path, "unlink", fail_second)
    result = runner.invoke(app, _args(), input="y\n")

    assert result.exit_code == 1
    assert "Working Copy files deleted: 1" in result.output
    assert "Deletion failures: 1" in result.output
    remaining = [path for path in (locations["working"] / "Shoot").rglob("*") if path.is_file()]
    assert len(remaining) == 1
