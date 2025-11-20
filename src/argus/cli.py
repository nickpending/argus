"""Command-line interface for Argus."""

import sys
from pathlib import Path

import click
import uvicorn

from argus.config import ConfigError, load_config


@click.group()
def main() -> None:
    """Argus observability platform CLI."""
    pass


@main.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config file (default: ~/.config/argus/config.toml)",
)
@click.option(
    "--host",
    type=str,
    default=None,
    help="Override server host from config",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Override server port from config",
)
def serve(config: Path | None, host: str | None, port: int | None) -> None:
    """Start the Argus server."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)

    server_host = host if host is not None else cfg.server.host
    server_port = port if port is not None else cfg.server.port

    click.echo(f"Starting Argus server on {server_host}:{server_port}")

    uvicorn.run(
        "argus.server:app",
        host=server_host,
        port=server_port,
        log_level=cfg.logging.level.lower(),
    )
