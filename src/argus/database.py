"""SQLite database layer with WAL mode."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Database:
    """SQLite database for event storage."""

    def __init__(self, db_path: str, journal_mode: str = "WAL") -> None:
        """Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file (tilde expansion handled by caller)
            journal_mode: SQLite journal mode (WAL, DELETE, TRUNCATE, etc.)
        """
        self.db_path = str(Path(db_path).expanduser().resolve())
        self._lock = threading.Lock()  # Thread safety for concurrent access

        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect and set journal mode
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute(f"PRAGMA journal_mode={journal_mode}")

        # Create schema if not exists
        self._create_schema()

        # Run migrations for schema evolution
        self._run_migrations()

    def _create_schema(self) -> None:
        """Create events table and indexes."""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message TEXT,
                    level TEXT,
                    data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for fast filtering
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON events(source)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_level ON events(level)")

            # Sessions table for session lifecycle tracking
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    project TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)

            # Agents table for agent/subagent tracking
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT,
                    session_id TEXT NOT NULL,
                    parent_agent_id TEXT,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    event_count INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)

            # Indexes for sessions and agents
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)")

    def _get_existing_columns(self, table: str) -> set[str]:
        """Get set of existing column names for a table.

        Args:
            table: Table name to inspect

        Returns:
            Set of column names
        """
        cursor = self.conn.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}

    def _run_migrations(self) -> None:
        """Run schema migrations for new columns and backfill data.

        Adds new columns to events table if they don't exist.
        Backfills session_id from JSON data blob where present.
        Each ALTER TABLE is atomic in SQLite, so partial failures are safe.
        """
        existing = self._get_existing_columns("events")

        # New columns for iteration 3: agent observability
        new_columns = [
            ("session_id", "TEXT"),
            ("hook", "TEXT"),
            ("tool_name", "TEXT"),
            ("tool_use_id", "TEXT"),
            ("status", "TEXT"),
            ("agent_id", "TEXT"),
        ]

        with self.conn:
            for col_name, col_type in new_columns:
                if col_name not in existing:
                    self.conn.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")

            # Create indexes for new columns (idempotent)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON events(session_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_hook ON events(hook)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON events(tool_name)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON events(status)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_id ON events(agent_id)")

            # Backfill session_id from JSON data blob (idempotent - only updates NULL)
            self.conn.execute("""
                UPDATE events
                SET session_id = json_extract(data, '$.session_id')
                WHERE session_id IS NULL
                  AND data IS NOT NULL
                  AND json_extract(data, '$.session_id') IS NOT NULL
            """)

    def get_journal_mode(self) -> str:
        """Get current journal mode (for verification).

        Returns:
            Journal mode string (e.g., 'wal')
        """
        cursor = self.conn.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        return str(result[0]).lower()

    def store_event(self, event: dict[str, Any]) -> int:
        """Store event in database.

        Args:
            event: Event dictionary with source, event_type, and optional fields.
                   New fields: session_id, hook, tool_name, tool_use_id, status, agent_id

        Returns:
            Event ID (auto-generated primary key)
        """
        # Generate timestamp if not provided
        timestamp = event.get("timestamp")
        if not timestamp:
            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Serialize data blob to JSON
        data_blob = None
        if "data" in event and event["data"] is not None:
            data_blob = json.dumps(event["data"])

        # Insert event with thread lock for concurrent safety
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO events (
                        source, event_type, timestamp, message, level, data,
                        session_id, hook, tool_name, tool_use_id, status, agent_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["source"],
                        event["event_type"],
                        timestamp,
                        event.get("message"),
                        event.get("level"),
                        data_blob,
                        event.get("session_id"),
                        event.get("hook"),
                        event.get("tool_name"),
                        event.get("tool_use_id"),
                        event.get("status"),
                        event.get("agent_id"),
                    ),
                )
                event_id = cursor.lastrowid
                if event_id is None:
                    raise RuntimeError("Failed to retrieve event ID after insertion")
                return event_id

    def query_events(
        self,
        source: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        session_id: str | None = None,
        hook: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query events with optional filtering.

        Args:
            source: Filter by source
            event_type: Filter by event type
            level: Filter by level
            since: Filter events after this timestamp (ISO8601)
            until: Filter events before this timestamp (ISO8601)
            limit: Maximum number of events to return (default 100)
            session_id: Filter by session ID
            hook: Filter by hook type
            tool_name: Filter by tool name
            status: Filter by status (success/failure/pending)
            agent_id: Filter by agent ID

        Returns:
            List of event dictionaries with deserialized data
        """
        # Build WHERE clause from safe, pre-defined fragments (not user input)
        where_clauses = []
        params: list[str | int] = []

        if source is not None:
            where_clauses.append("source = ?")
            params.append(source)
        if event_type is not None:
            where_clauses.append("event_type = ?")
            params.append(event_type)
        if level is not None:
            where_clauses.append("level = ?")
            params.append(level)
        if since is not None:
            where_clauses.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            where_clauses.append("timestamp <= ?")
            params.append(until)
        if session_id is not None:
            where_clauses.append("session_id = ?")
            params.append(session_id)
        if hook is not None:
            where_clauses.append("hook = ?")
            params.append(hook)
        if tool_name is not None:
            where_clauses.append("tool_name = ?")
            params.append(tool_name)
        if status is not None:
            where_clauses.append("status = ?")
            params.append(status)
        if agent_id is not None:
            where_clauses.append("agent_id = ?")
            params.append(agent_id)

        # Build query with parameterized values only
        base_query = (
            "SELECT id, source, event_type, timestamp, message, level, data, created_at, "
            "session_id, hook, tool_name, tool_use_id, status, agent_id FROM events"
        )

        if where_clauses:
            # Join pre-defined safe clauses (no user input in SQL structure)
            where_clause = " WHERE " + " AND ".join(where_clauses)
            query = base_query + where_clause + " ORDER BY timestamp DESC LIMIT ?"
        else:
            query = base_query + " ORDER BY timestamp DESC LIMIT ?"

        params.append(limit)

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()

        # Convert rows to dictionaries with JSON deserialization
        events = []
        for row in rows:
            event = {
                "id": row[0],
                "source": row[1],
                "event_type": row[2],
                "timestamp": row[3],
                "message": row[4],
                "level": row[5],
                "data": json.loads(row[6]) if row[6] else None,
                "created_at": row[7],
                "session_id": row[8],
                "hook": row[9],
                "tool_name": row[10],
                "tool_use_id": row[11],
                "status": row[12],
                "agent_id": row[13],
            }
            events.append(event)

        return events

    def get_sources(self) -> list[str]:
        """Get list of distinct sources from events.

        Returns:
            Sorted list of unique source strings
        """
        cursor = self.conn.execute("SELECT DISTINCT source FROM events ORDER BY source")
        rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

    def get_event_types(self) -> list[str]:
        """Get list of distinct event types from events.

        Returns:
            Sorted list of unique event_type strings
        """
        cursor = self.conn.execute("SELECT DISTINCT event_type FROM events ORDER BY event_type")
        rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

    def cleanup_old_events(self, retention_days: int, vacuum: bool = False) -> int:
        """Delete events older than retention threshold.

        Args:
            retention_days: Delete events older than N days
            vacuum: Run VACUUM after cleanup to reclaim disk space

        Returns:
            Number of events deleted
        """
        from datetime import timedelta

        # Calculate cutoff timestamp (events older than this will be deleted)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")

        # Delete old events with thread lock for concurrent safety
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    "DELETE FROM events WHERE timestamp < ?",
                    (cutoff_iso,),
                )
                deleted_count = cursor.rowcount

            # Optionally run VACUUM to reclaim disk space
            # Note: VACUUM cannot run inside a transaction, so execute separately
            if vacuum and deleted_count > 0:
                self.conn.execute("VACUUM")

            return deleted_count

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __del__(self) -> None:
        """Cleanup connection on deletion."""
        if hasattr(self, "conn"):
            self.conn.close()
