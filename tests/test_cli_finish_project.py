from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import config as vflow_config
from vflow import main as vflow_main
from vflow.main import app
from vflow.resolve_adapter import ResolveUnavailableError


runner = CliRunner()


class FakeResolveAdapter:
    def __init__(self, content: bytes = b"portable-project-backup", succeeds: bool = True):
        self.content = content
        self.succeeds = succeeds
        self.calls = []

    def export_project_backup(
        self,
        project_name: str,
        destination: Path,
        include_stills_and_luts: bool = True,
    ) -> bool:
        self.calls.append((project_name, destination, include_stills_and_luts))
        if not self.succeeds:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.content)
        return True


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
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
    return archive, exports


def _retained_output(archive: Path, exports: Path, project: str = "Project") -> Path:
    local = exports / "Final Videos" / project / "final.mov"
    archived = archive / "Exports" / "Final Videos" / project / "final.mov"
    local.parent.mkdir(parents=True)
    archived.parent.mkdir(parents=True)
    local.write_bytes(b"verified-final-video")
    archived.write_bytes(b"verified-final-video")
    return local


def test_finish_exports_and_verifies_portable_project_backup(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    local_output = _retained_output(archive, exports)
    adapter = FakeResolveAdapter()
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, ["finish", "--project", "Project"])

    assert result.exit_code == 0, result.output
    archived_backup = archive / "Project Backups" / "Project" / "Project.drp"
    assert archived_backup.read_bytes() == b"portable-project-backup"
    assert local_output.read_bytes() == b"verified-final-video"
    assert adapter.calls[0][0] == "Project"
    assert adapter.calls[0][2] is True
    assert "Verified retained outputs: 1" in result.output
    assert "Project Backups verified: 1" in result.output
    assert "Retained local files: 1" in result.output


def test_finish_dry_run_verifies_outputs_without_calling_resolve(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    _retained_output(archive, exports)

    def unexpected_adapter():
        raise AssertionError("dry run called Resolve")

    monkeypatch.setattr(vflow_main, "get_resolve_adapter", unexpected_adapter)
    result = runner.invoke(app, ["finish", "--project", "Project", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Resolve was not called" in result.output
    assert "with stills and LUTs: 1" in result.output
    assert not (archive / "Project Backups").exists()


def test_finish_fails_safely_when_resolve_is_unavailable(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    local_output = _retained_output(archive, exports)

    def unavailable():
        raise ResolveUnavailableError("Resolve access failed: unavailable in test")

    monkeypatch.setattr(vflow_main, "get_resolve_adapter", unavailable)
    result = runner.invoke(app, ["finish", "--project", "Project"])

    assert result.exit_code == 1
    assert "Resolve access failed" in result.output
    assert local_output.read_bytes() == b"verified-final-video"
    assert not (archive / "Project Backups").exists()


def test_finish_fails_safely_when_project_export_fails(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    local_output = _retained_output(archive, exports)
    monkeypatch.setattr(
        vflow_main,
        "get_resolve_adapter",
        lambda: FakeResolveAdapter(succeeds=False),
    )

    result = runner.invoke(app, ["finish", "--project", "Project"])

    assert result.exit_code == 1
    assert "Resolve project export failed" in result.output
    assert local_output.read_bytes() == b"verified-final-video"
    assert not (archive / "Project Backups").exists()


def test_finish_stops_before_resolve_when_retained_output_is_missing(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    local = exports / "Final Videos" / "Project" / "missing.mov"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"local-only")
    adapter = FakeResolveAdapter()
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, ["finish", "--project", "Project"])

    assert result.exit_code == 1
    assert "archived Final Video is missing" in result.output
    assert adapter.calls == []
    assert local.read_bytes() == b"local-only"


def test_finish_rejects_retained_output_with_different_content(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    local = _retained_output(archive, exports)
    archived = archive / "Exports" / "Final Videos" / "Project" / "final.mov"
    archived.write_bytes(b"different-content")
    adapter = FakeResolveAdapter()
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)

    result = runner.invoke(app, ["finish", "--project", "Project"])

    assert result.exit_code == 1
    assert "content differs" in result.output
    assert adapter.calls == []
    assert local.read_bytes() == b"verified-final-video"


def test_repeated_finish_reuses_identical_archive_backup_without_overwriting(tmp_path, monkeypatch):
    archive, exports = _configure(tmp_path, monkeypatch)
    _retained_output(archive, exports)
    adapter = FakeResolveAdapter()
    monkeypatch.setattr(vflow_main, "get_resolve_adapter", lambda: adapter)
    args = ["finish", "--project", "Project"]

    first = runner.invoke(app, args)
    retry = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert retry.exit_code == 0, retry.output
    assert "Project Backups copied: 0" in retry.output
    assert "Project Backups skipped: 1" in retry.output
    assert (archive / "Project Backups" / "Project" / "Project.drp").read_bytes() == b"portable-project-backup"
