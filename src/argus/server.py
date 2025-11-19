"""FastAPI server and endpoints."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
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

    # Initialize WebSocket manager (stub for tasks 6.1-6.4)
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

    # Return success response
    return {"status": "captured", "event_id": event_id}


# Mount static files for web UI (serves at /)
# Note: Must be mounted AFTER API routes to avoid shadowing /events endpoint
web_dir = Path(__file__).parent.parent.parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
