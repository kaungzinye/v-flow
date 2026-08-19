from pathlib import Path
from typing import Any, Optional

import typer
import yaml

from .shoot_manifest import safe_subpath


CONFIG_PATH = Path.home() / ".vflow_config.yml"
CONFIG_VERSION = 2
DEFAULT_LAPTOP_FREE_SPACE_RESERVE_GB = 50

# Where each media kind's flat folders sit under the Archive. A 'layout' section
# in the config file overrides a key; an absent section or key keeps the default.
DEFAULT_LAYOUT = {"footage_raw": "Video/RAW", "photo_raw": "Photo/RAW"}
LAYOUT_KEYS = {"video": "footage_raw", "photo": "photo_raw"}


def load_config() -> dict:
    """Load role-based storage configuration."""
    if not CONFIG_PATH.exists():
        typer.echo(f"Configuration file not found at: {CONFIG_PATH}")
        typer.echo("Create it with 'v-flow make-config'.")
        raise typer.Exit(code=1)

    try:
        with CONFIG_PATH.open("r") as config_file:
            loaded = yaml.safe_load(config_file)
    except yaml.YAMLError as error:
        typer.echo(f"Error parsing configuration file: {error}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(loaded, dict):
        typer.echo("Configuration file must contain a YAML dictionary.", err=True)
        raise typer.Exit(code=1)

    locations = loaded.get("locations")
    if not isinstance(locations, dict):
        typer.echo("Configuration file must contain a 'locations' dictionary.", err=True)
        raise typer.Exit(code=1)

    missing_roles = [role for role in ("archive", "exports") if not locations.get(role)]
    if missing_roles:
        typer.echo(
            "Configuration is missing storage role(s): " + ", ".join(missing_roles),
            err=True,
        )
        raise typer.Exit(code=1)

    working = locations.get("working")
    if not isinstance(working, dict) or not working:
        typer.echo(
            "Configuration must contain at least one named location under 'locations.working'.",
            err=True,
        )
        raise typer.Exit(code=1)

    return loaded


def resolve_location(app_config: dict, name: str) -> Optional[str]:
    """Resolve an Archive, Exports, or named Working Location path."""
    locations = app_config.get("locations", {})
    if name in ("archive", "exports") and isinstance(locations.get(name), str):
        return locations[name]

    working = locations.get("working", {})
    if isinstance(working, dict) and isinstance(working.get(name), str):
        return working[name]
    return None


def get_location(app_config: dict, name: str) -> Path:
    """Get a configured storage role and require its directory."""
    path_str = resolve_location(app_config, name)
    if not path_str:
        typer.echo(f"Location '{name}' is not defined in the configuration.", err=True)
        raise typer.Exit(code=1)

    path = Path(path_str)
    if not path.exists() or not path.is_dir():
        typer.echo(f"Location '{name}' is unavailable: {path}", err=True)
        raise typer.Exit(code=1)
    return path


def configured_layout(app_config: dict) -> dict[str, str]:
    """The layout subpath configured for each layout key, defaults filling the gaps."""
    section = app_config.get("layout") or {}
    if not isinstance(section, dict):
        typer.echo("Configuration 'layout' must be a dictionary.", err=True)
        raise typer.Exit(code=1)
    return {key: section.get(key, default) for key, default in DEFAULT_LAYOUT.items()}


def get_layout(app_config: dict) -> dict[str, tuple[str, ...]]:
    """Archive subpath segments per media kind, validated to stay inside the Archive."""
    configured = configured_layout(app_config)
    layout: dict[str, tuple[str, ...]] = {}
    for kind, key in LAYOUT_KEYS.items():
        try:
            layout[kind] = safe_subpath(configured[key], f"layout.{key}")
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1)
    return layout


def get_setting(app_config: dict, key: str, default: Any = None) -> Any:
    """Get a setting, returning the supplied default when it is absent."""
    return app_config.get("settings", {}).get(key, default)


def save_config(app_config: dict) -> None:
    """Write configuration to its configured persistent path."""
    with CONFIG_PATH.open("w") as config_file:
        yaml.safe_dump(
            app_config,
            config_file,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def location_status(path_str: str) -> str:
    """Describe whether a configured storage path is currently available."""
    path = Path(path_str)
    return "available" if path.exists() and path.is_dir() else "unavailable"
