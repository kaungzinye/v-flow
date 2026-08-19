import json
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


def _shoot(archive: Path, name: str) -> Path:
    return archive / "Video" / "RAW" / name


def _collection(archive: Path, name: str) -> Path:
    return archive / "Photo" / "RAW" / name


def _manifest(folder: Path) -> dict:
    return json.loads((folder / ".vflow-manifest.json").read_text())


def _count_media_reads(monkeypatch, suffix: str) -> dict[str, int]:
    """Count content reads of archived media, ignoring manifest bookkeeping."""
    reads: dict[str, int] = {}
    original_open = Path.open

    def counting_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode and "w" not in mode and self.suffix.lower() == suffix:
            reads[self.name] = reads.get(self.name, 0) + 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    return reads


def test_unindexed_shoot_content_deduplicates_a_card_clip(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"])

    assert result.exit_code == 0, result.output
    assert "0 copied, 0 already verified, 1 deduplicated" in result.output
    fresh = _shoot(archive, "Fresh")
    assert sorted(path.name for path in fresh.iterdir()) == [".vflow-manifest.json"]
    skipped = _manifest(fresh)["deduplicated"]
    assert len(skipped) == 1
    assert skipped[0]["existing_location"] == "Video/RAW/2019_Handmade/C0001.MP4"


def test_unindexed_collection_content_deduplicates_a_card_photo(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _collection(archive, "2019 Trip")
    _write(old / "DSC00001.ARW", b"legacy-frame")
    source = tmp_path / "CARD"
    _write(source / "DSC09001.ARW", b"legacy-frame")

    result = runner.invoke(app, ["photo-ingest", "-s", str(source), "-c", "Fresh"])

    assert result.exit_code == 0, result.output
    assert "0 copied, 0 already verified, 1 deduplicated" in result.output
    skipped = _manifest(_collection(archive, "Fresh"))["deduplicated"]
    assert len(skipped) == 1
    assert skipped[0]["existing_location"] == "Photo/RAW/2019 Trip/DSC00001.ARW"


def test_same_name_and_size_with_different_content_still_copies(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"AAAAAAAAAAA")
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"BBBBBBBBBBB")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"])

    assert result.exit_code == 0, result.output
    assert "1 copied, 0 already verified, 0 deduplicated" in result.output
    assert (_shoot(archive, "Fresh") / "C0001.MP4").read_bytes() == b"BBBBBBBBBBB"
    assert (old / "C0001.MP4").read_bytes() == b"AAAAAAAAAAA"


def test_same_name_and_size_photo_with_different_content_still_copies(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _collection(archive, "2019 Trip")
    _write(old / "DSC00001.ARW", b"AAAAAAAAAAA")
    source = tmp_path / "CARD"
    _write(source / "DSC00001.ARW", b"BBBBBBBBBBB")

    result = runner.invoke(app, ["photo-ingest", "-s", str(source), "-c", "Fresh"])

    assert result.exit_code == 0, result.output
    assert (_collection(archive, "Fresh") / "DSC00001.ARW").read_bytes() == b"BBBBBBBBBBB"
    assert (old / "DSC00001.ARW").read_bytes() == b"AAAAAAAAAAA"


def test_candidate_checksums_land_in_a_partial_manifest(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    _write(old / "C0002.MP4", b"another-legacy-clip")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")

    assert runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"]).exit_code == 0

    manifest = _manifest(old)
    assert manifest["partial"] is True
    assert manifest["shoot"] == "2019_Handmade"
    entries = {entry["name"]: entry for entry in manifest["files"]}
    assert set(entries) == {"C0001.MP4"}
    indexed = entries["C0001.MP4"]
    assert indexed["source"] == "indexed-in-place"
    assert indexed["byte_size"] == len(b"legacy-clip")
    assert len(indexed["checksum"]) == 64
    assert "batch_id" not in indexed
    assert "source_relative_path" not in indexed


def test_a_repeat_ingest_reads_the_old_file_zero_times(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")
    args = ["ingest", "-s", str(source), "-n", "Fresh"]

    assert runner.invoke(app, args).exit_code == 0

    reads = _count_media_reads(monkeypatch, ".mp4")
    repeat = runner.invoke(app, args)

    assert repeat.exit_code == 0, repeat.output
    assert "1 deduplicated" in repeat.output
    assert reads.get("C0001.MP4", 0) == 0


def test_a_folder_without_a_size_match_is_never_read(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    untouched = _shoot(archive, "2019_Handmade")
    _write(untouched / "C0001.MP4", b"a-legacy-clip-of-its-own-length")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"short")

    reads = _count_media_reads(monkeypatch, ".mp4")
    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"])

    assert result.exit_code == 0, result.output
    assert reads.get("C0001.MP4", 0) == 0
    assert list(untouched.iterdir()) == [untouched / "C0001.MP4"]


def test_a_partial_manifest_is_distinguishable_from_a_complete_one(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    _write(old / "C0002.MP4", b"another-legacy-clip")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")

    assert runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"]).exit_code == 0

    assert _manifest(old)["partial"] is True
    assert "partial" not in _manifest(_shoot(archive, "Fresh"))


def test_hashing_the_last_uncovered_file_completes_the_manifest(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"legacy-clip")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"legacy-clip")

    assert runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"]).exit_code == 0

    assert "partial" not in _manifest(old)


def test_a_second_card_clip_hashes_each_candidate_only_once(tmp_path, monkeypatch):
    archive = _configure(tmp_path, monkeypatch)
    old = _shoot(archive, "2019_Handmade")
    _write(old / "C0001.MP4", b"aaaa")
    _write(old / "C0002.MP4", b"bbbb")
    source = tmp_path / "CARD"
    _write(source / "C9001.MP4", b"bbbb")
    _write(source / "C9002.MP4", b"aaaa")

    reads = _count_media_reads(monkeypatch, ".mp4")
    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Fresh"])

    assert result.exit_code == 0, result.output
    assert "0 copied, 0 already verified, 2 deduplicated" in result.output
    assert reads["C0001.MP4"] == 1
    assert reads["C0002.MP4"] == 1
