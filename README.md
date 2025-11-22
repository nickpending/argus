# Argus

<div align="center">

  **Centralized local-network observability platform for development tools**

  [![Status](https://img.shields.io/badge/Status-Active-green?style=flat)](#status-active)
  [![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat)](https://python.org)
  [![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

**Argus** solves the async batching problem in agent frameworks through synchronous HTTP event capture, provides real-time WebSocket streaming, and offers programmatic querying. Shared infrastructure for Sable, Prismis, and future development tools - no per-project duplication.

Think of it as having a single pane of glass for all your local development tool activity.

## Status: Active

**This is production-ready software in active daily use.** All 29 iteration 1 tasks shipped. Core observability platform complete with real-time streaming, query API, web UI, and CLI tools.

## ✨ Features

- 🔄 **Synchronous Event Capture** - POST blocks until event stored (solves async batching problem)
- ⚡ **Real-Time Streaming** - WebSocket broadcasting with subscription filters
- 💾 **SQLite Storage** - WAL mode for concurrent access, indexed queries
- 🔍 **Query API** - Programmatic filtering by source, event type, level, time range
- 🎨 **Cyberpunk Web UI** - Dark theme with real-time event visualization
- 🔐 **API Key Authentication** - Simple bearer token auth for all endpoints
- 📊 **Discovery Endpoints** - Auto-detect available sources and event types
- 🗑️ **Automatic Retention** - Configurable cleanup job with VACUUM support
- 🛠️ **CLI Tools** - Serve, query, config, and status commands

## 🎬 Quick Start

```bash
# Install dependencies
uv sync

# Initialize configuration
uv run argus config init
# Edit ~/.config/argus/config.toml - set your API key

# Start server
uv run argus serve
# Server running on http://127.0.0.1:8765

# Open web UI
open http://127.0.0.1:8765
```

**Sending Your First Event:**

```bash
# From command line
curl -X POST http://127.0.0.1:8765/events \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "my-app",
    "event_type": "startup",
    "message": "Application started",
    "level": "info",
    "data": {"version": "1.0.0"}
  }'

# Watch events appear in real-time in web UI
```

That's it! You're observing events.

## 📡 Sending Data to Argus

### HTTP POST Endpoint

**Endpoint:** `POST /events`
**Authentication:** `X-API-Key` header
**Latency:** Sub-100ms POST-to-broadcast on localhost

**Event Schema:**

```json
{
  "source": "string",       // Required: Service name (e.g., "sable", "prismis")
  "event_type": "string",   // Required: Event type (e.g., "thinking", "error")
  "message": "string",      // Optional: Human-readable message
  "level": "string",        // Optional: "debug", "info", "warn", "error"
  "timestamp": "string",    // Optional: ISO8601 with Z (server generates if missing)
  "data": {}                // Optional: Arbitrary JSON data
}
```

**Response:**

```json
{
  "status": "captured",
  "event_id": 123
}
```

### Python Integration

```python
import httpx
from datetime import datetime, UTC

class ArgusClient:
    def __init__(self, host="http://127.0.0.1:8765", api_key=None):
        self.host = host
        self.api_key = api_key
        self.client = httpx.Client()

    def post_event(self, source, event_type, message=None, level=None, data=None):
        """Post event to Argus - blocks until captured."""
        event = {
            "source": source,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z")
        }

        if message:
            event["message"] = message
        if level:
            event["level"] = level
        if data:
            event["data"] = data

        response = self.client.post(
            f"{self.host}/events",
            headers={"X-API-Key": self.api_key},
            json=event,
            timeout=5.0
        )
        response.raise_for_status()
        return response.json()["event_id"]

# Usage
argus = ArgusClient(api_key="your-api-key")
event_id = argus.post_event(
    source="sable",
    event_type="thinking",
    message="Analyzing user request",
    level="debug",
    data={"tokens": 1234, "duration_ms": 567}
)
```

### JavaScript Integration

```javascript
class ArgusClient {
  constructor(host = "http://127.0.0.1:8765", apiKey) {
    this.host = host;
    this.apiKey = apiKey;
  }

  async postEvent(source, eventType, { message, level, data } = {}) {
    const event = {
      source,
      event_type: eventType,
      timestamp: new Date().toISOString()
    };

    if (message) event.message = message;
    if (level) event.level = level;
    if (data) event.data = data;

    const response = await fetch(`${this.host}/events`, {
      method: 'POST',
      headers: {
        'X-API-Key': this.apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(event)
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }

    const result = await response.json();
    return result.event_id;
  }
}

// Usage
const argus = new ArgusClient("http://127.0.0.1:8765", "your-api-key");
const eventId = await argus.postEvent("prismis", "article_saved", {
  message: "Article saved to database",
  level: "info",
  data: { article_id: "abc123", priority: "high" }
});
```

### Why Synchronous POST?

**Problem:** Async event batching in agent frameworks can lose events if the process crashes before batch flushes.

**Solution:** Argus POST blocks until the event is committed to SQLite with WAL mode. When POST returns success, the event is durable.

This solves observability gaps in crash scenarios while maintaining <100ms latency on localhost.

## 🎮 How It Works

### Architecture

```
Producer (Sable/Prismis)
        │
        ├─► POST /events ──► Validate API key ──► SQLite (WAL mode)
        │                                              │
        │                                              ├─► Broadcast to WebSocket clients
        │                                              │         │
WebSocket Client ◄─── Filter by source/type/level ◄───┘         │
        │                                                        │
    Web UI ◄─────────────────────────────────────────────────────┘
        │
    Query API ◄─── GET /events?source=sable&limit=100
```

**Data Flow:**
1. Producer POSTs event with API key
2. Server validates schema and API key
3. Event stored in SQLite (blocks until committed)
4. Event broadcast to all authenticated WebSocket clients with matching filters
5. Web UI receives and displays event in real-time (<100ms latency)
6. Historical queries available via GET /events

### Components

- **FastAPI Server** - Single monolithic application for tight integration
- **SQLite WAL** - Concurrent reads during writes, indexed on source/event_type/timestamp/level
- **WebSocket Manager** - Maintains client connections with subscription filters
- **Web UI** - Vanilla JS with cyberpunk aesthetic, client-side filtering
- **CLI** - Server control, config management, query interface

## 🔧 Installation

### Prerequisites

- **Python 3.11+**
- **uv package manager** - [Install here](https://github.com/astral-sh/uv)

### Install from Source

```bash
git clone https://github.com/nickpending/argus.git
cd argus
uv sync
```

### Configuration

```bash
# Initialize default config
uv run argus config init

# Edit configuration
vim ~/.config/argus/config.toml
```

**Configuration Structure:**

```toml
[server]
host = "127.0.0.1"  # Local network only (change to 0.0.0.0 for network access)
port = 8765
api_keys = ["your-api-key-here"]  # Add multiple keys as needed

[database]
path = "~/.local/share/argus/events.db"

[retention]
days = 30                    # Keep events for 30 days
cleanup_time = "03:00"       # Daily cleanup at 3 AM
vacuum_after_cleanup = true  # Reclaim disk space

[limits]
max_payload_size_kb = 512
max_query_limit = 1000

[web_ui]
title = "Argus Observability"

[logging]
level = "info"
```

**Security Note:** Config file is created with 600 permissions (user-only read/write). Never commit `config.toml` to git.

## 🚀 Usage Patterns

### Starting the Server

```bash
# Default config (~/.config/argus/config.toml)
uv run argus serve

# Custom config location
uv run argus serve --config /path/to/config.toml

# Override host/port
uv run argus serve --host 0.0.0.0 --port 9000
```

### Querying Events

```bash
# CLI queries
uv run argus query --source sable --limit 10
uv run argus query --event-type error --level error
uv run argus query --since 2025-11-20T00:00:00Z --json

# HTTP API queries
curl "http://127.0.0.1:8765/events?source=sable&limit=10" \
  -H "X-API-Key: your-api-key"

# Discovery endpoints
curl http://127.0.0.1:8765/sources -H "X-API-Key: your-api-key"
curl http://127.0.0.1:8765/event-types -H "X-API-Key: your-api-key"
```

### WebSocket Streaming

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://127.0.0.1:8765/ws');

// Authenticate
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'auth',
    api_key: 'your-api-key'
  }));
};

// Subscribe with filters
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'auth_result' && msg.status === 'success') {
    // Authenticated - subscribe to events
    ws.send(JSON.stringify({
      type: 'subscribe',
      filters: {
        source: 'sable',          // Optional: filter by source
        event_type: 'thinking',   // Optional: filter by type
        level: 'info'             // Optional: filter by level
      }
    }));
  }

  if (msg.type === 'event') {
    console.log('Received event:', msg.event);
  }
};
```

**WebSocket Protocol:**

```json
// Auth message
{"type": "auth", "api_key": "your-api-key"}

// Auth response
{"type": "auth_result", "status": "success"}

// Subscribe message (empty filters = all events)
{"type": "subscribe", "filters": {"source": "sable"}}

// Subscribe response
{"type": "subscribe_result", "status": "subscribed", "active_filters": {...}}

// Event broadcast
{"type": "event", "event": {
  "id": 123,
  "source": "sable",
  "event_type": "thinking",
  "message": "Processing request",
  "level": "debug",
  "timestamp": "2025-11-20T12:34:56Z",
  "data": {}
}}

// Ping (keepalive)
{"type": "ping"}

// Pong response
{"type": "pong"}
```

### Server Status

```bash
# Check if server is running
uv run argus status

# Output:
# ✓ Argus server is running
# URL: http://127.0.0.1:8765
# API Version: 1.0.0
```

## 📊 API Reference

### POST /events

Capture event synchronously (blocks until stored).

**Headers:**
- `X-API-Key: string` (required)
- `Content-Type: application/json`

**Body:**
```json
{
  "source": "string",       // Required
  "event_type": "string",   // Required
  "message": "string",      // Optional
  "level": "string",        // Optional: debug, info, warn, error
  "timestamp": "string",    // Optional: ISO8601 with Z
  "data": {}                // Optional: JSON object
}
```

**Response:** `200 OK`
```json
{
  "status": "captured",
  "event_id": 123
}
```

**Errors:**
- `401` - Missing or invalid API key
- `422` - Invalid schema (missing required fields)
- `500` - Database write failure

### GET /events

Query historical events with filtering.

**Headers:**
- `X-API-Key: string` (required)

**Query Parameters:**
- `source` - Filter by source (exact match)
- `event_type` - Filter by event type (exact match)
- `level` - Filter by level (exact match)
- `since` - ISO8601 timestamp (events after this time)
- `until` - ISO8601 timestamp (events before this time)
- `limit` - Max results (default: 100, max: 1000)

**Response:** `200 OK`
```json
{
  "events": [
    {
      "id": 123,
      "source": "sable",
      "event_type": "thinking",
      "message": "Processing request",
      "level": "debug",
      "timestamp": "2025-11-20T12:34:56Z",
      "data": {}
    }
  ]
}
```

### GET /sources

List all unique sources in database.

**Headers:**
- `X-API-Key: string` (required)

**Response:** `200 OK`
```json
{
  "sources": ["sable", "prismis", "argus"]
}
```

### GET /event-types

List all unique event types in database.

**Headers:**
- `X-API-Key: string` (required)

**Response:** `200 OK`
```json
{
  "event_types": ["thinking", "error", "startup", "shutdown"]
}
```

### WebSocket /ws

Real-time event streaming with subscription filters.

See [WebSocket Streaming](#websocket-streaming) section for protocol details.

## 🧪 Development

### Running Tests

```bash
# Install dev dependencies
uv sync --all-extras

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/argus --cov-report=term-missing

# Run specific test file
uv run pytest tests/integration/test_events_api.py -v
```

### Code Quality

```bash
# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Type check
uv run mypy src/argus
```

### Project Structure

```
argus/
├── src/argus/           # Python source
│   ├── cli.py           # CLI commands (serve, query, config, status)
│   ├── server.py        # FastAPI application
│   ├── database.py      # SQLite layer with WAL mode
│   ├── websocket.py     # WebSocket manager
│   ├── config.py        # Configuration loading
│   └── models.py        # Pydantic models
├── web/                 # Web UI (vanilla JS)
│   ├── index.html       # HTML structure
│   ├── styles.css       # Cyberpunk theme
│   └── app.js           # WebSocket client, event rendering
├── tests/               # Pytest suite
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
├── .workflow/           # Momentum workflow artifacts
└── pyproject.toml       # uv configuration
```

## 🎯 Design Decisions

### Why SQLite?

- **WAL Mode** - Concurrent reads during writes (critical for real-time queries)
- **Local-First** - No network database complexity for local dev tools
- **Indexed Queries** - Fast filtering on source/event_type/timestamp/level
- **Durability** - ACID guarantees with synchronous POST
- **Simplicity** - Single file, no separate database process

### Why Synchronous POST?

Async batching in agent frameworks can lose events on crash. Synchronous POST blocks until event is committed to disk (WAL mode), guaranteeing durability while maintaining <100ms latency on localhost.

### Why Monolithic FastAPI?

Tight integration between HTTP POST, WebSocket broadcast, and database ensures low-latency real-time streaming. Microservices would add network hops and complexity without benefits for local-network deployment.

### Why No TLS Initially?

Local network deployment (127.0.0.1 or private network). TLS adds setup complexity for minimal security benefit. Can be added via reverse proxy if needed.

## 🔐 Security Considerations

- **API Keys in Plaintext** - Config file has 600 permissions, lives in XDG config directory
- **No Per-Source Keys** - Single API key for v1 (per-source keys future feature)
- **Local Network Only** - Default host 127.0.0.1 prevents external access
- **Payload Size Limit** - 512KB default prevents memory exhaustion
- **Query Limit** - 1000 events max per query prevents DOS
- **XSS Protection** - Web UI escapes all event fields (source, event_type, message)

## 🤝 Contributing

Argus is built through momentum workflow - we ship improvements iteratively. See [TASKS.md](.workflow/artifacts/TASKS.md) for current iteration status.

Areas where we'd love contributions:
- Additional client libraries (Rust, Go, Ruby)
- Grafana datasource plugin
- Prometheus metrics exporter
- Additional web UI themes
- Performance optimizations for high-volume scenarios

## 📈 Why Argus?

**The Problem:** Development tools (Sable, Prismis, etc.) each implement their own logging/observability. This creates duplication, inconsistent interfaces, and difficulty correlating events across tools.

**The Solution:** Argus provides shared observability infrastructure. Tools POST events to a single service, query via unified API, and stream via WebSocket. One web UI, one query interface, one place to debug.

**The Philosophy:** Observability infrastructure should be invisible until you need it. POST events, query when debugging, stream when monitoring - that's it.

## 📄 License

[MIT](LICENSE) - Use it, fork it, make it better.

## 🙏 Acknowledgments

Built for and with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- [SQLite](https://sqlite.org/) - Reliable embedded database
- [Momentum](https://github.com/nickpending/momentum) - Development workflow system

---

<div align="center">

  **Stop implementing logging in every tool. Start observing everything.**

  [Get Started](#-quick-start)

</div>
