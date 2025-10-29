import yaml
from pathlib import Path
import typer

CONFIG_PATH = Path.home() / ".vflow_config.yml"

def load_config():
    """Loads the configuration from the user's home directory."""
    if not CONFIG_PATH.exists():
        typer.echo(f"Configuration file not found at: {CONFIG_PATH}")
        typer.echo("Please create this file with your storage locations.")
        raise typer.Exit(code=1)
    
    with open(CONFIG_PATH, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            typer.echo(f"Error parsing configuration file: {e}")
            raise typer.Exit(code=1)
    
    # Basic validation
    if "locations" not in config or not isinstance(config["locations"], dict):
        typer.echo("Configuration file must contain a 'locations' dictionary.")
        raise typer.Exit(code=1)
        
    return config

def get_location(config: dict, name: str) -> Path:
    """Gets a specific location from the config and ensures it exists."""
    path_str = config["locations"].get(name)
    if not path_str:
        typer.echo(f"Location '{name}' not defined in config file.")
        raise typer.Exit(code=1)
        
    path = Path(path_str)
    if not path.exists() or not path.is_dir():
        typer.echo(f"The directory for location '{name}' does not exist: {path}")
        raise typer.Exit(code=1)
        
    return path
