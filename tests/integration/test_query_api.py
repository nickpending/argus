"""Integration tests for query API endpoints.

INVARIANT PROTECTION: Query authentication, DOS prevention, filter accuracy, discovery completeness
"""

from fastapi.testclient import TestClient


def test_get_events_requires_valid_api_key(client: TestClient) -> None:
    """
    INVARIANT: Unauthorized users cannot query events
    BREAKS: Data breach - attacker queries all user events without authentication

    Security boundary: GET /events must validate X-API-Key header
    """
    # Attempt GET /events with invalid API key
    response = client.get("/events", headers={"X-API-Key": "invalid-key-999"})

    # Verify 401 Unauthorized
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_get_sources_requires_valid_api_key(client: TestClient) -> None:
    """
    INVARIANT: Unauthorized users cannot discover system metadata
    BREAKS: Information disclosure - attacker learns what tools are integrated

    Security boundary: GET /sources reveals which applications are sending events
    """
    # Attempt GET /sources with invalid API key
    response = client.get("/sources", headers={"X-API-Key": "wrong-key-123"})

    # Verify 401 Unauthorized
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_get_event_types_requires_valid_api_key(client: TestClient) -> None:
    """
    INVARIANT: Unauthorized users cannot discover event types
    BREAKS: Information disclosure - attacker learns system activity patterns

    Security boundary: GET /event-types reveals what types of events are being logged
    """
    # Attempt GET /event-types with invalid API key
    response = client.get("/event-types", headers={"X-API-Key": "attacker-key"})

    # Verify 401 Unauthorized
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_limit_enforces_maximum_1000(client: TestClient) -> None:
    """
    INVARIANT: Query limit never exceeds 1000 events
    BREAKS: DOS - unbounded query exhausts memory, blocks all users, system crash

    DOS prevention: Attacker requests limit=999999, server crashes
    """
    # Attempt query with excessive limit
    response = client.get(
        "/events?limit=999999",
        headers={"X-API-Key": "test-key-1"},
    )

    # Verify 400 Bad Request
    assert response.status_code == 400
    assert "1000" in response.json()["detail"]


def test_negative_limit_handled_gracefully(client: TestClient) -> None:
    """
    INVARIANT: Negative limit parameter rejected or defaulted safely
    BREAKS: Undefined database behavior, potential query failure

    Input validation: Negative values could cause unexpected behavior
    """
    # Attempt query with negative limit
    response = client.get(
        "/events?limit=-1",
        headers={"X-API-Key": "test-key-1"},
    )

    # Should either reject (400) or default to safe value and succeed (200)
    # FastAPI Query() with int type validates this automatically
    assert response.status_code in [200, 400, 422]

    # If successful, verify reasonable result
    if response.status_code == 200:
        data = response.json()
        assert "events" in data
        # Verify it didn't return negative number of events
        assert len(data["events"]) >= 0


def test_source_filter_returns_only_matching_events(client: TestClient) -> None:
    """
    INVARIANT: Filters return only matching events
    BREAKS: Wrong events returned = broken debugging, users lose trust in system

    Query accuracy: Filtering is core observability feature
    """
    # Create events with different sources
    test_events = [
        {"source": "app-a", "event_type": "test", "message": "From app-a"},
        {"source": "app-b", "event_type": "test", "message": "From app-b"},
        {"source": "app-a", "event_type": "test", "message": "Another from app-a"},
        {"source": "app-c", "event_type": "test", "message": "From app-c"},
    ]

    for event in test_events:
        response = client.post(
            "/events",
            json=event,
            headers={"X-API-Key": "test-key-1"},
        )
        assert response.status_code == 201

    # Query with source filter
    response = client.get(
        "/events?source=app-a&limit=100",
        headers={"X-API-Key": "test-key-1"},
    )

    assert response.status_code == 200
    data = response.json()
    events = data["events"]

    # Verify only app-a events returned
    assert len(events) >= 2  # At least our 2 app-a events
    for event in events:
        assert event["source"] == "app-a", f"Filter leaked event from {event['source']}"


def test_discovery_endpoints_return_complete_sorted_lists(client: TestClient) -> None:
    """
    INVARIANT: Discovery returns complete, accurate, sorted lists
    BREAKS: Users miss critical events during debugging, incomplete system view

    System completeness: Discovery must show ALL sources and types
    """
    # Create events with multiple sources and types
    test_events = [
        {"source": "zebra", "event_type": "type_z", "message": "Test Z"},
        {"source": "alpha", "event_type": "type_a", "message": "Test A"},
        {"source": "beta", "event_type": "type_b", "message": "Test B"},
    ]

    for event in test_events:
        response = client.post(
            "/events",
            json=event,
            headers={"X-API-Key": "test-key-1"},
        )
        assert response.status_code == 201

    # Test GET /sources
    response = client.get("/sources", headers={"X-API-Key": "test-key-1"})
    assert response.status_code == 200
    sources = response.json()["sources"]

    # Verify all sources present
    assert "alpha" in sources
    assert "beta" in sources
    assert "zebra" in sources

    # Verify alphabetically sorted
    alpha_idx = sources.index("alpha")
    beta_idx = sources.index("beta")
    zebra_idx = sources.index("zebra")
    assert alpha_idx < beta_idx < zebra_idx

    # Test GET /event-types
    response = client.get("/event-types", headers={"X-API-Key": "test-key-1"})
    assert response.status_code == 200
    event_types = response.json()["event_types"]

    # Verify all types present
    assert "type_a" in event_types
    assert "type_b" in event_types
    assert "type_z" in event_types

    # Verify alphabetically sorted
    type_a_idx = event_types.index("type_a")
    type_b_idx = event_types.index("type_b")
    type_z_idx = event_types.index("type_z")
    assert type_a_idx < type_b_idx < type_z_idx
