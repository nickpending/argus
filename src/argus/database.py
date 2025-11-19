"""SQLite database layer with WAL mode."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Database:
    """SQLite database with WAL mode for event storage."""

    def __init__(self, db_path: str) -> None:
        """Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file (tilde expansion handled by caller)
        """
        self.db_path = str(Path(db_path).expanduser().resolve())

        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect and enable WAL mode
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")

        # Create schema if not exists
        self._create_schema()

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
            event: Event dictionary with source, event_type, and optional fields

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

        # Insert event and commit before returning (durability guarantee)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO events (source, event_type, timestamp, message, level, data)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event["source"],
                    event["event_type"],
                    timestamp,
                    event.get("message"),
                    event.get("level"),
                    data_blob,
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
    ) -> list[dict[str, Any]]:
        """Query events with optional filtering.

        Args:
            source: Filter by source
            event_type: Filter by event type
            level: Filter by level
            since: Filter events after this timestamp (ISO8601)
            until: Filter events before this timestamp (ISO8601)
            limit: Maximum number of events to return (default 100)

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

        # Build query with parameterized values only
        base_query = (
            "SELECT id, source, event_type, timestamp, message, level, data, created_at FROM events"
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
            }
            events.append(event)

        return events

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __del__(self) -> None:
        """Cleanup connection on deletion."""
        if hasattr(self, "conn"):
            self.conn.close()
