from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ResolveUnavailableError(RuntimeError):
    """DaVinci Resolve or its supported scripting API is unavailable."""


class ResolveAdapter(Protocol):
    def export_project_backup(
        self,
        project_name: str,
        destination: Path,
        include_stills_and_luts: bool = True,
    ) -> bool:
        """Export a portable Resolve Project Backup."""


class DaVinciResolveAdapter:
    """Use Resolve's supported project-level scripting API."""

    def __init__(self) -> None:
        try:
            import DaVinciResolveScript as resolve_script
        except ImportError as error:
            raise ResolveUnavailableError(
                "Resolve access failed: DaVinciResolveScript is unavailable. "
                "Enable external scripting in Resolve and configure its Developer/Scripting modules."
            ) from error

        resolve = resolve_script.scriptapp("Resolve")
        if resolve is None:
            raise ResolveUnavailableError(
                "Resolve access failed: DaVinci Resolve is not running or scripting access is disabled."
            )
        project_manager = resolve.GetProjectManager()
        if project_manager is None:
            raise ResolveUnavailableError(
                "Resolve access failed: the current Project Library is unavailable."
            )
        self._project_manager = project_manager

    def export_project_backup(
        self,
        project_name: str,
        destination: Path,
        include_stills_and_luts: bool = True,
    ) -> bool:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return bool(
            self._project_manager.ExportProject(
                project_name,
                str(destination),
                include_stills_and_luts,
            )
        )


def get_resolve_adapter() -> ResolveAdapter:
    return DaVinciResolveAdapter()
