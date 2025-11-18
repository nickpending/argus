# Argus

Centralized local-network observability platform for development tools.

## Features

- Synchronous HTTP POST event capture
- Real-time WebSocket event streaming
- SQLite storage with WAL mode
- Programmatic query API
- Web UI for event visualization

## Installation

```bash
uv sync
```

## Usage

```bash
# Start server
uv run argus serve

# Query events
uv run argus query --source <source> --limit 10
```

## Development

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Lint code
uv run ruff check .

# Type check
uv run mypy src/argus
```
