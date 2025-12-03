// Argus Web UI - Event Observability Interface
// WebSocket client with real-time event streaming

// Configuration
const CONFIG = {
  wsUrl: `ws://${window.location.host}/ws`,
  reconnect: {
    initialDelay: 5000,
    maxDelay: 60000,
    backoffMultiplier: 2,
  },
};

// Connection state
const state = {
  ws: null,
  connectionState: "disconnected",
  reconnectDelay: CONFIG.reconnect.initialDelay,
  reconnectTimer: null,
  authenticated: false,
  currentFilters: {},
  eventCount: 0,
  selectedEventId: null,
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
  // Status
  elements.statusDot = document.getElementById("status-dot");
  elements.statusText = document.getElementById("status-text");

  // Events
  elements.eventsBody = document.getElementById("events-body");
  elements.eventCount = document.getElementById("event-count");
  elements.autoScroll = document.getElementById("auto-scroll");

  // Right panel (detail)
  elements.rightPanel = document.getElementById("right-panel");
  elements.detailPanel = document.getElementById("detail-panel");
  elements.detailClose = document.getElementById("detail-close");
  elements.detailEmpty = document.getElementById("detail-empty");
  elements.detailView = document.getElementById("detail-view");
  elements.detailId = document.getElementById("detail-id");
  elements.detailSource = document.getElementById("detail-source");
  elements.detailType = document.getElementById("detail-type");
  elements.detailTimestamp = document.getElementById("detail-timestamp");
  elements.detailLevel = document.getElementById("detail-level");
  elements.detailMessage = document.getElementById("detail-message");
  elements.detailDataJson = document.getElementById("detail-data-json");

  // Left panel (filters)
  elements.leftPanel = document.getElementById("left-panel");
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
    hideEventDetail();
  });

  // Close detail on ESC key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.selectedEventId) {
      hideEventDetail();
    }
  });

  // Level chip toggle buttons (auto-apply on click)
  elements.levelChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
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

  // Apply filters on Enter key in text inputs
  elements.filterType.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
  });
  elements.filterSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
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
  sendAuth();
}

// Handle WebSocket messages
function handleMessage(event) {
  try {
    const message = JSON.parse(event.data);

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

  scheduleReconnect();
}

// Handle WebSocket error
function handleError(error) {
  console.error("WebSocket error:", error);
}

// Send authentication message
function sendAuth() {
  send({ type: "auth" });
}

// Handle authentication result
function handleAuthResult(message) {
  if (message.status === "success") {
    state.authenticated = true;
    state.connectionState = "connected";
    state.reconnectDelay = CONFIG.reconnect.initialDelay;
    updateStatus("connected", "Connected");

    console.log("WebSocket authenticated successfully");
    subscribe({});
  } else {
    console.error("Authentication failed:", message.message);
    state.ws.close();
  }
}

// Send subscribe message
function subscribe(filters) {
  state.currentFilters = filters;
  send({ type: "subscribe", filters: filters });
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
  renderEvent(message.event);
}

// Render event to table
function renderEvent(event) {
  const row = document.createElement("tr");
  row.className = "event-row";
  row.dataset.eventId = event.id;
  if (event.level) {
    row.dataset.level = event.level;
  }

  const timestamp = formatTimestamp(event.timestamp);
  const level = event.level || "debug";
  const levelText = event.level || "-";
  const levelBadge = `<span class="level-badge ${escapeHtml(level)}">${escapeHtml(levelText)}</span>`;

  const message = event.message || "-";
  const displayMessage =
    message.length > 80 ? message.substring(0, 77) + "..." : message;

  row.innerHTML = `
    <td class="time">${timestamp}</td>
    <td class="source"><span class="source-badge">${escapeHtml(event.source)}</span></td>
    <td class="type">${escapeHtml(event.event_type)}</td>
    <td class="level">${levelBadge}</td>
    <td class="message">${escapeHtml(displayMessage)}</td>
  `;

  // Click handler for detail panel
  row.addEventListener("click", () => {
    showEventDetail(event, row);
  });

  // Check if row matches current filters
  const matchesFilter = rowMatchesFilter(row, state.currentFilters);
  if (!matchesFilter) {
    row.style.display = "none";
  }

  // Insert at top (newest first)
  elements.eventsBody.insertBefore(row, elements.eventsBody.firstChild);

  // Update count
  state.eventCount++;
  updateEventCount();

  // Auto-scroll if enabled
  if (elements.autoScroll.checked && matchesFilter) {
    row.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// Show event detail panel
function showEventDetail(event, row) {
  // Remove selection from previous row
  const previouslySelected = elements.eventsBody.querySelector(
    ".event-row.selected",
  );
  if (previouslySelected) {
    previouslySelected.classList.remove("selected");
  }

  // Mark new row as selected
  row.classList.add("selected");
  state.selectedEventId = event.id;

  // Populate detail fields
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

  // Show detail view
  elements.rightPanel.classList.add("has-selection");
}

// Hide event detail panel
function hideEventDetail() {
  // Remove row selection
  const selectedRow = elements.eventsBody.querySelector(".event-row.selected");
  if (selectedRow) {
    selectedRow.classList.remove("selected");
  }

  state.selectedEventId = null;
  elements.rightPanel.classList.remove("has-selection");
}

// Format timestamp for display
function formatTimestamp(isoTimestamp) {
  const date = new Date(isoTimestamp);
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
function updateStatus(statusState, text) {
  elements.statusDot.className = `status-dot ${statusState}`;
  elements.statusText.textContent = text;
}

// Update event count display
function updateEventCount() {
  const visible = elements.eventsBody.querySelectorAll(
    '.event-row:not([style*="display: none"])',
  ).length;
  const total = state.eventCount;

  if (visible === total) {
    elements.eventCount.textContent = `${total} events`;
  } else {
    elements.eventCount.textContent = `${visible} / ${total} events`;
  }
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
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
  }

  console.log(`Reconnecting in ${state.reconnectDelay / 1000}s...`);

  state.reconnectTimer = setTimeout(() => {
    connect();
    state.reconnectDelay = Math.min(
      state.reconnectDelay * CONFIG.reconnect.backoffMultiplier,
      CONFIG.reconnect.maxDelay,
    );
  }, state.reconnectDelay);
}

// Collect current filter values
function collectFilters() {
  const filters = {};

  const source = elements.filterSource.value.trim();
  if (source) {
    filters.source = source;
  }

  const eventType = elements.filterType.value.trim();
  if (eventType) {
    filters.event_type = eventType;
  }

  const activeLevels = Array.from(elements.levelChips)
    .filter((chip) => chip.classList.contains("active"))
    .map((chip) => chip.dataset.level);

  if (activeLevels.length < 4) {
    filters.levels = activeLevels;
  }

  const search = elements.filterSearch.value.trim();
  if (search) {
    filters.search = search;
  }

  return filters;
}

// Apply current filters
function applyFilters() {
  const filters = collectFilters();
  state.currentFilters = filters;
  filterTableRows(filters);
  updateEventCount();
}

// Clear all filters
function clearFilters() {
  elements.filterSource.value = "";
  elements.filterType.value = "";
  elements.filterSearch.value = "";

  elements.levelChips.forEach((chip) => {
    chip.classList.add("active");
  });

  state.currentFilters = {};
  filterTableRows({});
  updateEventCount();
}

// Filter table rows client-side
function filterTableRows(filters) {
  const rows = elements.eventsBody.querySelectorAll(".event-row");

  rows.forEach((row) => {
    const matchesFilter = rowMatchesFilter(row, filters);
    row.style.display = matchesFilter ? "" : "none";
  });
}

// Check if row matches filter criteria
function rowMatchesFilter(row, filters) {
  if (Object.keys(filters).length === 0) {
    return true;
  }

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

  if (filters.source && rowData.source !== filters.source) {
    return false;
  }

  if (filters.event_type && rowData.event_type !== filters.event_type) {
    return false;
  }

  if (filters.levels !== undefined) {
    if (filters.levels.length === 0) {
      return false;
    }
    const eventLevel = rowData.level === "-" ? "debug" : rowData.level;
    if (!filters.levels.includes(eventLevel)) {
      return false;
    }
  }

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
    const response = await fetch("/sources");

    if (!response.ok) {
      console.error("Failed to load sources:", response.status);
      return;
    }

    const data = await response.json();
    const sources = data.sources || [];

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
