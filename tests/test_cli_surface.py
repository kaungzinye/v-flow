from typer.main import get_command
from typer.testing import CliRunner

from vflow.main import app


runner = CliRunner()


def test_removed_commands_are_absent() -> None:
    command = get_command(app)

    assert not {"prep", "pull", "create-select", "remove-duplicates"} & set(
        command.commands
    )


def test_removed_ingest_flags_are_absent() -> None:
    result = runner.invoke(app, ["ingest", "--help"])

    assert result.exit_code == 0, result.output
    for option in ("--force", "--skip-laptop", "--workspace", "--split-by-gap"):
        assert option not in result.output


def test_removed_backup_deletion_flags_are_absent() -> None:
    backup_help = runner.invoke(app, ["backup", "--help"])
    verify_help = runner.invoke(app, ["verify-backup", "--help"])

    assert backup_help.exit_code == 0, backup_help.output
    assert verify_help.exit_code == 0, verify_help.output
    assert "--delete-source" not in backup_help.output
    assert "--allow-delete" not in verify_help.output
