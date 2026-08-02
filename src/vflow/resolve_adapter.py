from __future__ import annotations

from collections import defaultdict
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

    def validate_project_media(
        self,
        project_name: str,
        path_map: dict[Path, Path],
        allow_relink: bool = True,
    ) -> dict:
        """Confirm or relink Project media before removing a Working Copy."""


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

    @staticmethod
    def _media_pool_items(folder) -> list:
        items = list(folder.GetClipList() or [])
        for child in folder.GetSubFolderList() or []:
            items.extend(DaVinciResolveAdapter._media_pool_items(child))
        return items

    def validate_project_media(
        self,
        project_name: str,
        path_map: dict[Path, Path],
        allow_relink: bool = True,
    ) -> dict:
        project = self._project_manager.GetCurrentProject()
        if project is None or project.GetName() != project_name:
            project = self._project_manager.LoadProject(project_name)
        if project is None:
            raise ValueError(
                f"Resolve validation failed: Project '{project_name}' is unavailable"
            )

        media_pool = project.GetMediaPool()
        root = media_pool.GetRootFolder() if media_pool is not None else None
        if media_pool is None or root is None:
            raise ValueError(
                f"Resolve validation failed: Project '{project_name}' has no accessible Media Pool"
            )

        normalized_map = {
            source.resolve(strict=False): destination.resolve(strict=False)
            for source, destination in path_map.items()
        }
        archive_paths = set(normalized_map.values())
        linked_to_working = []
        confirmed = 0
        for item in self._media_pool_items(root):
            properties = item.GetClipProperty() or {}
            value = properties.get("File Path") if isinstance(properties, dict) else None
            if not value:
                continue
            current = Path(value).resolve(strict=False)
            if current in normalized_map:
                linked_to_working.append((item, normalized_map[current]))
            elif current in archive_paths and current.is_file():
                confirmed += 1

        if linked_to_working and not allow_relink:
            return {
                "checked": confirmed + len(linked_to_working),
                "confirmed": confirmed,
                "relinked": 0,
                "pending_relinks": [
                    str(destination) for _, destination in linked_to_working
                ],
                "unresolved": [],
            }

        by_directory = defaultdict(list)
        for item, destination in linked_to_working:
            by_directory[destination.parent].append((item, destination))

        unresolved = []
        relinked = 0
        for directory, pairs in by_directory.items():
            if not media_pool.RelinkClips([item for item, _ in pairs], str(directory)):
                unresolved.extend(str(destination) for _, destination in pairs)
                continue
            for item, destination in pairs:
                properties = item.GetClipProperty() or {}
                value = properties.get("File Path") if isinstance(properties, dict) else None
                current = Path(value).resolve(strict=False) if value else None
                if current == destination and destination.is_file():
                    relinked += 1
                else:
                    unresolved.append(str(destination))

        return {
            "checked": confirmed + len(linked_to_working),
            "confirmed": confirmed,
            "relinked": relinked,
            "pending_relinks": [],
            "unresolved": unresolved,
        }


def get_resolve_adapter() -> ResolveAdapter:
    return DaVinciResolveAdapter()
