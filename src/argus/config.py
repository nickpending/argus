"""Configuration loading and validation."""

import tomllib
from pathlib import Path

from pydantic import ValidationError

from argus.models import Config


class ConfigError(Exception):
    """Configuration error."""

    pass


def load_config(config_path: str | Path | None = None) -> Config:
    """Load and validate configuration from TOML file.

    Args:
        config_path: Path to config file. Defaults to ~/.config/argus/config.toml

    Returns:
        Validated Config object

    Raises:
        ConfigError: If config file not found, invalid TOML, or validation fails
    """
    # Default to XDG config path
    if config_path is None:
        config_path = Path.home() / ".config" / "argus" / "config.toml"
    else:
        config_path = Path(config_path)

    # Check file exists
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}\nCreate one with: argus config init"
        )

    # Load TOML
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML syntax in {config_path}: {e}") from e
    except OSError as e:
        raise ConfigError(f"Failed to read config file {config_path}: {e}") from e

    # Validate with Pydantic
    try:
        config = Config(**data)
    except ValidationError as e:
        raise ConfigError(f"Config validation failed:\n{e}") from e

    return config
