from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow.main import app


runner = CliRunner()


def _write_role_config(
    path: Path,
    archive: Path,
    exports: Path,
    working: dict,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "locations": {
                    "archive": str(archive),
                    "exports": str(exports),
                    "working": {name: str(location) for name, location in working.items()},
                },
                "settings": {"laptop_free_space_reserve_gb": 80},
            },
            sort_keys=False,
        )
    )


def test_locations_reports_roles_and_named_working_locations(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    laptop = tmp_path / "laptop"
    travel = tmp_path / "travel"
    for location in (archive, exports, laptop, travel):
        location.mkdir()
    config_path = tmp_path / "config.yml"
    _write_role_config(
        config_path,
        archive,
        exports,
        {"laptop": laptop, "travel_ssd": travel},
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)

    result = runner.invoke(app, ["locations"])

    assert result.exit_code == 0
    assert f"Archive: {archive} [available]" in result.output
    assert f"Exports: {exports} [available]" in result.output
    assert f"laptop: {laptop} [available]" in result.output
    assert f"travel_ssd: {travel} [available]" in result.output
    assert "laptop_free_space_reserve_gb: 80" in result.output


def test_locations_reports_unavailable_roles(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yml"
    _write_role_config(
        config_path,
        tmp_path / "missing-archive",
        tmp_path / "missing-exports",
        {"work_ssd": tmp_path / "missing-work"},
    )
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)

    result = runner.invoke(app, ["locations"])

    assert result.exit_code == 0
    assert result.output.count("[unavailable]") == 3


def test_missing_roles_fail_with_clear_error(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yml"
    config_path.write_text("locations:\n  archive: /archive\n  working:\n    laptop: /work\n")
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)

    result = runner.invoke(app, ["locations"])

    assert result.exit_code == 1
    assert "missing storage role(s): exports" in result.output


def test_set_adds_a_named_working_location(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    exports = tmp_path / "exports"
    laptop = tmp_path / "laptop"
    config_path = tmp_path / "config.yml"
    _write_role_config(config_path, archive, exports, {"laptop": laptop})
    monkeypatch.setattr(vflow_config, "CONFIG_PATH", config_path)

    result = runner.invoke(
        app,
        ["set", "working.travel_ssd", str(tmp_path / "travel")],
    )

    assert result.exit_code == 0
    saved = yaml.safe_load(config_path.read_text())
    assert saved["locations"]["working"]["travel_ssd"] == str(tmp_path / "travel")


def test_get_location_rejects_an_unavailable_working_location(tmp_path):
    app_config = {
        "locations": {
            "archive": str(tmp_path / "archive"),
            "exports": str(tmp_path / "exports"),
            "working": {"travel_ssd": str(tmp_path / "missing")},
        }
    }

    try:
        vflow_config.get_location(app_config, "travel_ssd")
    except Exception as error:
        assert getattr(error, "exit_code", None) == 1
    else:
        raise AssertionError("unavailable working location was accepted")
