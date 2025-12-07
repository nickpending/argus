"""WebSocket server and connection management."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class ClientConnection:
    """Represents a WebSocket client connection with auth state and filters.

    Attributes:
        websocket: FastAPI WebSocket connection
        authenticated: Whether client has passed API key validation
        filters: Subscription filters (empty dict = receive all events)
    """

    websocket: WebSocket
    authenticated: bool = False
    filters: dict[str, Any] = field(default_factory=dict)

    def matches_event(self, event: dict[str, Any]) -> bool:
        """Check if event matches this client's subscription filters.

        Args:
            event: Event dict with source, event_type, level, etc.

        Returns:
            True if event matches filters (or no filters set), False otherwise

        Filter logic:
            - Empty filters dict = match all events
            - Multiple filters use AND logic (all must match)
            - Uses exact string comparison for filter values
        """
        if not self.authenticated:
            return False

        if not self.filters:
            return True  # No filters = receive all events

        # Check all filters with AND logic
        for key, value in self.filters.items():
            if event.get(key) != value:
                return False

        return True


class WebSocketManager:
    """Manages WebSocket connections for event broadcasting.

    Handles connection tracking, authentication state, subscription filters,
    and event broadcasting with filter matching.

    Thread safety: Uses asyncio.Lock for connection list modifications.
    """

    def __init__(self) -> None:
        """Initialize WebSocket manager with empty connection list."""
        self.connections: list[ClientConnection] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> ClientConnection:
        """Add new WebSocket connection to manager.

        Args:
            websocket: FastAPI WebSocket connection

        Returns:
            ClientConnection object for this connection
        """
        async with self._lock:
            client = ClientConnection(websocket=websocket)
            self.connections.append(client)
            return client

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection from manager.

        Args:
            websocket: FastAPI WebSocket connection to remove
        """
        async with self._lock:
            self.connections = [conn for conn in self.connections if conn.websocket != websocket]

    async def authenticate(self, websocket: WebSocket) -> None:
        """Mark connection as authenticated.

        Args:
            websocket: FastAPI WebSocket connection to authenticate
        """
        async with self._lock:
            for conn in self.connections:
                if conn.websocket == websocket:
                    conn.authenticated = True
                    break

    async def update_filters(self, websocket: WebSocket, filters: dict[str, Any]) -> None:
        """Update subscription filters for a connection.

        Args:
            websocket: FastAPI WebSocket connection
            filters: New filter dict (replaces existing filters)
        """
        async with self._lock:
            for conn in self.connections:
                if conn.websocket == websocket:
                    conn.filters = filters
                    break

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Broadcast event to all matching WebSocket clients.

        Sends event to clients where:
        - Client is authenticated
        - Event matches client's subscription filters (or no filters set)

        Disconnected clients are removed automatically on send failure.

        Args:
            event: Event dict to broadcast (must include source, event_type)
        """
        # Create snapshot of connections to iterate
        async with self._lock:
            connections_snapshot = list(self.connections)

        disconnected: list[ClientConnection] = []

        # Send to matching clients (without holding lock)
        for conn in connections_snapshot:
            if conn.matches_event(event):
                try:
                    await conn.websocket.send_json({"type": "event", "event": event})
                except Exception:
                    # Client disconnected or send failed
                    disconnected.append(conn)

        # Remove disconnected clients
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.connections:
                        self.connections.remove(conn)

    async def broadcast_lifecycle(self, message_type: str, payload: dict[str, Any]) -> None:
        """Broadcast lifecycle event to all authenticated clients.

        Unlike broadcast(), this sends to ALL authenticated clients without filter matching.
        Used for session/agent lifecycle events that update the UI tree.

        Args:
            message_type: Message type (e.g., 'session_started', 'agent_completed')
            payload: Full session or agent object
        """
        async with self._lock:
            connections_snapshot = list(self.connections)

        disconnected: list[ClientConnection] = []

        for conn in connections_snapshot:
            if conn.authenticated:
                try:
                    await conn.websocket.send_json({"type": message_type, "payload": payload})
                except Exception:
                    disconnected.append(conn)

        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.connections:
                        self.connections.remove(conn)
