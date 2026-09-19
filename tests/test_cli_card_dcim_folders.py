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


def _card_with_rolled_over_dcim(root: Path) -> None:
    """A Sony card whose counter rolled DCIM into a second numbered folder."""
    _write(root / "DCIM" / "100MSDCF" / "A7409998.ARW", b"before-rollover")
    _write(root / "DCIM" / "101MSDCF" / "A7400001.ARW", b"after-rollover")
    _write(root / "DCIM" / "101MSDCF" / "A7400002.ARW", b"after-rollover-2")


def test_card_report_lists_photos_from_every_dcim_folder(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _card_with_rolled_over_dcim(source)

    result = runner.invoke(app, ["card-report", "-s", str(source)])

    assert result.exit_code == 0, result.output
    assert "PHOTOS  — folder not found" not in result.output
    assert "3 file(s)" in result.output
    assert "A7400001.ARW .. A7409998.ARW" in result.output


def test_card_verify_checks_photos_from_every_dcim_folder(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _card_with_rolled_over_dcim(source)
    collection = archive / "Photo" / "RAW" / "Grad"
    _write(collection / "A7409998.ARW", b"before-rollover")
    _write(collection / "A7400001.ARW", b"after-rollover")

    result = runner.invoke(
        app, ["card-verify", "-s", str(source), "--photo-shoot", "Grad"]
    )

    assert "On card:       3" in result.output
    assert "Missing:       1" in result.output
    assert "- A7400002.ARW" in result.output
    assert "OVERALL: FAIL" in result.output
