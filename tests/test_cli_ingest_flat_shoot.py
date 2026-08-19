import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vflow import card_ingest
from vflow import config as vflow_config
from vflow.main import app


runner = CliRunner()


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    archive = tmp_path / "archive"
    laptop = tmp_path / "laptop"
    exports = tmp_path / "exports"
    for path in (archive, laptop, exports):
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
    return archive, laptop


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _shoot(archive: Path, name: str) -> Path:
    return archive / "Video" / "RAW" / name


def _manifest(shoot: Path) -> dict:
    return json.loads((shoot / ".vflow-manifest.json").read_text())


def _sony_card(root: Path) -> None:
    clips = root / "PRIVATE" / "M4ROOT" / "CLIP"
    _write(clips / "C6634.MP4", b"first-clip")
    _write(clips / "C6634M01.XML", b"sidecar")
    _write(clips / "C6635.MP4", b"second-clip")
    _write(root / "PRIVATE" / "M4ROOT" / "THMBNL" / "C6634T01.JPG", b"thumb")
    _write(root / "PRIVATE" / "M4ROOT" / "GENERAL" / "MEDIAPRO.XML", b"card-database")
    _write(root / "._C6634.MP4", b"appledouble")


def test_sony_card_ingest_lands_flat_footage_and_hidden_manifest(tmp_path, monkeypatch):
    archive, laptop = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _sony_card(source)

    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            str(source),
            "--shoot",
            "2026-08-02_Stockholm",
            "--import-batch",
            "card-a",
        ],
    )

    assert result.exit_code == 0, result.output
    shoot = _shoot(archive, "2026-08-02_Stockholm")
    assert sorted(path.name for path in shoot.iterdir()) == [
        ".vflow-manifest.json",
        "C6634.MP4",
        "C6635.MP4",
    ]
    assert (shoot / "C6634.MP4").read_bytes() == b"first-clip"
    assert list(laptop.rglob("*")) == []

    manifest = _manifest(shoot)
    assert manifest["manifest_version"] == 2
    assert manifest["checksum_algorithm"] == "sha256"
    assert manifest["shoot"] == "2026-08-02_Stockholm"
    entries = {entry["name"]: entry for entry in manifest["files"]}
    clip = entries["C6634.MP4"]
    assert clip["byte_size"] == len(b"first-clip")
    assert len(clip["checksum"]) == 64
    assert clip["source_relative_path"] == "PRIVATE/M4ROOT/CLIP/C6634.MP4"
    assert clip["source_name"] == "CARD"
    assert clip["batch_id"] == "card-a"
    assert clip["ingested_at"]

    excluded = {item["source_relative_path"]: item for item in manifest["excluded"]}
    assert set(excluded) == {
        "PRIVATE/M4ROOT/CLIP/C6634M01.XML",
        "PRIVATE/M4ROOT/THMBNL/C6634T01.JPG",
        "PRIVATE/M4ROOT/GENERAL/MEDIAPRO.XML",
        "._C6634.MP4",
    }
    assert excluded["PRIVATE/M4ROOT/CLIP/C6634M01.XML"]["reason"] == "non-footage file type"
    assert excluded["._C6634.MP4"]["reason"] == "AppleDouble sidecar"
    assert "Retained copies: 1 (Archive only)" in result.output


def test_include_all_keeps_non_footage_out_of_the_flat_shoot(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _sony_card(source)

    result = runner.invoke(
        app,
        ["ingest", "-s", str(source), "-n", "Shoot", "--import-batch", "card-a", "--include-all"],
    )

    assert result.exit_code == 0, result.output
    shoot = _shoot(archive, "Shoot")
    assert sorted(path.name for path in shoot.iterdir()) == [
        ".vflow-extras",
        ".vflow-manifest.json",
        "C6634.MP4",
        "C6635.MP4",
    ]
    extras = shoot / ".vflow-extras"
    assert (extras / "PRIVATE" / "M4ROOT" / "CLIP" / "C6634M01.XML").read_bytes() == b"sidecar"
    assert (extras / "PRIVATE" / "M4ROOT" / "THMBNL" / "C6634T01.JPG").read_bytes() == b"thumb"

    excluded = {item["source_relative_path"]: item for item in _manifest(shoot)["excluded"]}
    stored = excluded["PRIVATE/M4ROOT/CLIP/C6634M01.XML"]
    assert stored["stored_as"] == ".vflow-extras/PRIVATE/M4ROOT/CLIP/C6634M01.XML"
    assert len(stored["checksum"]) == 64


def test_audio_files_count_as_footage(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "recorder"
    _write(source / "ZOOM0001.WAV", b"double-system-audio")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    assert (_shoot(archive, "Shoot") / "ZOOM0001.WAV").read_bytes() == b"double-system-audio"


def test_each_source_file_is_read_once_during_ingest(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "CLIP" / "C0001.MP4", b"clip-one")
    _write(source / "CLIP" / "C0002.MP4", b"clip-two-longer")
    reads: dict[str, int] = {}
    original_open = Path.open

    def counting_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode and source in self.parents:
            reads[self.name] = reads.get(self.name, 0) + 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    assert reads == {"C0001.MP4": 1, "C0002.MP4": 1}


def test_destination_is_verified_by_rehashing_the_archive_copy(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")
    original_copy = card_ingest._copy_hashing

    def copy_then_corrupt(source_file, temporary):
        digest = original_copy(source_file, temporary)
        temporary.write_bytes(b"corrupted-on-arrival")
        return digest

    monkeypatch.setattr(card_ingest, "_copy_hashing", copy_then_corrupt)
    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 1
    assert "Checksum verification failed" in result.output
    assert not (_shoot(archive, "Shoot") / "C0001.MP4").exists()


def test_repeated_ingest_resumes_from_the_manifest(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")
    _write(source / "C0002.MP4", b"clip-two-longer")
    original_place = card_ingest._place_verified
    attempts = 0

    def fail_second_copy(source_file, destination, expected=None):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated interruption")
        return original_place(source_file, destination, expected)

    monkeypatch.setattr(card_ingest, "_place_verified", fail_second_copy)
    args = ["ingest", "-s", str(source), "-n", "Shoot"]
    interrupted = runner.invoke(app, args)

    assert interrupted.exit_code == 1
    shoot = _shoot(archive, "Shoot")
    assert (shoot / "C0001.MP4").read_bytes() == b"clip-one"
    assert not (shoot / ".vflow-manifest.json").exists()
    assert (shoot / ".vflow-manifest.pending.json").exists()

    monkeypatch.setattr(card_ingest, "_place_verified", original_place)
    reads: list[str] = []
    original_open = Path.open

    def counting_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode and source in self.parents:
            reads.append(self.name)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    retry = runner.invoke(app, args)

    assert retry.exit_code == 0, retry.output
    assert "1 copied, 1 already verified" in retry.output
    assert reads == ["C0002.MP4"]
    assert (shoot / "C0002.MP4").read_bytes() == b"clip-two-longer"
    assert not (shoot / ".vflow-manifest.pending.json").exists()
    names = sorted(entry["name"] for entry in _manifest(shoot)["files"])
    assert names == ["C0001.MP4", "C0002.MP4"]


def test_resume_recopies_a_file_missing_from_the_shoot(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"clip-one")
    args = ["ingest", "-s", str(source), "-n", "Shoot"]
    assert runner.invoke(app, args).exit_code == 0
    shoot = _shoot(archive, "Shoot")
    (shoot / "C0001.MP4").unlink()

    retry = runner.invoke(app, args)

    assert retry.exit_code == 0, retry.output
    assert (shoot / "C0001.MP4").read_bytes() == b"clip-one"
    assert len(_manifest(shoot)["files"]) == 1


def test_already_archived_content_is_deduplicated_across_shoots(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "C0001.MP4", b"same-content")
    _write(second / "C0009.MP4", b"same-content")
    _write(second / "C0010.MP4", b"fresh-content")

    assert runner.invoke(app, ["ingest", "-s", str(first), "-n", "Monday"]).exit_code == 0
    result = runner.invoke(app, ["ingest", "-s", str(second), "-n", "Tuesday"])

    assert result.exit_code == 0, result.output
    assert "1 copied, 0 already verified, 1 deduplicated" in result.output
    tuesday = _shoot(archive, "Tuesday")
    assert sorted(path.name for path in tuesday.iterdir()) == [
        ".vflow-manifest.json",
        "C0010.MP4",
    ]
    skipped = _manifest(tuesday)["deduplicated"]
    assert len(skipped) == 1
    assert skipped[0]["source_relative_path"] == "C0009.MP4"
    assert skipped[0]["existing_location"] == "Video/RAW/Monday/C0001.MP4"


def test_same_name_with_different_content_lands_suffixed(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "C0001.MP4", b"first-card")
    _write(second / "C0001.MP4", b"second-card")

    assert runner.invoke(app, ["ingest", "-s", str(first), "-n", "Shoot"]).exit_code == 0
    result = runner.invoke(app, ["ingest", "-s", str(second), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    shoot = _shoot(archive, "Shoot")
    assert (shoot / "C0001.MP4").read_bytes() == b"first-card"
    assert (shoot / "C0001_b.MP4").read_bytes() == b"second-card"
    entries = {entry["name"]: entry for entry in _manifest(shoot)["files"]}
    assert entries["C0001_b.MP4"]["original_name"] == "C0001.MP4"


def test_same_name_and_size_from_one_card_never_skips_on_name(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "CARD"
    _write(source / "A" / "C0001.MP4", b"AAAA")
    _write(source / "B" / "C0001.MP4", b"BBBB")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    shoot = _shoot(archive, "Shoot")
    assert (shoot / "C0001.MP4").read_bytes() == b"AAAA"
    assert (shoot / "C0001_b.MP4").read_bytes() == b"BBBB"


def test_multiple_cards_merge_into_one_flat_shoot_and_manifest(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    first = tmp_path / "card-a"
    second = tmp_path / "card-b"
    _write(first / "CLIP" / "C0001.MP4", b"first-card")
    _write(second / "CLIP" / "C0002.MP4", b"second-card")

    for source in (first, second):
        assert runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"]).exit_code == 0

    shoot = _shoot(archive, "Shoot")
    assert sorted(path.name for path in shoot.iterdir()) == [
        ".vflow-manifest.json",
        "C0001.MP4",
        "C0002.MP4",
    ]
    manifest = _manifest(shoot)
    batches = {entry["batch_id"] for entry in manifest["files"]}
    assert len(batches) == 2
    assert {entry["source_name"] for entry in manifest["files"]} == {"card-a", "card-b"}


def test_unavailable_working_location_does_not_block_archive_ingest(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    config = yaml.safe_load(vflow_config.CONFIG_PATH.read_text())
    config["locations"]["working"]["laptop"] = str(tmp_path / "unavailable-laptop")
    vflow_config.CONFIG_PATH.write_text(yaml.safe_dump(config))
    source = tmp_path / "card"
    _write(source / "C0001.MP4", b"original")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    assert (_shoot(archive, "Shoot") / "C0001.MP4").read_bytes() == b"original"


def test_batch_identity_is_stable_across_retries(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    source = tmp_path / "card"
    _write(source / "C0001.MP4", b"original")
    args = ["ingest", "-s", str(source), "-n", "Shoot"]

    first = runner.invoke(app, args)
    retry = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert retry.exit_code == 0, retry.output
    assert "0 copied, 1 already verified" in retry.output
    manifest = _manifest(_shoot(archive, "Shoot"))
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["batch_id"].startswith("card-")


def test_ingest_never_overwrites_an_existing_hand_made_file(tmp_path, monkeypatch):
    archive, _ = _configure(tmp_path, monkeypatch)
    shoot = _shoot(archive, "Shoot")
    _write(shoot / "C0001.MP4", b"hand-placed")
    source = tmp_path / "CARD"
    _write(source / "C0001.MP4", b"from-the-card")

    result = runner.invoke(app, ["ingest", "-s", str(source), "-n", "Shoot"])

    assert result.exit_code == 0, result.output
    assert (shoot / "C0001.MP4").read_bytes() == b"hand-placed"
    assert (shoot / "C0001_b.MP4").read_bytes() == b"from-the-card"
