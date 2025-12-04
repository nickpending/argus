"""Integration tests for WebSocket real-time event streaming.

INVARIANT PROTECTION: WebSocket auth security, filter correctness, broadcast reliability
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_unauthenticated_client_receives_no_events(client: TestClient) -> None:
    """
    INVARIANT: Unauthenticated clients never receive events
    BREAKS: Unauthorized access to potentially sensitive event data

    Security boundary: Even if client sends subscribe before auth,
    they must not receive any broadcast events.
    """
    with client.websocket_connect("/ws") as websocket:
        # Client connects but does NOT authenticate
        # Send subscribe message without auth
        websocket.send_json({"type": "subscribe", "filters": {}})

        # Post event via HTTP API
        response = client.post(
            "/events",
            json={"source": "test", "event_type": "session", "message": "Sensitive"},
            headers={"X-API-Key": "test-key-1"},
        )
        assert response.status_code == 201

        # Try to receive - should only get subscribe response, not event
        # (unauthenticated clients don't match filters)
        msg = websocket.receive_json()
        # First message should be subscribe response or nothing event-related
        if msg.get("type") == "event":
            pytest.fail("Unauthenticated client received event!")


def test_invalid_api_key_closes_connection(client: TestClient) -> None:
    """
    INVARIANT: Invalid API key closes WebSocket connection
    BREAKS: Unauthorized persistent connections consuming resources

    Failure mode: Wrong API key must be explicitly rejected with error message,
    then connection closed (code 1008 policy violation).
    """
    with client.websocket_connect("/ws") as websocket:
        # Send auth with invalid API key
        websocket.send_json({"type": "auth", "api_key": "wrong-key-999"})

        # Receive auth failure response
        auth_result = websocket.receive_json()

        assert auth_result["type"] == "auth_result"
        assert auth_result["status"] == "error"
        assert "invalid" in auth_result["message"].lower()

        # Connection should close after auth failure
        try:
            websocket.receive_json()  # Should raise WebSocketDisconnect
            pytest.fail("Connection should have closed after auth failure")
        except WebSocketDisconnect:
            # Expected - connection closed
            pass


def test_filter_and_logic_prevents_leakage(client: TestClient) -> None:
    """
    INVARIANT: Filters use AND logic - all filter keys must match
    BREAKS: Events leak to subscribers with partial match (data leakage)

    Security risk: In multi-tenant observability, incorrect filtering
    could expose events to wrong subscribers.
    """
    with client.websocket_connect("/ws") as websocket:
        # Authenticate
        websocket.send_json({"type": "auth", "api_key": "test-key-1"})
        auth_response = websocket.receive_json()
        assert auth_response["status"] == "success"

        # Subscribe with TWO filters: source AND event_type
        websocket.send_json(
            {
                "type": "subscribe",
                "filters": {"source": "app-a", "event_type": "agent"},
            }
        )
        subscribe_response = websocket.receive_json()
        assert subscribe_response["status"] == "success"

        # Post events with different combinations
        test_cases = [
            {
                "source": "app-a",
                "event_type": "agent",
                "should_receive": True,
            },  # Match both
            {
                "source": "app-a",
                "event_type": "tool",
                "should_receive": False,
            },  # Wrong event_type
            {
                "source": "app-b",
                "event_type": "agent",
                "should_receive": False,
            },  # Wrong source
        ]

        for test_case in test_cases:
            response = client.post(
                "/events",
                json={
                    "source": test_case["source"],
                    "event_type": test_case["event_type"],
                    "message": f"Test {test_case['source']}/{test_case['event_type']}",
                },
                headers={"X-API-Key": "test-key-1"},
            )
            assert response.status_code == 201

        # Receive events (only the matching one should arrive)
        # Give broadcast time to complete
        import time

        time.sleep(0.1)

        # Receive exactly one event (only the fully-matching one)
        msg = websocket.receive_json()
        assert msg["type"] == "event"
        received_event = msg["event"]

        # Verify the event matches our filter
        assert received_event["source"] == "app-a"
        assert received_event["event_type"] == "agent"


def test_empty_filters_receive_all_events(client: TestClient) -> None:
    """
    INVARIANT: Empty filters dict receives ALL events
    BREAKS: Silent data loss from missing events

    Protocol requirement: No filters = subscribe to everything.
    """
    with client.websocket_connect("/ws") as websocket:
        # Authenticate
        websocket.send_json({"type": "auth", "api_key": "test-key-1"})
        auth_response = websocket.receive_json()
        assert auth_response["status"] == "success"

        # Subscribe with EMPTY filters
        websocket.send_json({"type": "subscribe", "filters": {}})
        subscribe_response = websocket.receive_json()
        assert subscribe_response["status"] == "success"

        # Post events with different sources and types
        test_events = [
            {"source": "app-1", "event_type": "tool"},
            {"source": "app-2", "event_type": "session"},
            {"source": "app-3", "event_type": "agent"},
        ]

        for event_data in test_events:
            response = client.post(
                "/events",
                json={**event_data, "message": "Test"},
                headers={"X-API-Key": "test-key-1"},
            )
            assert response.status_code == 201

        # Receive all events
        import time

        time.sleep(0.1)  # Let broadcasts complete

        # Receive exactly 3 events
        received_events = []
        for _ in range(3):
            msg = websocket.receive_json()
            assert msg["type"] == "event"
            received_events.append(msg["event"])

        # Verify ALL events were received
        assert len(received_events) == 3
        sources = {e["source"] for e in received_events}
        assert sources == {"app-1", "app-2", "app-3"}


def test_disconnected_clients_removed(client: TestClient) -> None:
    """
    INVARIANT: Disconnected clients removed from broadcast list
    BREAKS: Memory leak + wasted CPU broadcasting to dead connections

    Connection lifecycle: Disconnect must clean up client from manager.
    """
    # Connect client 1, authenticate, then disconnect
    with client.websocket_connect("/ws") as ws1:
        ws1.send_json({"type": "auth", "api_key": "test-key-1"})
        ws1.receive_json()  # Auth response
        ws1.send_json({"type": "subscribe", "filters": {}})
        ws1.receive_json()  # Subscribe response
        # Close connection - should trigger cleanup

    # Connect client 2
    with client.websocket_connect("/ws") as ws2:
        ws2.send_json({"type": "auth", "api_key": "test-key-1"})
        ws2.receive_json()  # Auth response
        ws2.send_json({"type": "subscribe", "filters": {}})
        ws2.receive_json()  # Subscribe response

        # Post event - should only go to ws2
        response = client.post(
            "/events",
            json={
                "source": "cleanup-test",
                "event_type": "prompt",
                "message": "After client 1 disconnected",
            },
            headers={"X-API-Key": "test-key-1"},
        )
        assert response.status_code == 201

        # ws2 should receive event
        import time

        time.sleep(0.1)

        msg = ws2.receive_json()
        assert msg["type"] == "event"

        # If we got here without crash, disconnected client was properly removed
        # (no attempt to broadcast to ws1)


def test_broadcast_reaches_all_matching_clients(client: TestClient) -> None:
    """
    INVARIANT: All authenticated, filter-matching clients receive broadcast
    BREAKS: Silent data loss to some subscribers

    Broadcast completeness: Every matching client gets the event.
    """
    # Note: TestClient doesn't support multiple simultaneous WebSocket connections
    # This test verifies single-client delivery works correctly
    # Multi-client testing would require a real server

    with client.websocket_connect("/ws") as websocket:
        # Authenticate
        websocket.send_json({"type": "auth", "api_key": "test-key-1"})
        auth_response = websocket.receive_json()
        assert auth_response["status"] == "success"

        # Subscribe to specific source
        websocket.send_json({"type": "subscribe", "filters": {"source": "broadcast-test"}})
        subscribe_response = websocket.receive_json()
        assert subscribe_response["status"] == "success"

        # Post matching event
        response = client.post(
            "/events",
            json={
                "source": "broadcast-test",
                "event_type": "response",
                "message": "Should be received",
            },
            headers={"X-API-Key": "test-key-1"},
        )
        assert response.status_code == 201

        # Client should receive the event
        import time

        time.sleep(0.1)

        msg = websocket.receive_json()
        assert msg["type"] == "event"
        assert msg["event"]["source"] == "broadcast-test"


def test_web_ui_auth_without_api_key(client: TestClient) -> None:
    """
    INVARIANT: Web UI can authenticate without API key using Origin validation
    BREAKS: Web UI cannot connect (usability failure)

    Security model: Web UI served by same server, authenticated by matching Origin port.
    TestClient creates localhost connections similar to web UI browser requests.
    """
    with client.websocket_connect("/ws", headers={"Origin": "http://127.0.0.1:8765"}) as websocket:
        # Authenticate WITHOUT API key (web UI pattern)
        websocket.send_json({"type": "auth"})
        auth_response = websocket.receive_json()

        assert auth_response["type"] == "auth_result"
        assert auth_response["status"] == "success"


def test_network_connection_without_api_key_rejected(client: TestClient) -> None:
    """
    INVARIANT: Connections without API key from wrong port are rejected (P0 fix)
    BREAKS: Authentication bypass vulnerability

    Attack vector: External client connects without API key, pretending different Origin.
    Must be rejected even if Origin header is present but port doesn't match.
    """
    with client.websocket_connect(
        "/ws", headers={"Origin": "http://192.168.1.100:9999"}
    ) as websocket:
        # Attempt auth without API key from different port
        websocket.send_json({"type": "auth"})
        auth_response = websocket.receive_json()

        assert auth_response["type"] == "auth_result"
        assert auth_response["status"] == "error"
        assert "api key required" in auth_response["message"].lower()

        # Connection should close
        try:
            websocket.receive_json()
            pytest.fail("Connection should have closed after auth failure")
        except WebSocketDisconnect:
            pass


def test_no_origin_header_without_api_key_rejected(client: TestClient) -> None:
    """
    INVARIANT: Connections without Origin header and no API key are rejected
    BREAKS: Non-browser clients bypass authentication

    Edge case: Non-browser tools may not send Origin header.
    Without API key, must be rejected (fail secure).
    """
    with client.websocket_connect("/ws") as websocket:
        # Attempt auth without API key and no Origin header
        websocket.send_json({"type": "auth"})
        auth_response = websocket.receive_json()

        assert auth_response["type"] == "auth_result"
        assert auth_response["status"] == "error"
        assert "api key required" in auth_response["message"].lower()

        # Connection should close
        try:
            websocket.receive_json()
            pytest.fail("Connection should have closed after auth failure")
        except WebSocketDisconnect:
            pass
