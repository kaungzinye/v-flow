from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app


runner = CliRunner()


def test_restore_folder_dry_run_and_real(tmp_path):
    """
    Test restore-folder in dry-run and real modes:
    - creates a simple source tree
    - dry-runs restore and checks planned copies
    - runs real restore and checks files exist at destination
    """
    source = tmp_path / "src"
    dest = tmp_path / "dest"

    # Create a deeper tree with many files to better exercise the restore logic
    (source / "sub1").mkdir(parents=True)
    (source / "sub2" / "nested").mkdir(parents=True)

    (source / "a.txt").write_text("root")
    (source / "sub1" / "b.txt").write_text("sub1")
    (source / "sub2" / "nested" / "c.txt").write_text("sub2-nested")

    # Add a bunch of numbered files to stress-test iteration
    for i in range(50):
        (source / "sub1" / f"clip_{i:03d}.mp4").write_text(f"clip-{i}")

    # Dry-run: nothing should be created in dest, but output should mention files
    result_dry = runner.invoke(
        app,
        [
            "restore-folder",
            "--source",
            str(source),
            "--destination",
            str(dest),
            "--dry-run",
        ],
    )

    assert result_dry.exit_code == 0, result_dry.output
    assert "WOULD COPY: a.txt" in result_dry.output
    assert "WOULD COPY: sub1/b.txt" in result_dry.output

    # Real restore
    result_real = runner.invoke(
        app,
        [
            "restore-folder",
            "--source",
            str(source),
            "--destination",
            str(dest),
        ],
    )

    assert result_real.exit_code == 0, result_real.output
    assert (dest / "a.txt").read_text() == "root"
    assert (dest / "sub1" / "b.txt").read_text() == "sub1"
    assert (dest / "sub2" / "nested" / "c.txt").read_text() == "sub2-nested"

    # All numbered clips should also be present
    for i in range(50):
        assert (dest / "sub1" / f"clip_{i:03d}.mp4").read_text() == f"clip-{i}"

