"""Shared test fixtures and configuration.

Provides isolated test environment with temporary database and proper FastAPI app lifecycle.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from argus.database import Database
from argus.models import Config, DatabaseConfig, ServerConfig
from argus.server import app
from argus.websocket import WebSocketManager


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create test configuration with temporary database.

    Args:
        tmp_path: Pytest fixture providing temporary directory

    Returns:
        Config object with isolated test database and test API keys
    """
    db_path = tmp_path / "test_events.db"
    return Config(
        database=DatabaseConfig(path=str(db_path)),
        server=ServerConfig(
            host="127.0.0.1",
            port=8765,
            api_keys=["test-key-1", "test-key-2"],
        ),
    )


@pytest.fixture
def test_db(test_config: Config) -> Generator[Database, None, None]:
    """Create isolated test database instance.

    Args:
        test_config: Test configuration with temporary database path

    Yields:
        Database instance connected to temporary test database

    Cleanup:
        Closes database connection after test completes
    """
    db = Database(test_config.database.path)
    yield db
    db.close()


@pytest.fixture
def test_ws_manager() -> WebSocketManager:
    """Create isolated WebSocket manager instance.

    Returns:
        Fresh WebSocketManager with no connections
    """
    return WebSocketManager()


@pytest.fixture
def client(
    test_config: Config, test_db: Database, test_ws_manager: WebSocketManager
) -> Generator[TestClient, None, None]:
    """Create FastAPI test client with isolated test state.

    Uses app state injection for test isolation. Each test gets fresh
    database and WebSocket manager instances.

    Args:
        test_config: Test configuration fixture
        test_db: Isolated test database fixture
        test_ws_manager: Isolated WebSocket manager fixture

    Yields:
        TestClient configured with test fixtures

    Notes:
        - Bypasses lifespan events to use test fixtures
        - Each test has isolated state (no cross-test contamination)
        - Database automatically cleaned up by test_db fixture
    """
    # Override app state with test fixtures BEFORE creating TestClient
    app.state.config = test_config
    app.state.db = test_db
    app.state.ws_manager = test_ws_manager

    # Create TestClient with raise_server_exceptions=False to bypass lifespan
    # This prevents the lifespan context manager from running, allowing us to use test fixtures
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    # Cleanup: Remove test state from global app
    # (Prevents state leakage to next test)
    if hasattr(app.state, "config"):
        delattr(app.state, "config")
    if hasattr(app.state, "db"):
        delattr(app.state, "db")
    if hasattr(app.state, "ws_manager"):
        delattr(app.state, "ws_manager")
