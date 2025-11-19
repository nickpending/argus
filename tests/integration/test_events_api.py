"""Integration tests for event API endpoints.

INVARIANT PROTECTION: API security, event durability, ID uniqueness
"""

from fastapi.testclient import TestClient

from argus.database import Database
from argus.models import Config


def test_api_key_blocks_unauthenticated(client: TestClient) -> None:
    """
    INVARIANT: Missing API key prevents event creation
    BREAKS: Unauthorized access to event storage

    Security boundary: All POST /events requests must include valid X-API-Key header
    """
    event_data = {
        "source": "test-app",
        "event_type": "test.event",
        "message": "Test event without authentication",
    }

    # Attempt POST without X-API-Key header
    response = client.post("/events", json=event_data)

    # Verify request is rejected
    assert response.status_code == 422  # FastAPI validation error for missing header


def test_invalid_api_key_returns_401(client: TestClient) -> None:
    """
    INVARIANT: Invalid API key returns 401 Unauthorized
    BREAKS: Unauthorized access with wrong credentials

    Failure mode: Wrong API key must be explicitly rejected, not silently accepted
    """
    event_data = {
        "source": "test-app",
        "event_type": "test.event",
        "message": "Test event with wrong API key",
    }

    # Attempt POST with invalid API key
    response = client.post(
        "/events",
        json=event_data,
        headers={"X-API-Key": "wrong-key-999"},
    )

    # Verify 401 Unauthorized
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_post_success_guarantees_persistence(client: TestClient, test_config: Config) -> None:
    """
    INVARIANT: Successful POST (201) guarantees event is persisted to disk
    BREAKS: Data loss - client believes event was saved but it wasn't

    Durability invariant: 201 response means synchronous commit completed
    """
    event_data = {
        "source": "critical-app",
        "event_type": "payment.completed",
        "message": "Payment processed",
        "data": {"amount": 99.99, "currency": "USD"},
    }

    # POST event with valid API key
    response = client.post(
        "/events",
        json=event_data,
        headers={"X-API-Key": "test-key-1"},
    )

    # Verify 201 Created
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["status"] == "captured"
    event_id = response_data["event_id"]

    # CRITICAL: Verify event actually exists in database
    db = Database(test_config.database.path)
    events = db.query_events(limit=1)
    db.close()

    assert len(events) == 1
    stored_event = events[0]
    assert stored_event["id"] == event_id
    assert stored_event["source"] == "critical-app"
    assert stored_event["event_type"] == "payment.completed"
    assert stored_event["data"]["amount"] == 99.99


def test_event_id_uniqueness(client: TestClient) -> None:
    """
    INVARIANT: Event IDs are unique and monotonically increasing
    BREAKS: ID collision could cause query confusion or data corruption

    Database invariant: SQLite INTEGER PRIMARY KEY AUTOINCREMENT guarantees uniqueness
    """
    event_template = {
        "source": "test-app",
        "event_type": "id.test",
        "message": "Testing ID uniqueness",
    }

    event_ids: list[int] = []

    # Create 5 events and collect their IDs
    for i in range(5):
        response = client.post(
            "/events",
            json={**event_template, "message": f"Event {i}"},
            headers={"X-API-Key": "test-key-1"},
        )
        assert response.status_code == 201
        event_ids.append(response.json()["event_id"])

    # Verify all IDs are unique
    assert len(event_ids) == len(set(event_ids))

    # Verify IDs are monotonically increasing
    for i in range(1, len(event_ids)):
        assert event_ids[i] > event_ids[i - 1]
