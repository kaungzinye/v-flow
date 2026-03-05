from pathlib import Path

from typer.testing import CliRunner

from vflow.main import app


runner = CliRunner()


def test_verify_backup_mirror_mode(tmp_path):
    """
    Verify-backup in mirror mode should succeed when destination is a path-for-path copy
    of the source tree.
    """
    source = tmp_path / "src"
    dest = tmp_path / "dest"

    (source / "sub").mkdir(parents=True)
    (dest / "sub").mkdir(parents=True)

    (source / "sub" / "file.txt").write_text("same")
    (dest / "sub" / "file.txt").write_text("same")

    result = runner.invoke(
        app,
        [
            "verify-backup",
            "--source",
            str(source),
            "--destination",
            str(dest),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Backup verification PASSED" in result.output


