# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Argus is a centralized local-network observability platform for development tools. It solves async batching problems through synchronous HTTP event capture, real-time WebSocket streaming, and programmatic querying via SQLite.

## Commands

```bash
# Python Backend
uv sync                                    # Install dependencies
uv sync --all-extras                       # Install with dev dependencies
uv run pytest                              # Run all tests
uv run pytest tests/integration/test_events_api.py -v  # Run single test file
uv run pytest -k "test_name"               # Run specific test
uv run ruff check .                        # Lint
uv run ruff format .                       # Format
uv run mypy src/argus                      # Type check

# Run server
argus serve                                # Start server (default port 8765)
argus config init                          # Initialize config
argus status                               # Check server status

# Svelte Dashboard (web-svelte/)
pnpm install                               # Install dependencies
pnpm dev                                   # Dev server
pnpm build                                 # Production build
pnpm check                                 # TypeScript/Svelte check
```

## Architecture

### Backend (Python/FastAPI)

```
src/argus/
├── server.py      # FastAPI app, routes, lifespan, serves web UI
├── database.py    # SQLite layer with WAL mode, indexed queries
├── websocket.py   # WebSocket manager, subscription filters, broadcast
├── models.py      # Pydantic models (Event, Config, etc.)
├── config.py      # TOML config loading from ~/.config/argus/
└── cli.py         # Click CLI (serve, query, config, status)
```

**Key patterns:**
- App state injection via `app.state` for `config`, `db`, `ws_manager`
- Synchronous POST blocks until SQLite commit (WAL mode for durability)
- WebSocket broadcasts filtered events to subscribed clients
- API key auth via `X-API-Key` header

### Dashboard (Svelte 5 + TypeScript)

```
web-svelte/src/
├── App.svelte           # Main app, WebSocket connection, state
├── lib/stores/          # Svelte stores for reactive state
└── lib/components/
    ├── CombinedTimeline.svelte  # Primary visualization
    ├── AgentSwimlanes.svelte    # Agent activity lanes
    ├── SessionTree.svelte       # Hierarchical session view
    ├── EventTable.svelte        # Event list with filtering
    ├── DetailPanel.svelte       # Event detail inspection
    ├── FilterBar.svelte         # Source/type/level filters
    └── StatusBadge.svelte       # Status indicators
```

### Tests

```
tests/
├── conftest.py                  # Fixtures: test_config, test_db, client
├── integration/
│   ├── test_events_api.py       # POST /events tests
│   ├── test_query_api.py        # GET /events query tests
│   └── test_websocket.py        # WebSocket protocol tests
└── unit/
    └── test_config.py           # Config loading tests
```

**Test fixtures use app state injection** - `app.state.config`, `app.state.db`, `app.state.ws_manager` are replaced with test instances. TestClient bypasses lifespan to use fixtures.

## Event Schema

```json
{
  "source": "string",       // Required: service name
  "event_type": "string",   // Required: event category
  "message": "string",      // Optional: human-readable
  "level": "string",        // Optional: debug/info/warn/error
  "timestamp": "string",    // Optional: ISO8601 with Z
  "data": {}                // Optional: arbitrary JSON
}
```

## Config Location

`~/.config/argus/config.toml` - API keys, database path, retention settings. Created via `argus config init`.

## Web UI Directories

- `web-svelte/` - Active Svelte 5 dashboard (use this)
- `web-vanilla/` - Legacy vanilla JS (deprecated)
- `web/` - Static assets served by FastAPI
