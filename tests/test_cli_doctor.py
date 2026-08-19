from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import doctor_service
from vflow.main import app
from vflow.resolve_adapter import ResolveUnavailableError


runner = CliRunner()


def _offline(monkeypatch) -> None:
    """Answer the optional PyPI check the way a machine with no network does."""
    monkeypatch.setattr(doctor_service, "published_version", lambda: None)


def _without_resolve(monkeypatch) -> None:
    def unavailable():
        raise ResolveUnavailableError("Resolve access failed: unavailable in test.")

    monkeypatch.setattr(doctor_service, "get_resolve_adapter", unavailable)


def _configure(tmp_path: Path, monkeypatch, **overrides) -> dict:
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    working = tmp_path / "working"
    for path in (archive, exports, working):
        path.mkdir()
    settings = {
        "version": 2,
        "locations": {
            "archive": str(archive),
            "exports": str(exports),
            "working": {"laptop": str(working)},
        },
    }
    settings.update(overrides)
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.safe_dump(settings))
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    _offline(monkeypatch)
    _without_resolve(monkeypatch)
    return {"archive": archive, "config": config_path, "settings": settings}


def test_a_healthy_environment_reports_ready(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert f"[ok] Config file: {locations['config']}" in result.output
    assert f"[ok] Archive: {locations['archive']} [available]" in result.output
    assert "[ok] Archive layout: footage_raw Video/RAW, photo_raw Photo/RAW" in result.output
    assert "will be created by the first ingest" in result.output
    assert "[info] Resolve API: unavailable." in result.output
    assert "Ready: ingest and index can run now." in result.output
    assert "[fail]" not in result.output


def test_an_absent_config_names_the_command_that_creates_one(tmp_path, monkeypatch):
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", tmp_path / "missing.yml")
    _offline(monkeypatch)
    _without_resolve(monkeypatch)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "[fail] Configuration file not found at:" in result.output
    assert "Create it with 'v-flow make-config'." in result.output
    assert "Not ready: fix each [fail] line above" in result.output


def test_an_unparseable_config_is_reported_as_one_failure(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yml"
    config_path.write_text("locations: [unclosed\n")
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)
    _offline(monkeypatch)
    _without_resolve(monkeypatch)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "[fail] Error parsing configuration file:" in result.output


def test_a_missing_storage_role_is_a_failure(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    settings = locations["settings"]
    del settings["locations"]["exports"]
    locations["config"].write_text(yaml.safe_dump(settings))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "[fail] Configuration is missing storage role(s): exports" in result.output


def test_an_unplugged_archive_drive_reads_as_unavailable(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    settings = locations["settings"]
    settings["locations"]["archive"] = str(tmp_path / "unplugged")
    locations["config"].write_text(yaml.safe_dump(settings))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "[unavailable]. Connect that drive" in result.output
    assert not (tmp_path / "unplugged").exists()


def test_an_unavailable_exports_drive_stays_informational(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    settings = locations["settings"]
    settings["locations"]["exports"] = str(tmp_path / "unplugged_exports")
    locations["config"].write_text(yaml.safe_dump(settings))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "[info] Exports:" in result.output
    assert "[unavailable]" in result.output


def test_an_unsafe_layout_key_is_a_failure(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    settings = locations["settings"]
    settings["layout"] = {"footage_raw": "../outside"}
    locations["config"].write_text(yaml.safe_dump(settings))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "[fail] Archive layout: layout.footage_raw must stay inside the Archive" in result.output
    assert "Run 'v-flow set layout.footage_raw <subpath>'." in result.output


def test_existing_archive_roots_are_reported(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    (locations["archive"] / "Video" / "RAW").mkdir(parents=True)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert f"[ok] Archive root footage_raw: {locations['archive']}/Video/RAW exists" in result.output


def test_a_reachable_resolve_is_reported(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor_service, "get_resolve_adapter", lambda: object())

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "[info] Resolve API: reachable" in result.output


def test_a_newer_published_version_is_informational(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor_service, "installed_version", lambda: "0.2.0")
    monkeypatch.setattr(doctor_service, "published_version", lambda: "0.3.0")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "[info] Version: 0.2.0 installed, 0.3.0 on PyPI." in result.output


def test_an_unanswered_version_check_never_fails_the_command(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "The PyPI check got no answer" in result.output


def test_doctor_writes_nothing(tmp_path, monkeypatch):
    locations = _configure(tmp_path, monkeypatch)
    before = sorted(path.name for path in tmp_path.rglob("*"))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in tmp_path.rglob("*")) == before
    assert locations["config"].read_text() == yaml.safe_dump(locations["settings"])
