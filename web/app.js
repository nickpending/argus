// Argus Web UI - Event Observability Interface
// WebSocket client with real-time event streaming

// Configuration
const CONFIG = {
  wsUrl: `ws://${window.location.host}/ws`,
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
  loadSourceOptions();
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
  // Filter panel elements
  elements.filterPanel = document.getElementById("filter-panel");
  elements.filterToggle = document.getElementById("filter-toggle");
  elements.filterSource = document.getElementById("filter-source");
  elements.filterType = document.getElementById("filter-type");
  elements.filterSearch = document.getElementById("filter-search");
  elements.filterApply = document.getElementById("filter-apply");
  elements.filterClear = document.getElementById("filter-clear");
  elements.levelChips = document.querySelectorAll(".level-chips .chip");
}

// Initialize event listeners
function initializeEventListeners() {
  // Detail panel close button
  elements.detailClose.addEventListener("click", () => {
    elements.detailPanel.classList.remove("open");
  });

  // Filter panel toggle button
  elements.filterToggle.addEventListener("click", () => {
    elements.filterPanel.classList.toggle("open");
  });

  // Level chip toggle buttons (auto-apply on click)
  elements.levelChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
      // Auto-apply filters when chip toggled
      applyFilters();
    });
  });

  // Filter apply button
  elements.filterApply.addEventListener("click", () => {
    applyFilters();
  });

  // Filter clear button
  elements.filterClear.addEventListener("click", () => {
    clearFilters();
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

  // Format level badge (null level = debug)
  const level = event.level || "debug";
  const levelText = event.level || "-";
  const levelBadge = `<span class="level-badge ${level}">${levelText}</span>`;

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

  // Check if row matches current filters
  const matchesFilter = rowMatchesFilter(row, state.currentFilters);
  if (!matchesFilter) {
    row.style.display = "none";
  }

  // Insert at top of table (newest first)
  elements.eventsBody.insertBefore(row, elements.eventsBody.firstChild);

  // Auto-scroll if enabled (only for visible rows)
  if (elements.autoScroll.checked && matchesFilter) {
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

// Collect current filter values
function collectFilters() {
  const filters = {};

  // Source filter (dropdown)
  const source = elements.filterSource.value.trim();
  if (source) {
    filters.source = source;
  }

  // Event type filter (comma-separated text input)
  const eventType = elements.filterType.value.trim();
  if (eventType) {
    filters.event_type = eventType;
  }

  // Level filter (active chips = visible levels)
  const activeLevels = Array.from(elements.levelChips)
    .filter((chip) => chip.classList.contains("active"))
    .map((chip) => chip.dataset.level);

  // Always apply level filter
  // If all active (4 chips), omit filter = show all
  // If some active, filter to those levels
  // If none active, empty array = hide all
  if (activeLevels.length < 4) {
    filters.levels = activeLevels;
  }

  // Search filter (message contains text)
  const search = elements.filterSearch.value.trim();
  if (search) {
    filters.search = search;
  }

  return filters;
}

// Apply current filters (CLIENT-SIDE - show/hide rows)
function applyFilters() {
  const filters = collectFilters();

  // Store current filters for newly arriving events
  state.currentFilters = filters;

  // Filter existing table rows
  filterTableRows(filters);
}

// Clear all filters
function clearFilters() {
  // Reset source dropdown
  elements.filterSource.value = "";

  // Reset event type input
  elements.filterType.value = "";

  // Reset search input
  elements.filterSearch.value = "";

  // Activate all level chips (show all levels)
  elements.levelChips.forEach((chip) => {
    chip.classList.add("active");
  });

  // Clear stored filters
  state.currentFilters = {};

  // Show all rows
  filterTableRows({});
}

// Filter table rows client-side (show/hide based on criteria)
function filterTableRows(filters) {
  const rows = elements.eventsBody.querySelectorAll(".event-row");

  rows.forEach((row) => {
    const matchesFilter = rowMatchesFilter(row, filters);
    row.style.display = matchesFilter ? "" : "none";
  });
}

// Check if row matches filter criteria
function rowMatchesFilter(row, filters) {
  // No filters = show all
  if (Object.keys(filters).length === 0) {
    return true;
  }

  // Extract row data from DOM
  const sourceCell = row.querySelector(".source .source-badge");
  const typeCell = row.querySelector(".type");
  const levelCell = row.querySelector(".level .level-badge");
  const messageCell = row.querySelector(".message");

  const rowData = {
    source: sourceCell ? sourceCell.textContent.trim() : "",
    event_type: typeCell ? typeCell.textContent.trim() : "",
    level: levelCell ? levelCell.textContent.trim() : "",
    message: messageCell ? messageCell.textContent.trim() : "",
  };

  // Check source filter
  if (filters.source && rowData.source !== filters.source) {
    return false;
  }

  // Check event_type filter
  if (filters.event_type && rowData.event_type !== filters.event_type) {
    return false;
  }

  // Check level filter (OR logic - show if matches ANY active level)
  if (filters.levels !== undefined) {
    // If empty array, hide all (no levels selected)
    if (filters.levels.length === 0) {
      return false;
    }
    // Events with no level show as "-" in badge, treat as debug level
    const eventLevel = rowData.level === "-" ? "debug" : rowData.level;
    if (!filters.levels.includes(eventLevel)) {
      return false;
    }
  }

  // Check search filter (message contains text)
  if (filters.search) {
    const searchLower = filters.search.toLowerCase();
    if (!rowData.message.toLowerCase().includes(searchLower)) {
      return false;
    }
  }

  return true;
}

// Load source options from API
async function loadSourceOptions() {
  try {
    const response = await fetch("/sources", {
      headers: {
        "X-API-Key": CONFIG.apiKey,
      },
    });

    if (!response.ok) {
      console.error("Failed to load sources:", response.status);
      return;
    }

    const data = await response.json();
    const sources = data.sources || [];

    // Populate dropdown
    sources.forEach((source) => {
      const option = document.createElement("option");
      option.value = source;
      option.textContent = source;
      elements.filterSource.appendChild(option);
    });

    console.log(`Loaded ${sources.length} sources for filter dropdown`);
  } catch (error) {
    console.error("Error loading sources:", error);
  }
}
