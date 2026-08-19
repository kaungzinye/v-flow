import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import index_service, shoot_manifest
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


def _shoot(archive: Path, name: str) -> Path:
    return archive / "Video" / "RAW" / name


def _collection(archive: Path, name: str) -> Path:
    return archive / "Photo" / "RAW" / name


def _manifest(folder: Path) -> dict:
    return json.loads((folder / ".vflow-manifest.json").read_text())


def _count_media_reads(monkeypatch, suffix: str) -> dict[str, int]:
    reads: dict[str, int] = {}
    original_open = Path.open

    def counting_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode and "w" not in mode and self.suffix.lower() == suffix:
            reads[self.name] = reads.get(self.name, 0) + 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    return reads


def test_indexing_a_shoot_writes_a_complete_manifest(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    _write(old / "C0002.MP4", b"another-legacy-clip")

    result = runner.invoke(app, ["index", "--folder", "2019_Handmade"])

    assert result.exit_code == 0, result.output
    manifest = _manifest(old)
    assert manifest["manifest_version"] == 2
    assert manifest["checksum_algorithm"] == "sha256"
    assert manifest["shoot"] == "2019_Handmade"
    assert manifest["excluded"] == []
    assert manifest["deduplicated"] == []
    assert "partial" not in manifest
    entries = {entry["name"]: entry for entry in manifest["files"]}
    assert set(entries) == {"C0001.MP4", "C0002.MP4"}
    clip = entries["C0001.MP4"]
    assert clip["byte_size"] == len(b"legacy-clip")
    assert clip["checksum"] == shoot_manifest.checksum(old / "C0001.MP4")
    assert clip["source"] == "indexed-in-place"
    assert clip["indexed_at"]
    assert "source_relative_path" not in clip
    assert "source_name" not in clip
    assert "batch_id" not in clip


def test_indexing_a_collection_uses_the_collection_identity(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _collection(archive, "2019 Trip")
    _write(old / "DSC00001.ARW", b"legacy-frame")

    result = runner.invoke(app, ["index", "-f", "Photo/RAW/2019 Trip"])

    assert result.exit_code == 0, result.output
    manifest = _manifest(old)
    assert manifest["collection"] == "2019 Trip"
    assert [entry["name"] for entry in manifest["files"]] == ["DSC00001.ARW"]


def test_index_all_covers_both_media_kinds(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    shoot = _shoot(archive, "2019_Handmade")
    collection = _collection(archive, "2019 Trip")
    _write(shoot / "C0001.MP4", b"legacy-clip")
    _write(collection / "DSC00001.ARW", b"legacy-frame")

    result = runner.invoke(app, ["index", "--all"])

    assert result.exit_code == 0, result.output
    assert "Indexed 2 folder(s)" in result.output
    assert "Video/RAW/2019_Handmade" in result.output
    assert "Photo/RAW/2019 Trip" in result.output
    assert len(_manifest(shoot)["files"]) == 1
    assert len(_manifest(collection)["files"]) == 1


def test_indexed_contents_stay_byte_for_byte_untouched(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    before = {
        "bytes": (old / "C0001.MP4").read_bytes(),
        "stat": (old / "C0001.MP4").stat().st_mtime_ns,
    }

    assert runner.invoke(app, ["index", "--all"]).exit_code == 0

    assert sorted(path.name for path in old.iterdir()) == [
        ".vflow-manifest.json",
        "C0001.MP4",
    ]
    assert (old / "C0001.MP4").read_bytes() == before["bytes"]
    assert (old / "C0001.MP4").stat().st_mtime_ns == before["stat"]


def test_index_all_completes_a_partial_manifest_without_rehashing(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    _write(old / "C0002.MP4", b"another-legacy-clip")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")
    assert runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"]).exit_code == 0
    partial = _manifest(old)
    assert partial["partial"] is True
    already = {entry["name"]: entry for entry in partial["files"]}["C0001.MP4"]

    reads = _count_media_reads(monkeypatch, ".mp4")
    result = runner.invoke(app, ["index", "--all"])

    assert result.exit_code == 0, result.output
    assert "partially indexed" in result.output
    assert reads.get("C0001.MP4", 0) == 0
    assert reads["C0002.MP4"] == 1
    manifest = _manifest(old)
    assert "partial" not in manifest
    entries = {entry["name"]: entry for entry in manifest["files"]}
    assert set(entries) == {"C0001.MP4", "C0002.MP4"}
    assert entries["C0001.MP4"] == already


def test_an_interrupted_index_resumes_without_rehashing(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    _write(old / "C0002.MP4", b"another-legacy-clip")
    _write(old / "C0003.MP4", b"a-third-legacy-clip-here")
    original_entry = index_service.indexed_entry
    attempts = 0

    def fail_on_the_second_file(path):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_entry(path)

    monkeypatch.setattr(index_service, "indexed_entry", fail_on_the_second_file)
    interrupted = runner.invoke(app, ["index", "--all"])

    assert interrupted.exit_code == 1
    assert "simulated interruption" in interrupted.output
    partial = _manifest(old)
    assert partial["partial"] is True
    assert [entry["name"] for entry in partial["files"]] == ["C0001.MP4"]

    monkeypatch.setattr(index_service, "indexed_entry", original_entry)
    reads = _count_media_reads(monkeypatch, ".mp4")
    resumed = runner.invoke(app, ["index", "--all"])

    assert resumed.exit_code == 0, resumed.output
    assert reads.get("C0001.MP4", 0) == 0
    assert reads["C0002.MP4"] == 1
    assert reads["C0003.MP4"] == 1
    manifest = _manifest(old)
    assert "partial" not in manifest
    assert sorted(entry["name"] for entry in manifest["files"]) == [
        "C0001.MP4",
        "C0002.MP4",
        "C0003.MP4",
    ]


def test_a_second_index_run_rehashes_nothing(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    assert runner.invoke(app, ["index", "--all"]).exit_code == 0

    reads = _count_media_reads(monkeypatch, ".mp4")
    again = runner.invoke(app, ["index", "--all"])

    assert again.exit_code == 0, again.output
    assert "Indexed 0 folder(s)" in again.output
    assert "Already carrying a complete Shoot Manifest: 1 folder(s)." in again.output
    assert reads == {}


def test_indexed_folders_participate_in_ingest_dedup(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    assert runner.invoke(app, ["index", "--all"]).exit_code == 0
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")

    reads = _count_media_reads(monkeypatch, ".mp4")
    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"])

    assert result.exit_code == 0, result.output
    assert "0 copied, 0 already verified, 1 deduplicated" in result.output
    assert reads.get("C0001.MP4", 0) == 0
    skipped = _manifest(_shoot(archive, "Fresh"))["deduplicated"]
    assert skipped[0]["existing_location"] == "Video/RAW/2019_Handmade/C0001.MP4"


def test_indexed_collections_participate_in_photo_ingest_dedup(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _collection(archive, "2019 Trip")
    _write(old / "DSC00001.ARW", b"legacy-frame")
    assert runner.invoke(app, ["index", "--all"]).exit_code == 0
    source = tmp_path / "CARD"
    _write(source / "DSC09001.ARW", b"legacy-frame")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"])

    assert result.exit_code == 0, result.output
    skipped = _manifest(_collection(archive, "Fresh"))["deduplicated"]
    assert skipped[0]["existing_location"] == "Photo/RAW/2019 Trip/DSC00001.ARW"


def test_dry_run_reports_folder_count_and_bytes_without_reading(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    shoot = _shoot(archive, "2019_Handmade")
    collection = _collection(archive, "2019 Trip")
    _write(shoot / "C0001.MP4", b"legacy-clip")
    _write(shoot / "C0002.MP4", b"another-legacy-clip")
    _write(collection / "DSC00001.ARW", b"legacy-frame")
    total = len(b"legacy-clip") + len(b"another-legacy-clip") + len(b"legacy-frame")

    reads = _count_media_reads(monkeypatch, ".mp4")
    result = runner.invoke(app, ["index", "--all", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert f"Would index 2 folder(s): 3 file(s), {total} bytes to read." in result.output
    assert "Dry run: no file was read and no manifest was written." in result.output
    assert reads == {}
    assert not (shoot / ".vflow-manifest.json").exists()
    assert not (collection / ".vflow-manifest.json").exists()


def test_indexing_ignores_hidden_files_and_the_extras_folder(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    _write(old / ".DS_Store", b"finder-noise")
    _write(old / ".vflow-extras" / "CLIP" / "C0001M01.XML", b"sidecar")

    assert runner.invoke(app, ["index", "--all"]).exit_code == 0

    manifest = _manifest(old)
    assert [entry["name"] for entry in manifest["files"]] == ["C0001.MP4"]
    assert "partial" not in manifest


def test_index_needs_an_explicit_target(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["index"])

    assert result.exit_code == 1
    assert "Give --folder for each Shoot or Collection, or --all." in result.output


def test_an_unknown_folder_is_reported(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["index", "-f", "Nowhere"])

    assert result.exit_code == 1
    assert "No Shoot or Collection named 'Nowhere'" in result.output


def test_a_name_in_both_roots_asks_for_a_path(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    _write(_shoot(archive, "Iceland") / "C0001.MP4", b"legacy-clip")
    _write(_collection(archive, "Iceland") / "DSC00001.ARW", b"legacy-frame")

    result = runner.invoke(app, ["index", "-f", "Iceland"])

    assert result.exit_code == 1
    assert "names both a Shoot and a Collection" in result.output
    assert "Video/RAW/Iceland" in result.output


def test_index_never_schedules_itself(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    result = runner.invoke(app, ["index", "--help"])

    assert result.exit_code == 0, result.output
    for option in ("--watch", "--schedule", "--background", "--auto"):
        assert option not in result.output
