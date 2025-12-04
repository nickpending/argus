"""Pydantic models for events and configuration."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ServerConfig(BaseModel):
    """Server configuration.

    Security note: Default host 127.0.0.1 binds to localhost only for security.
    For local network access, set host to "0.0.0.0" in config.
    Network access is protected by API key authentication.
    """

    host: str = Field(default="127.0.0.1", description="Bind address")
    port: int = Field(default=8765, ge=1, le=65535, description="Server port")
    api_keys: list[str] = Field(..., min_length=1, description="Valid API keys for auth")

    @field_validator("api_keys")
    @classmethod
    def validate_api_keys_unique(cls, v: list[str]) -> list[str]:
        """Ensure API keys are unique."""
        if len(v) != len(set(v)):
            raise ValueError("API keys must be unique")
        return v


class DatabaseConfig(BaseModel):
    """Database configuration."""

    path: str = Field(default="~/.local/share/argus/events.db", description="SQLite database path")
    journal_mode: Literal["WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"] = Field(
        default="WAL", description="SQLite journal mode"
    )

    @field_validator("path")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand and normalize path, resolving symlinks."""
        # Expand tilde and resolve to absolute path
        expanded = Path(v).expanduser().resolve()
        return str(expanded)


class RetentionConfig(BaseModel):
    """Event retention configuration."""

    retention_days: int = Field(default=30, ge=1, description="Delete events older than N days")
    cleanup_time: str = Field(default="03:00", description="When to run cleanup (HH:MM)")
    vacuum_after_cleanup: bool = Field(default=True, description="Run VACUUM after cleanup")

    @field_validator("cleanup_time")
    @classmethod
    def validate_cleanup_time_format(cls, v: str) -> str:
        """Validate cleanup_time format is HH:MM."""
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("cleanup_time must be in HH:MM format")
        try:
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time values")
        except ValueError as e:
            raise ValueError("cleanup_time must be valid 24-hour time (HH:MM)") from e
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: Literal["debug", "info", "warn", "error"] = Field(
        default="info", description="Log level"
    )


class Config(BaseModel):
    """Root configuration model."""

    server: ServerConfig
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# Event models


class EventCreate(BaseModel):
    """Event creation model for POST input.

    Accepts events from observability producers (Sable, Prismis, etc).
    Timestamp auto-generated if not provided.
    """

    source: str = Field(
        ..., min_length=1, max_length=50, description="Producing application identifier"
    )
    event_type: str = Field(..., min_length=1, max_length=50, description="Event category")
    timestamp: str | None = Field(default=None, description="ISO8601 timestamp (UTC with Z suffix)")
    message: str | None = Field(
        default=None, max_length=2000, description="Human-readable description"
    )
    level: str | None = Field(default=None, description="Log level (debug/info/warn/error)")
    data: dict[str, Any] | None = Field(default=None, description="Arbitrary JSON data")

    # Agent observability fields (all optional for backwards compatibility)
    session_id: str | None = Field(default=None, description="Claude Code session identifier")
    hook: (
        Literal[
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "SessionStart",
            "SessionEnd",
            "SubagentStart",
            "SubagentStop",
            "UserPromptSubmit",
        ]
        | None
    ) = Field(default=None, description="Claude Code hook that fired")
    tool_name: str | None = Field(default=None, description="Tool invoked (Bash, Read, Edit, etc.)")
    tool_use_id: str | None = Field(
        default=None, description="Correlates PreToolUse/PostToolUse pairs"
    )
    status: Literal["success", "failure", "pending"] | None = Field(
        default=None, description="Event outcome"
    )
    agent_id: str | None = Field(default=None, description="Links event to agent instance")

    @field_validator("source")
    @classmethod
    def validate_source_pattern(cls, v: str) -> str:
        """Validate source matches pattern: lowercase start, alphanumeric + hyphens."""
        v = v.strip()
        if not v:
            raise ValueError("source must not be empty")
        if not re.match(r"^[a-z][a-z0-9-]*$", v):
            raise ValueError(
                "source must start with lowercase letter and contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type_pattern(cls, v: str) -> str:
        """Validate event_type matches pattern: lowercase start, alphanumeric + underscores/dots."""
        v = v.strip()
        if not v:
            raise ValueError("event_type must not be empty")
        if not re.match(r"^[a-z][a-z0-9_.]*$", v):
            raise ValueError(
                "event_type must start with lowercase letter and contain only lowercase letters, numbers, underscores, and dots"
            )
        return v

    @field_validator("level")
    @classmethod
    def validate_level_enum(cls, v: str | None) -> str | None:
        """Validate level is a valid log level if provided."""
        if v is None:
            return None
        v = v.strip().lower()
        valid_levels = {"debug", "info", "warn", "error"}
        if v not in valid_levels:
            raise ValueError(f"level must be one of {valid_levels} or None")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_format(cls, v: str | None) -> str | None:
        """Validate timestamp is ISO8601 format if provided."""
        if v is None:
            return None
        try:
            # Attempt to parse ISO8601 timestamp
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"timestamp must be valid ISO8601 format: {e}") from e
        return v


class Event(BaseModel):
    """Event model for database output.

    Includes server-generated fields (id, timestamp).
    """

    id: int = Field(..., description="Database-generated event ID")
    source: str = Field(..., description="Producing application identifier")
    event_type: str = Field(..., description="Event category")
    timestamp: str = Field(..., description="ISO8601 timestamp (UTC with Z suffix)")
    message: str | None = Field(default=None, description="Human-readable description")
    level: str | None = Field(default=None, description="Log level")
    data: dict[str, Any] | None = Field(default=None, description="Arbitrary JSON data")
