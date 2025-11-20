"""FastAPI server and endpoints."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.staticfiles import StaticFiles

from argus.config import load_config
from argus.database import Database
from argus.models import EventCreate
from argus.websocket import WebSocketManager


async def cleanup_task(
    db: Database, retention_days: int, cleanup_time_str: str, vacuum: bool
) -> None:
    """Background task to cleanup old events daily at scheduled time.

    Args:
        db: Database instance
        retention_days: Delete events older than N days
        cleanup_time_str: Time to run cleanup (HH:MM format)
        vacuum: Run VACUUM after cleanup
    """
    # Parse cleanup time (HH:MM)
    hour, minute = map(int, cleanup_time_str.split(":"))
    cleanup_time_obj = time(hour, minute)

    while True:
        # Calculate next cleanup time
        now = datetime.now(UTC)
        today_cleanup = datetime.combine(now.date(), cleanup_time_obj, tzinfo=UTC)

        if now >= today_cleanup:
            # Today's cleanup time has passed, schedule for tomorrow
            next_cleanup = today_cleanup + timedelta(days=1)
        else:
            # Today's cleanup time hasn't happened yet
            next_cleanup = today_cleanup

        # Sleep until cleanup time
        sleep_seconds = (next_cleanup - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        # Run cleanup
        try:
            deleted = db.cleanup_old_events(retention_days, vacuum)
            print(f"Cleanup completed: deleted {deleted} events (retention={retention_days} days)")
        except Exception as e:
            # Log error but don't crash the task
            print(f"Cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Manage application lifecycle - startup and shutdown."""
    # STARTUP PHASE
    config = load_config()

    # Initialize database
    db_path = config.database.path
    db = Database(db_path)

    # Initialize WebSocket manager
    ws_manager = WebSocketManager()

    # Launch cleanup task in background
    cleanup_task_handle = asyncio.create_task(
        cleanup_task(
            db=db,
            retention_days=config.retention.retention_days,
            cleanup_time_str=config.retention.cleanup_time,
            vacuum=config.retention.vacuum_after_cleanup,
        )
    )

    # Store in app state for endpoint access
    app.state.config = config
    app.state.db = db
    app.state.ws_manager = ws_manager
    app.state.cleanup_task = cleanup_task_handle

    yield  # Application runs here

    # SHUTDOWN PHASE
    # Cancel cleanup task gracefully
    cleanup_task_handle.cancel()
    try:
        await cleanup_task_handle
    except asyncio.CancelledError:
        pass  # Expected when cancelling

    db.close()


# Create FastAPI application
app = FastAPI(
    title="Argus Event Observability",
    description="Local-network observability platform for development tools",
    version="0.1.0",
    lifespan=lifespan,
)


# API key validation dependency
async def verify_api_key(
    x_api_key: str = Header(..., description="API key for authentication"),
) -> str:
    """Validate API key from X-API-Key header.

    Args:
        x_api_key: API key from request header

    Returns:
        Validated API key

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    # Access config from app state - get current app instance
    # Note: This dependency is called within request context, so we can't access app.state directly
    # We'll need to pass Request to get app.state
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key validation requires Request context",
    )


# POST /events endpoint - Event ingestion with API key auth and database storage
@app.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    request: Request,
    x_api_key: str = Header(..., description="API key for authentication"),
) -> dict[str, Any]:
    """Create event in database with API key authentication.

    Args:
        event: Event data (source, event_type required)
        request: FastAPI request for app.state access
        x_api_key: API key from X-API-Key header

    Returns:
        Success response with event_id

    Raises:
        HTTPException: 401 if API key invalid, 422 if schema invalid (automatic)
    """
    # Validate API key
    config = request.app.state.config
    if x_api_key not in config.server.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Convert EventCreate to dict and generate timestamp if missing
    event_dict = event.model_dump()
    if event_dict.get("timestamp") is None:
        event_dict["timestamp"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    # Store in database
    db = request.app.state.db
    event_id = db.store_event(event_dict)

    # Broadcast to WebSocket clients (non-blocking)
    ws_manager = request.app.state.ws_manager
    # Construct complete event dict with ID for broadcast
    broadcast_event = {
        "id": event_id,
        "source": event_dict["source"],
        "event_type": event_dict["event_type"],
        "timestamp": event_dict["timestamp"],
        "message": event_dict.get("message"),
        "level": event_dict.get("level"),
        "data": event_dict.get("data"),
    }
    # Broadcast in background task to avoid blocking response
    asyncio.create_task(ws_manager.broadcast(broadcast_event))

    # Return success response
    return {"status": "captured", "event_id": event_id}


# GET /events endpoint - Query historical events with filtering
@app.get("/events")
async def query_events(
    request: Request,
    x_api_key: str = Header(..., description="API key for authentication"),
    source: str | None = None,
    event_type: str | None = None,
    level: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Query events with optional filtering.

    Args:
        request: FastAPI request for app.state access
        x_api_key: API key from X-API-Key header
        source: Filter by source
        event_type: Filter by event type
        level: Filter by level
        since: Filter events after this timestamp (ISO8601)
        until: Filter events before this timestamp (ISO8601)
        limit: Maximum number of events to return (default 100, max 1000)

    Returns:
        JSON response with events list

    Raises:
        HTTPException: 401 if API key invalid, 400 if limit exceeds max
    """
    # Validate API key
    config = request.app.state.config
    if x_api_key not in config.server.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Enforce max limit of 1000
    if limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit cannot exceed 1000",
        )

    # Query database with filters
    db = request.app.state.db
    events = db.query_events(
        source=source,
        event_type=event_type,
        level=level,
        since=since,
        until=until,
        limit=limit,
    )

    return {"events": events}


# GET /sources endpoint - Discovery endpoint for available sources
@app.get("/sources")
async def get_sources(
    request: Request,
    x_api_key: str = Header(..., description="API key for authentication"),
) -> dict[str, Any]:
    """Get list of distinct sources from events.

    Args:
        request: FastAPI request for app.state access
        x_api_key: API key from X-API-Key header

    Returns:
        JSON response with sources list

    Raises:
        HTTPException: 401 if API key invalid
    """
    # Validate API key
    config = request.app.state.config
    if x_api_key not in config.server.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Get distinct sources from database
    db = request.app.state.db
    sources = db.get_sources()

    return {"sources": sources}


# GET /event-types endpoint - Discovery endpoint for available event types
@app.get("/event-types")
async def get_event_types(
    request: Request,
    x_api_key: str = Header(..., description="API key for authentication"),
) -> dict[str, Any]:
    """Get list of distinct event types from events.

    Args:
        request: FastAPI request for app.state access
        x_api_key: API key from X-API-Key header

    Returns:
        JSON response with event_types list

    Raises:
        HTTPException: 401 if API key invalid
    """
    # Validate API key
    config = request.app.state.config
    if x_api_key not in config.server.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Get distinct event types from database
    db = request.app.state.db
    event_types = db.get_event_types()

    return {"event_types": event_types}


# WebSocket /ws endpoint - Real-time event streaming with auth and filtering
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time event streaming.

    Protocol:
        1. Client sends auth message: {"type": "auth", "api_key": "..."}
        2. Server validates and responds with {"type": "auth_result", ...}
        3. Client sends subscribe message: {"type": "subscribe", "filters": {...}}
        4. Server streams events: {"type": "event", "event": {...}}

    Args:
        websocket: FastAPI WebSocket connection
    """
    await websocket.accept()

    # Add connection to manager
    ws_manager: WebSocketManager = websocket.app.state.ws_manager
    await ws_manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            message = await websocket.receive_json()
            message_type = message.get("type")

            if message_type == "auth":
                # Validate API key
                api_key = message.get("api_key")
                config = websocket.app.state.config

                if api_key and api_key in config.server.api_keys:
                    # Authentication successful
                    await ws_manager.authenticate(websocket)
                    await websocket.send_json(
                        {
                            "type": "auth_result",
                            "status": "success",
                            "message": "Authenticated successfully",
                        }
                    )
                else:
                    # Authentication failed
                    await websocket.send_json(
                        {
                            "type": "auth_result",
                            "status": "error",
                            "message": "Invalid API key",
                        }
                    )
                    await websocket.close(code=1008)  # Policy violation
                    break

            elif message_type == "subscribe":
                # Update subscription filters
                filters = message.get("filters", {})
                await ws_manager.update_filters(websocket, filters)
                await websocket.send_json(
                    {
                        "type": "subscribe_result",
                        "status": "success",
                        "active_filters": filters,
                    }
                )

            elif message_type == "ping":
                # Respond to ping with pong
                await websocket.send_json({"type": "pong"})

            else:
                # Unknown message type
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unknown message type: {message_type}",
                    }
                )

    except WebSocketDisconnect:
        # Client disconnected normally
        pass
    except Exception as e:
        # Log error and disconnect client
        # Note: In production, use proper logging instead of pass
        print(f"WebSocket error: {e}")
    finally:
        # Remove connection from manager
        await ws_manager.disconnect(websocket)


# Mount static files for web UI (serves at /)
# Note: Must be mounted AFTER API routes to avoid shadowing /events endpoint
web_dir = Path(__file__).parent.parent.parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
