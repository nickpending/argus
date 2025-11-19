// Argus Web UI - Event Observability Interface
// WebSocket client with real-time event streaming

// Configuration
const CONFIG = {
  wsUrl: "ws://localhost:8765/ws",
  apiKey: "test-key-123", // TODO: Load from server config endpoint (task 9.3)
  reconnect: {
    initialDelay: 5000, // 5 seconds
    maxDelay: 60000, // 60 seconds
    backoffMultiplier: 2,
  },
};

// Connection state
const state = {
  ws: null,
  connectionState: "disconnected", // disconnected | connecting | connected
  reconnectDelay: CONFIG.reconnect.initialDelay,
  reconnectTimer: null,
  authenticated: false,
  currentFilters: {},
};

// DOM element references (cached on load)
const elements = {};

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  initializeEventListeners();
  connect();
});

// Cache DOM element references
function cacheElements() {
  elements.statusDot = document.getElementById("status-dot");
  elements.statusText = document.getElementById("status-text");
  elements.eventsBody = document.getElementById("events-body");
  elements.autoScroll = document.getElementById("auto-scroll");
  elements.detailPanel = document.getElementById("detail-panel");
  elements.detailClose = document.getElementById("detail-close");
  elements.detailId = document.getElementById("detail-id");
  elements.detailSource = document.getElementById("detail-source");
  elements.detailType = document.getElementById("detail-type");
  elements.detailTimestamp = document.getElementById("detail-timestamp");
  elements.detailLevel = document.getElementById("detail-level");
  elements.detailMessage = document.getElementById("detail-message");
  elements.detailDataJson = document.getElementById("detail-data-json");
}

// Initialize event listeners
function initializeEventListeners() {
  // Detail panel close button
  elements.detailClose.addEventListener("click", () => {
    elements.detailPanel.classList.remove("open");
  });
}

// WebSocket connection management
function connect() {
  if (state.connectionState !== "disconnected") {
    return;
  }

  state.connectionState = "connecting";
  updateStatus("connecting", "Connecting...");

  try {
    state.ws = new WebSocket(CONFIG.wsUrl);

    state.ws.addEventListener("open", handleOpen);
    state.ws.addEventListener("message", handleMessage);
    state.ws.addEventListener("close", handleClose);
    state.ws.addEventListener("error", handleError);
  } catch (error) {
    console.error("WebSocket connection error:", error);
    scheduleReconnect();
  }
}

// Handle WebSocket open
function handleOpen() {
  console.log("WebSocket connected");

  // Send auth message immediately
  sendAuth();
}

// Handle WebSocket messages
function handleMessage(event) {
  try {
    const message = JSON.parse(event.data);

    // Route by message type
    switch (message.type) {
      case "auth_result":
        handleAuthResult(message);
        break;
      case "subscribe_result":
        handleSubscribeResult(message);
        break;
      case "event":
        handleEvent(message);
        break;
      case "error":
        console.error("WebSocket error:", message.message);
        break;
      case "pong":
        // Heartbeat response (optional feature)
        break;
      default:
        console.warn("Unknown message type:", message.type);
    }
  } catch (error) {
    console.error("Failed to parse WebSocket message:", error);
  }
}

// Handle WebSocket close
function handleClose(event) {
  console.log("WebSocket closed:", event.code, event.reason);

  state.connectionState = "disconnected";
  state.authenticated = false;
  updateStatus("disconnected", "Disconnected");

  // Attempt reconnection
  scheduleReconnect();
}

// Handle WebSocket error
function handleError(error) {
  console.error("WebSocket error:", error);
}

// Send authentication message
function sendAuth() {
  const authMessage = {
    type: "auth",
    api_key: CONFIG.apiKey,
  };

  send(authMessage);
}

// Handle authentication result
function handleAuthResult(message) {
  if (message.status === "success") {
    state.authenticated = true;
    state.connectionState = "connected";
    state.reconnectDelay = CONFIG.reconnect.initialDelay; // Reset backoff
    updateStatus("connected", "Connected");

    console.log("WebSocket authenticated successfully");

    // Subscribe to all events initially (empty filters)
    subscribe({});
  } else {
    console.error("Authentication failed:", message.message);
    state.ws.close();
  }
}

// Send subscribe message
function subscribe(filters) {
  const subscribeMessage = {
    type: "subscribe",
    filters: filters,
  };

  state.currentFilters = filters;
  send(subscribeMessage);
}

// Handle subscribe result
function handleSubscribeResult(message) {
  if (message.status === "success") {
    console.log("Subscribed with filters:", message.active_filters);
  } else {
    console.error("Subscription failed:", message.message);
  }
}

// Handle event message
function handleEvent(message) {
  const event = message.event;

  // Render event to table
  renderEvent(event);
}

// Render event to table
function renderEvent(event) {
  const row = document.createElement("tr");
  row.className = "event-row";
  row.dataset.eventId = event.id;
  if (event.level) {
    row.dataset.level = event.level;
  }

  // Format timestamp
  const timestamp = formatTimestamp(event.timestamp);

  // Format level badge
  const levelBadge = event.level
    ? `<span class="level-badge ${event.level}">${event.level}</span>`
    : '<span class="level-badge debug">-</span>';

  // Truncate message for table display
  const message = event.message || "-";
  const displayMessage =
    message.length > 60 ? message.substring(0, 57) + "..." : message;

  row.innerHTML = `
        <td class="time">${timestamp}</td>
        <td class="source"><span class="source-badge">${escapeHtml(event.source)}</span></td>
        <td class="type">${escapeHtml(event.event_type)}</td>
        <td class="level">${levelBadge}</td>
        <td class="message">${escapeHtml(displayMessage)}</td>
    `;

  // Add click handler for detail panel
  row.addEventListener("click", () => {
    showEventDetail(event);
  });

  // Insert at top of table (newest first)
  elements.eventsBody.insertBefore(row, elements.eventsBody.firstChild);

  // Auto-scroll if enabled
  if (elements.autoScroll.checked) {
    row.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// Show event detail panel
function showEventDetail(event) {
  elements.detailId.textContent = event.id;
  elements.detailSource.textContent = event.source;
  elements.detailType.textContent = event.event_type;
  elements.detailTimestamp.textContent = event.timestamp;
  elements.detailLevel.textContent = event.level || "-";
  elements.detailMessage.textContent = event.message || "-";

  // Pretty-print JSON data
  if (event.data) {
    elements.detailDataJson.textContent = JSON.stringify(event.data, null, 2);
  } else {
    elements.detailDataJson.textContent = "null";
  }

  // Show panel
  elements.detailPanel.classList.add("open");
}

// Format timestamp for display
function formatTimestamp(isoTimestamp) {
  const date = new Date(isoTimestamp);

  // Format as HH:MM:SS
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");

  return `${hours}:${minutes}:${seconds}`;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Update connection status indicator
function updateStatus(state, text) {
  elements.statusDot.className = `status-dot ${state}`;
  elements.statusText.textContent = text;
}

// Send message to WebSocket
function send(message) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(message));
  } else {
    console.warn("WebSocket not open, cannot send message:", message);
  }
}

// Schedule reconnection with exponential backoff
function scheduleReconnect() {
  // Clear existing timer
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
  }

  console.log(`Reconnecting in ${state.reconnectDelay / 1000}s...`);

  state.reconnectTimer = setTimeout(() => {
    connect();

    // Increase backoff for next attempt
    state.reconnectDelay = Math.min(
      state.reconnectDelay * CONFIG.reconnect.backoffMultiplier,
      CONFIG.reconnect.maxDelay,
    );
  }, state.reconnectDelay);
}
