"""Command-line interface for Argus."""

import json
import os
import sys
from pathlib import Path

import click
import httpx
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


@main.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config file (default: ~/.config/argus/config.toml)",
)
@click.option("--source", type=str, default=None, help="Filter by event source")
@click.option("--event-type", type=str, default=None, help="Filter by event type")
@click.option("--level", type=str, default=None, help="Filter by level (debug/info/warn/error)")
@click.option("--since", type=str, default=None, help="Filter events since timestamp (ISO8601)")
@click.option("--until", type=str, default=None, help="Filter events until timestamp (ISO8601)")
@click.option("--limit", type=int, default=100, help="Maximum number of events to return")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON instead of table")
def query(
    config: Path | None,
    source: str | None,
    event_type: str | None,
    level: str | None,
    since: str | None,
    until: str | None,
    limit: int,
    json_output: bool,
) -> None:
    """Query events from the Argus server."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)

    # Build query parameters
    params: dict[str, str | int] = {}
    if source is not None:
        params["source"] = source
    if event_type is not None:
        params["event_type"] = event_type
    if level is not None:
        params["level"] = level
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    params["limit"] = limit

    # Build URL and headers
    url = f"http://{cfg.server.host}:{cfg.server.port}/events"
    headers = {"X-API-Key": cfg.server.api_keys[0]}

    # Make request
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except httpx.ConnectError:
        click.echo("Error: Could not connect to server. Is it running?", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except httpx.RequestError as e:
        click.echo(f"Request failed: {e}", err=True)
        sys.exit(1)

    data = response.json()
    events = data.get("events", [])

    if not events:
        click.echo("No events found.")
        return

    # Output formatting
    if json_output:
        click.echo(json.dumps(events, indent=2))
    else:
        # Simple table format
        click.echo(f"{'ID':<6} {'Time':<20} {'Source':<15} {'Type':<20} {'Level':<8} Message")
        click.echo("-" * 100)
        for event in events:
            event_id = str(event.get("id", ""))
            timestamp = event.get("timestamp", "")[:19]  # Truncate milliseconds
            src = event.get("source", "")[:15]
            evt_type = event.get("event_type", "")[:20]
            lvl = event.get("level", "-")[:8]
            msg = event.get("message", "")[:40]
            click.echo(f"{event_id:<6} {timestamp:<20} {src:<15} {evt_type:<20} {lvl:<8} {msg}")

        click.echo(f"\nTotal: {len(events)} events")


@main.group()
def config() -> None:
    """Configuration management commands."""
    pass


@config.command("init")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing config file",
)
def config_init(force: bool) -> None:
    """Create default configuration file.

    Creates config at ~/.config/argus/config.toml with secure defaults.
    File permissions are set to 600 (user-only read/write) to protect API keys.
    """
    import secrets

    config_path = Path.home() / ".config" / "argus" / "config.toml"

    # Check if file exists
    if config_path.exists() and not force:
        click.echo(f"Config file already exists: {config_path}", err=True)
        click.echo("Use --force to overwrite", err=True)
        sys.exit(1)

    # Create parent directory
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate cryptographic random API key
    api_key = secrets.token_urlsafe(32)

    # Generate TOML template with defaults from Config model
    toml_content = f"""# Argus Configuration
#
# SECURITY: This file contains API keys in plaintext.
# File permissions are set to 600 (user-only read/write).
# DO NOT commit this file to version control.

[server]
# Bind address - 127.0.0.1 for localhost only (recommended)
host = "127.0.0.1"
# Server port
port = 8765
# API keys for authentication (automatically generated on init)
api_keys = ["{api_key}"]

[database]
# SQLite database path (tilde expansion supported)
path = "~/.local/share/argus/events.db"
# Journal mode for SQLite (WAL recommended for concurrency)
journal_mode = "WAL"

[retention]
# Delete events older than N days
retention_days = 30
# Daily cleanup time (HH:MM, 24-hour format)
cleanup_time = "03:00"
# Run VACUUM after cleanup to reclaim disk space
vacuum_after_cleanup = true

[limits]
# Maximum event size in KB
max_event_size_kb = 512
# Maximum events per batch POST
max_batch_size = 100

[web_ui]
# Enable web UI serving
enabled = true

[logging]
# Log level: debug, info, warn, error
level = "info"
# Log format: json, text
format = "json"
# Log output destination
output = "stdout"
"""

    # Write config file
    config_path.write_text(toml_content)

    # Set permissions to 600 (user-only read/write)
    os.chmod(config_path, 0o600)

    click.echo(f"Created config file: {config_path}")
    click.echo("File permissions set to 600 (user-only read/write)")
    click.echo("")
    click.echo("✓ Generated secure API key (cryptographic random)")
    click.echo("  API keys are stored in the config file under [server] section")


@main.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config file (default: ~/.config/argus/config.toml)",
)
def status(config: Path | None) -> None:
    """Check if Argus server is running."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)

    # Build URL and headers
    url = f"http://{cfg.server.host}:{cfg.server.port}/sources"
    headers = {"X-API-Key": cfg.server.api_keys[0]}

    # Check server status
    try:
        response = httpx.get(url, headers=headers, timeout=2)
        response.raise_for_status()

        # Server is running and responding
        click.echo("Argus server: Running")
        click.echo(f"  Address: http://{cfg.server.host}:{cfg.server.port}")
        click.echo("  Status: Healthy")

    except httpx.ConnectError:
        click.echo("Argus server: Stopped")
        click.echo(f"  Expected address: http://{cfg.server.host}:{cfg.server.port}")
        click.echo("  Start with: argus serve")
        sys.exit(1)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            click.echo("Argus server: Running (authentication failed)")
            click.echo(f"  Address: http://{cfg.server.host}:{cfg.server.port}")
            click.echo("  Error: API key in config may be incorrect")
            sys.exit(1)
        else:
            click.echo(f"Argus server: Error ({e.response.status_code})")
            sys.exit(1)

    except httpx.RequestError as e:
        click.echo(f"Argus server: Connection error - {e}", err=True)
        sys.exit(1)
