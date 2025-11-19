"""FastAPI server and endpoints."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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

    # Store in app state for endpoint access
    app.state.config = config
    app.state.db = db
    app.state.ws_manager = ws_manager

    yield  # Application runs here

    # SHUTDOWN PHASE
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
