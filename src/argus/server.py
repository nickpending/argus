"""FastAPI server and endpoints."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.staticfiles import StaticFiles

from argus.config import load_config
from argus.database import Database
from argus.models import (
    AgentListResponse,
    EventCreate,
    EventListResponse,
    SessionListResponse,
)
from argus.websocket import WebSocketManager

# Configure logging
logger = logging.getLogger(__name__)


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
            logger.info(
                "Cleanup completed: deleted %d events (retention=%d days)", deleted, retention_days
            )
        except Exception as e:
            # Log error but don't crash the task
            logger.error("Cleanup error: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Manage application lifecycle - startup and shutdown."""
    # STARTUP PHASE
    config = load_config()

    # Initialize database
    db_path = config.database.path
    db = Database(db_path, journal_mode=config.database.journal_mode)

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
    version="0.1.2",
    lifespan=lifespan,
)


# API key validation dependencies
async def verify_api_key(
    request: Request,
    x_api_key: str = Header(..., description="API key for authentication"),
) -> str:
    """Validate API key from X-API-Key header (required).

    Args:
        request: FastAPI request for app.state access
        x_api_key: API key from request header

    Returns:
        Validated API key

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    config = request.app.state.config
    if x_api_key not in config.server.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key


async def verify_optional_api_key(
    request: Request,
    x_api_key: str | None = Header(
        None, description="API key for authentication (optional for web UI)"
    ),
) -> str | None:
    """Validate API key if provided (optional for same-origin web UI).

    Args:
        request: FastAPI request for app.state access
        x_api_key: API key from request header (optional)

    Returns:
        Validated API key or None if not provided

    Raises:
        HTTPException: 401 if API key provided but invalid
    """
    if x_api_key is None:
        return None
    config = request.app.state.config
    if x_api_key not in config.server.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key


# POST /events endpoint - Event ingestion with API key auth and database storage
@app.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    request: Request,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Create event in database with API key authentication.

    Args:
        event: Event data (source, event_type required)
        request: FastAPI request for app.state access
        _api_key: Validated API key (via dependency)

    Returns:
        Success response with event_id

    Raises:
        HTTPException: 401 if API key invalid, 422 if schema invalid (automatic)
    """
    # Convert EventCreate to dict and generate timestamp if missing
    event_dict = event.model_dump()
    if event_dict.get("timestamp") is None:
        event_dict["timestamp"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    db = request.app.state.db

    # Handle session lifecycle events
    hook = event_dict.get("hook")
    session_id = event_dict.get("session_id")

    ws_manager = request.app.state.ws_manager

    if hook == "SessionStart":
        if session_id:
            # Extract project from data blob if present
            data = event_dict.get("data") or {}
            project = data.get("project")
            db.create_session(session_id, project)
            # Broadcast session lifecycle to UI
            session_data = db.get_session_by_id(session_id)
            if session_data:
                asyncio.create_task(ws_manager.broadcast_lifecycle("session_started", session_data))
        else:
            logger.warning("SessionStart event missing session_id, skipping session creation")

    elif hook == "SessionEnd":
        if session_id:
            if db.update_session_ended(session_id):
                # Broadcast session lifecycle to UI
                session_data = db.get_session_by_id(session_id)
                if session_data:
                    asyncio.create_task(
                        ws_manager.broadcast_lifecycle("session_ended", session_data)
                    )
            else:
                logger.warning(f"SessionEnd for unknown session: {session_id}")
        else:
            logger.warning("SessionEnd event missing session_id, skipping session update")

    # Handle agent lifecycle events
    # New flow: PreToolUse (pending) -> PostToolUse (completion) with tool_use_id correlation
    event_type = event_dict.get("event_type")
    agent_id = event_dict.get("agent_id")
    tool_use_id = event_dict.get("tool_use_id")

    if event_type == "agent" and hook == "PreToolUse":
        # Agent starting - create pending record keyed by tool_use_id
        if tool_use_id and session_id:
            data = event_dict.get("data") or {}
            agent_type = data.get("subagent_type", "subagent")
            name = data.get("description")
            parent_agent_id = data.get("parent_agent_id")
            created = db.create_pending_agent(
                tool_use_id, session_id, agent_type, name, parent_agent_id
            )
            logger.info(f"Agent PreToolUse: created={created} tool_use_id={tool_use_id}")
            # Broadcast agent lifecycle to UI (using tool_use_id as temporary id)
            agent_data = db.get_agent_by_tool_use_id(tool_use_id)
            if agent_data:
                logger.info(f"Broadcasting agent_started: {agent_data.get('id')}")
                asyncio.create_task(ws_manager.broadcast_lifecycle("agent_started", agent_data))
            else:
                logger.warning(
                    f"Agent PreToolUse: get_agent_by_tool_use_id returned None for {tool_use_id}"
                )
        else:
            if not tool_use_id:
                logger.warning(
                    "Agent PreToolUse event missing tool_use_id, skipping agent creation"
                )
            if not session_id:
                logger.warning("Agent PreToolUse event missing session_id, skipping agent creation")

    elif event_type == "agent" and hook == "PostToolUse":
        # Agent completed - correlate tool_use_id to set real agent_id
        if tool_use_id and agent_id:
            event_status = event_dict.get("status", "success")
            final_status = "completed" if event_status == "success" else "failed"
            if db.complete_agent_by_tool_use_id(tool_use_id, agent_id, final_status):
                # Broadcast agent lifecycle to UI (now with real agent_id)
                agent_data = db.get_agent_by_id(agent_id)
                if agent_data:
                    asyncio.create_task(
                        ws_manager.broadcast_lifecycle("agent_completed", agent_data)
                    )
            else:
                logger.warning(f"Agent PostToolUse for unknown tool_use_id: {tool_use_id}")
        else:
            if not tool_use_id:
                logger.warning("Agent PostToolUse event missing tool_use_id, skipping agent update")
            if not agent_id:
                logger.warning("Agent PostToolUse event missing agent_id, skipping agent update")

    # Legacy SubagentStart/SubagentStop handlers (keep for backwards compatibility)
    elif hook == "SubagentStart":
        if agent_id and session_id:
            data = event_dict.get("data") or {}
            agent_type = data.get("type", "subagent")
            name = data.get("name")
            parent_agent_id = data.get("parent_agent_id")
            db.create_agent(agent_id, session_id, agent_type, name, parent_agent_id)
            # Broadcast agent lifecycle to UI
            agent_data = db.get_agent_by_id(agent_id)
            if agent_data:
                asyncio.create_task(ws_manager.broadcast_lifecycle("agent_started", agent_data))
        else:
            if not agent_id:
                logger.warning("SubagentStart event missing agent_id, skipping agent creation")
            if not session_id:
                logger.warning("SubagentStart event missing session_id, skipping agent creation")

    elif hook == "SubagentStop":
        if agent_id:
            data = event_dict.get("data") or {}
            status = data.get("status", "completed")
            if db.update_agent_completed(agent_id, status):
                # Broadcast agent lifecycle to UI
                agent_data = db.get_agent_by_id(agent_id)
                if agent_data:
                    asyncio.create_task(
                        ws_manager.broadcast_lifecycle("agent_completed", agent_data)
                    )
            else:
                logger.warning(f"SubagentStop for unknown agent: {agent_id}")
        else:
            logger.warning("SubagentStop event missing agent_id, skipping agent update")

    elif hook == "SubagentActivated":
        # Activation event correlates pending agent (by tool_use_id) with real agent_id
        # Sent by Momentum when first tool inside subagent fires
        if tool_use_id and agent_id:
            if db.activate_pending_agent(tool_use_id, agent_id):
                logger.info(f"Activated pending agent: {tool_use_id} -> {agent_id}")
                # Broadcast activation to UI with both IDs for tree update
                agent_data = db.get_agent_by_id(agent_id)
                if agent_data:
                    # Include old ID so UI can find and update the element
                    agent_data["old_id"] = tool_use_id
                    asyncio.create_task(
                        ws_manager.broadcast_lifecycle("agent_activated", agent_data)
                    )
            else:
                logger.warning(f"SubagentActivated: no pending agent for tool_use_id={tool_use_id}")
        else:
            if not tool_use_id:
                logger.warning("SubagentActivated missing tool_use_id")
            if not agent_id:
                logger.warning("SubagentActivated missing agent_id")

    # Store event in database
    event_id = db.store_event(event_dict)

    # Broadcast event to WebSocket clients (non-blocking)
    # Construct complete event dict with ID for broadcast
    broadcast_event = {
        "id": event_id,
        "source": event_dict["source"],
        "event_type": event_dict["event_type"],
        "timestamp": event_dict["timestamp"],
        "message": event_dict.get("message"),
        "level": event_dict.get("level"),
        "data": event_dict.get("data"),
        "session_id": event_dict.get("session_id"),
        "hook": event_dict.get("hook"),
        "tool_name": event_dict.get("tool_name"),
        "tool_use_id": event_dict.get("tool_use_id"),
        "status": event_dict.get("status"),
        "agent_id": event_dict.get("agent_id"),
        "is_background": event_dict.get("is_background"),
    }
    # Broadcast in background task to avoid blocking response
    asyncio.create_task(ws_manager.broadcast(broadcast_event))

    # Return success response
    return {"status": "captured", "event_id": event_id}


# GET /events endpoint - Query historical events with filtering
@app.get("/events", response_model=EventListResponse)
async def query_events(
    request: Request,
    _api_key: str | None = Depends(verify_optional_api_key),
    source: str | None = None,
    event_type: str | None = None,
    level: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
    session_id: str | None = None,
    hook: str | None = None,
    tool_name: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    agent_id: str | None = None,
) -> EventListResponse:
    """Query events with optional filtering.

    Args:
        request: FastAPI request for app.state access
        _api_key: Validated API key or None (via dependency)
        source: Filter by source
        event_type: Filter by event type
        level: Filter by level
        since: Filter events after this timestamp (ISO8601)
        until: Filter events before this timestamp (ISO8601)
        limit: Maximum number of events to return (default 100, max 1000)
        session_id: Filter by session ID
        hook: Filter by hook type
        tool_name: Filter by tool name
        status_filter: Filter by status (success/failure/pending)
        agent_id: Filter by agent ID

    Returns:
        JSON response with events list

    Raises:
        HTTPException: 401 if API key provided but invalid, 400 if limit exceeds max
    """
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
        session_id=session_id,
        hook=hook,
        tool_name=tool_name,
        status=status_filter,
        agent_id=agent_id,
    )

    return EventListResponse(events=events, total=len(events))


# GET /sources endpoint - Discovery endpoint for available sources
@app.get("/sources")
async def get_sources(
    request: Request,
    _api_key: str | None = Depends(verify_optional_api_key),
) -> dict[str, Any]:
    """Get list of distinct sources from events.

    Args:
        request: FastAPI request for app.state access
        _api_key: Validated API key or None (via dependency)

    Returns:
        JSON response with sources list

    Raises:
        HTTPException: 401 if API key provided but invalid
    """
    db = request.app.state.db
    sources = db.get_sources()

    return {"sources": sources}


# GET /event-types endpoint - Discovery endpoint for available event types
@app.get("/event-types")
async def get_event_types(
    request: Request,
    _api_key: str | None = Depends(verify_optional_api_key),
) -> dict[str, Any]:
    """Get list of distinct event types from events.

    Args:
        request: FastAPI request for app.state access
        _api_key: Validated API key or None (via dependency)

    Returns:
        JSON response with event_types list

    Raises:
        HTTPException: 401 if API key provided but invalid
    """
    db = request.app.state.db
    event_types = db.get_event_types()

    return {"event_types": event_types}


# GET /sessions endpoint - Discovery endpoint for sessions with agent counts
@app.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    request: Request,
    _api_key: str | None = Depends(verify_optional_api_key),
) -> SessionListResponse:
    """Get list of sessions with agent counts.

    Args:
        request: FastAPI request for app.state access
        _api_key: Validated API key or None (via dependency)

    Returns:
        JSON response with sessions list including agent_count per session

    Raises:
        HTTPException: 401 if API key provided but invalid
    """
    db = request.app.state.db
    sessions = db.get_sessions()

    return SessionListResponse(sessions=sessions)


# GET /agents endpoint - Discovery endpoint for agents with optional session filter
@app.get("/agents", response_model=AgentListResponse)
async def get_agents(
    request: Request,
    _api_key: str | None = Depends(verify_optional_api_key),
    session_id: str | None = None,
) -> AgentListResponse:
    """Get list of agents, optionally filtered by session.

    Args:
        request: FastAPI request for app.state access
        _api_key: Validated API key or None (via dependency)
        session_id: Optional session ID to filter agents

    Returns:
        JSON response with agents list

    Raises:
        HTTPException: 401 if API key provided but invalid
    """
    db = request.app.state.db
    agents = db.get_agents(session_id=session_id)

    return AgentListResponse(agents=agents)


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
                # Validate API key or check for same-origin (web UI)
                api_key = message.get("api_key")
                config = websocket.app.state.config

                # Check if API key is valid
                is_api_key_valid = api_key and api_key in config.server.api_keys

                # Check if request is from web UI (same server, identified by matching port)
                is_web_ui = False
                if not api_key:
                    # No API key provided - check if Origin port matches server port
                    origin = websocket.headers.get("origin", "")
                    if origin:
                        try:
                            # Parse port from Origin (e.g., "http://192.168.1.100:8765")
                            origin_port = int(origin.split(":")[-1].rstrip("/"))
                            is_web_ui = origin_port == config.server.port
                        except (ValueError, IndexError):
                            # Invalid Origin format - not from web UI
                            is_web_ui = False

                if is_api_key_valid or is_web_ui:
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
                    # Authentication failed (API key invalid or missing Origin/wrong port)
                    error_msg = "Invalid API key" if api_key else "API key required"
                    await websocket.send_json(
                        {
                            "type": "auth_result",
                            "status": "error",
                            "message": error_msg,
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
        logger.error("WebSocket error: %s", e, exc_info=True)
    finally:
        # Remove connection from manager
        await ws_manager.disconnect(websocket)


# Mount static files for web UI (serves at /)
# Note: Must be mounted AFTER API routes to avoid shadowing /events endpoint
# Try development location first, then installed location
web_dir = Path(__file__).parent.parent.parent / "web"
if not web_dir.exists():
    # Try installed location (sys.prefix/share/argus/web)
    import sys

    web_dir = Path(sys.prefix) / "share" / "argus" / "web"

if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
else:
    logger.warning("Web UI directory not found at %s", web_dir)
