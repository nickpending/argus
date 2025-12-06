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
  currentTimeRange: "all", // "all", "1h", "24h", "7d", "custom"
  eventCount: 0,
  selectedEventId: null,
  selectedSessionId: null, // Selected session in tree for filtering
  selectedAgentId: null, // Selected agent in tree for filtering
  knownEventIds: new Set(), // Track rendered event IDs for deduplication
  isLoadingHistory: false, // Loading state for historical fetch
};

// DOM element references (cached on load)
const elements = {};

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  initializeEventListeners();
  loadSourceOptions();
  loadSessionOptions();
  loadSessionTree();
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
  elements.exportBtn = document.getElementById("export-btn");

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
  elements.filterSession = document.getElementById("filter-session");
  elements.eventTypeChips = document.querySelectorAll(
    ".event-type-chips .chip",
  );
  elements.filterSearch = document.getElementById("filter-search");
  elements.filterApply = document.getElementById("filter-apply");
  elements.filterClear = document.getElementById("filter-clear");
  elements.levelChips = document.querySelectorAll(".level-chips .chip");

  // Time range elements
  elements.timeRangeChips = document.querySelectorAll(
    ".time-range-chips .chip",
  );
  elements.timeRangeCustom = document.getElementById("time-range-custom");
  elements.filterTimeStart = document.getElementById("filter-time-start");
  elements.filterTimeEnd = document.getElementById("filter-time-end");

  // Session tree elements
  elements.sessionTree = document.getElementById("session-tree");
  elements.sessionCount = document.getElementById("session-count");
  elements.treeEmpty = document.getElementById("tree-empty");
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

  // Event type chip toggle buttons (auto-apply on click)
  elements.eventTypeChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
      applyFilters();
    });
  });

  // Level chip toggle buttons (auto-apply on click)
  elements.levelChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
      applyFilters();
    });
  });

  // Time range chip buttons (exclusive selection)
  elements.timeRangeChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      // Remove active from all time range chips
      elements.timeRangeChips.forEach((c) => c.classList.remove("active"));
      // Activate clicked chip
      chip.classList.add("active");

      const range = chip.dataset.range;
      state.currentTimeRange = range;

      // Show/hide custom datetime inputs
      if (range === "custom") {
        elements.timeRangeCustom.classList.add("visible");
      } else {
        elements.timeRangeCustom.classList.remove("visible");
      }

      applyFilters();
    });
  });

  // Custom time range inputs (apply on change)
  elements.filterTimeStart.addEventListener("change", () => {
    if (state.currentTimeRange === "custom") {
      applyFilters();
    }
  });
  elements.filterTimeEnd.addEventListener("change", () => {
    if (state.currentTimeRange === "custom") {
      applyFilters();
    }
  });

  // Filter apply button
  elements.filterApply.addEventListener("click", () => {
    applyFilters();
  });

  // Filter clear button
  elements.filterClear.addEventListener("click", () => {
    clearFilters();
  });

  // Apply filters on Enter key in search input
  elements.filterSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
  });

  // Export CSV button
  elements.exportBtn.addEventListener("click", exportCsv);

  // Session dropdown change
  elements.filterSession.addEventListener("change", () => {
    const sessionId = elements.filterSession.value;
    if (sessionId) {
      // Sync tree selection to dropdown
      syncTreeToDropdown(sessionId);
      state.selectedSessionId = sessionId;
      state.selectedAgentId = null;
    } else {
      // "All Sessions" selected - clear tree selection
      clearTreeSelection();
    }
    applyFilters();
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
  const event = message.event;

  // Deduplicate: skip if we already have this event
  if (state.knownEventIds.has(event.id)) {
    return;
  }

  // Track the event ID
  state.knownEventIds.add(event.id);

  // Render the event (filter check happens in renderEvent)
  renderEvent(event);
}

// Render event to table
function renderEvent(event) {
  const row = document.createElement("tr");
  row.className = "event-row";
  row.dataset.eventId = event.id;
  row.dataset.timestamp = event.timestamp;
  if (event.level) {
    row.dataset.level = event.level;
  }
  if (event.session_id) {
    row.dataset.sessionId = event.session_id;
  }
  if (event.agent_id) {
    row.dataset.agentId = event.agent_id;
  }

  const timestamp = formatTimestamp(event.timestamp);
  const level = event.level || "debug";
  const levelText = event.level || "-";
  const levelBadge = `<span class="level-badge ${escapeHtml(level)}">${escapeHtml(levelText)}</span>`;

  const message = event.message || "-";
  const displayMessage =
    message.length > 80 ? message.substring(0, 77) + "..." : message;

  // Extract project from data payload if available
  const project = event.data?.project || "-";

  row.innerHTML = `
    <td class="time">${timestamp}</td>
    <td class="source"><span class="source-badge">${escapeHtml(event.source)}</span></td>
    <td class="project">${escapeHtml(project)}</td>
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

  // Pretty-print JSON data with syntax highlighting
  elements.detailDataJson.innerHTML = highlightJson(event.data);

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

// Syntax highlight JSON for display
function highlightJson(data) {
  if (data === null || data === undefined) {
    return '<span class="json-null">null</span>';
  }

  const json = JSON.stringify(data, null, 2);

  // Escape HTML first, then apply highlighting
  const escaped = escapeHtml(json);

  // Apply syntax highlighting with regex
  return (
    escaped
      // Keys (property names before colon)
      .replace(/"([^"]+)":/g, '<span class="json-key">"$1"</span>:')
      // String values (after colon or in arrays)
      .replace(/: "([^"]*)"/g, ': <span class="json-string">"$1"</span>')
      .replace(/\["([^"]*)"/g, '[<span class="json-string">"$1"</span>')
      .replace(/, "([^"]*)"/g, ', <span class="json-string">"$1"</span>')
      // Numbers
      .replace(/: (-?\d+\.?\d*)/g, ': <span class="json-number">$1</span>')
      .replace(/\[(-?\d+\.?\d*)/g, '[<span class="json-number">$1</span>')
      .replace(/, (-?\d+\.?\d*)/g, ', <span class="json-number">$1</span>')
      // Booleans
      .replace(/: (true|false)/g, ': <span class="json-boolean">$1</span>')
      // Null
      .replace(/: (null)/g, ': <span class="json-null">$1</span>')
  );
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

  // Event type chips (multi-select)
  const activeEventTypes = Array.from(elements.eventTypeChips)
    .filter((chip) => chip.classList.contains("active"))
    .map((chip) => chip.dataset.eventType);

  if (activeEventTypes.length < 5) {
    filters.event_types = activeEventTypes;
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

  // Time range filter
  const timeRange = getTimeRange();
  if (timeRange.since) {
    filters.time_since = timeRange.since;
  }
  if (timeRange.until) {
    filters.time_until = timeRange.until;
  }

  // Session/agent tree selection
  if (state.selectedSessionId) {
    filters.session_id = state.selectedSessionId;
  }
  if (state.selectedAgentId) {
    filters.agent_id = state.selectedAgentId;
  }

  return filters;
}

// Calculate time range based on current selection
function getTimeRange() {
  const range = state.currentTimeRange;
  const now = new Date();

  switch (range) {
    case "1h":
      return { since: new Date(now.getTime() - 60 * 60 * 1000).toISOString() };
    case "24h":
      return {
        since: new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString(),
      };
    case "7d":
      return {
        since: new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      };
    case "custom": {
      const result = {};
      const startVal = elements.filterTimeStart.value;
      const endVal = elements.filterTimeEnd.value;
      if (startVal) {
        result.since = new Date(startVal).toISOString();
      }
      if (endVal) {
        result.until = new Date(endVal).toISOString();
      }
      return result;
    }
    default:
      // "all" - no time filter
      return {};
  }
}

// Apply current filters
function applyFilters() {
  const filters = collectFilters();
  state.currentFilters = filters;

  // If time range filter is active, fetch historical events from API
  if (filters.time_since || filters.time_until) {
    fetchHistoricalEvents(filters);
  } else {
    // No time filter - just filter existing DOM rows
    filterTableRows(filters);
    updateEventCount();
  }
}

// Clear all filters
function clearFilters() {
  elements.filterSource.value = "";
  elements.filterSearch.value = "";

  // Reset event type chips to all active
  elements.eventTypeChips.forEach((chip) => {
    chip.classList.add("active");
  });

  elements.levelChips.forEach((chip) => {
    chip.classList.add("active");
  });

  // Reset time range to "All"
  elements.timeRangeChips.forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.range === "all");
  });
  elements.timeRangeCustom.classList.remove("visible");
  elements.filterTimeStart.value = "";
  elements.filterTimeEnd.value = "";
  state.currentTimeRange = "all";

  // Clear session/agent tree selection
  clearTreeSelection();

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

  // Event type chips filtering (multi-select)
  if (filters.event_types !== undefined) {
    if (filters.event_types.length === 0) {
      return false;
    }
    if (!filters.event_types.includes(rowData.event_type)) {
      return false;
    }
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

  // Time range filtering
  if (filters.time_since || filters.time_until) {
    const eventTimestamp = row.dataset.timestamp;
    if (eventTimestamp) {
      const eventTime = new Date(eventTimestamp).getTime();
      if (filters.time_since) {
        const sinceTime = new Date(filters.time_since).getTime();
        if (eventTime < sinceTime) {
          return false;
        }
      }
      if (filters.time_until) {
        const untilTime = new Date(filters.time_until).getTime();
        if (eventTime > untilTime) {
          return false;
        }
      }
    }
  }

  // Session/agent tree filtering
  if (filters.session_id) {
    const rowSessionId = row.dataset.sessionId || "";
    if (rowSessionId !== filters.session_id) {
      return false;
    }
  }

  if (filters.agent_id) {
    const rowAgentId = row.dataset.agentId || "";
    if (rowAgentId !== filters.agent_id) {
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

// Load session options from API
async function loadSessionOptions() {
  try {
    const response = await fetch("/sessions");

    if (!response.ok) {
      console.error("Failed to load sessions:", response.status);
      return;
    }

    const data = await response.json();
    const sessions = data.sessions || [];

    // Clear existing options (keep "All Sessions")
    while (elements.filterSession.options.length > 1) {
      elements.filterSession.remove(1);
    }

    sessions.forEach((session) => {
      const option = document.createElement("option");
      option.value = session.id;
      // Display project name or truncated session ID
      const label = session.project || session.id.substring(0, 8);
      const status = session.status === "active" ? "●" : "○";
      option.textContent = `${status} ${label}`;
      elements.filterSession.appendChild(option);
    });

    console.log(`Loaded ${sessions.length} sessions for filter dropdown`);
  } catch (error) {
    console.error("Error loading sessions:", error);
  }
}

// Fetch historical events from API based on current filters
async function fetchHistoricalEvents(filters) {
  if (state.isLoadingHistory) {
    return; // Prevent concurrent fetches
  }

  state.isLoadingHistory = true;
  updateLoadingState(true);

  try {
    // Build query parameters
    const params = new URLSearchParams();

    if (filters.source) {
      params.append("source", filters.source);
    }
    if (filters.event_type) {
      params.append("event_type", filters.event_type);
    }
    if (filters.levels && filters.levels.length === 1) {
      // API only supports single level filter
      params.append("level", filters.levels[0]);
    }
    if (filters.time_since) {
      params.append("since", filters.time_since);
    }
    if (filters.time_until) {
      params.append("until", filters.time_until);
    }
    if (filters.session_id) {
      params.append("session_id", filters.session_id);
    }
    if (filters.agent_id) {
      params.append("agent_id", filters.agent_id);
    }
    params.append("limit", "500"); // Fetch more for historical view

    const url = `/events?${params.toString()}`;
    console.log("Fetching historical events:", url);

    const response = await fetch(url);

    if (!response.ok) {
      console.error("Failed to fetch events:", response.status);
      return;
    }

    const data = await response.json();
    const events = data.events || [];

    // Clear existing events and reset tracking
    clearEventsTable();
    state.knownEventIds.clear();
    state.eventCount = 0;

    // Render events (API returns newest first, so reverse for insertion)
    // Since renderEvent inserts at top, we render oldest first
    const reversedEvents = [...events].reverse();
    reversedEvents.forEach((event) => {
      state.knownEventIds.add(event.id);
      renderEventWithoutFilter(event); // Render without filter check (already filtered by API)
    });

    // Apply client-side filters for levels and search (API doesn't support these fully)
    filterTableRows(filters);
    updateEventCount();

    console.log(`Loaded ${events.length} historical events`);
  } catch (error) {
    console.error("Error fetching historical events:", error);
  } finally {
    state.isLoadingHistory = false;
    updateLoadingState(false);
  }
}

// Clear all events from table
function clearEventsTable() {
  elements.eventsBody.innerHTML = "";
  state.eventCount = 0;
  state.selectedEventId = null;
  elements.rightPanel.classList.remove("has-selection");
}

// Render event without applying filter check (for historical events already filtered by API)
function renderEventWithoutFilter(event) {
  const row = document.createElement("tr");
  row.className = "event-row";
  row.dataset.eventId = event.id;
  row.dataset.timestamp = event.timestamp;
  if (event.level) {
    row.dataset.level = event.level;
  }
  if (event.session_id) {
    row.dataset.sessionId = event.session_id;
  }
  if (event.agent_id) {
    row.dataset.agentId = event.agent_id;
  }

  const timestamp = formatTimestamp(event.timestamp);
  const level = event.level || "debug";
  const levelText = event.level || "-";
  const levelBadge = `<span class="level-badge ${escapeHtml(level)}">${escapeHtml(levelText)}</span>`;

  const message = event.message || "-";
  const displayMessage =
    message.length > 80 ? message.substring(0, 77) + "..." : message;

  const project = event.data?.project || "-";

  row.innerHTML = `
    <td class="time">${timestamp}</td>
    <td class="source"><span class="source-badge">${escapeHtml(event.source)}</span></td>
    <td class="project">${escapeHtml(project)}</td>
    <td class="type">${escapeHtml(event.event_type)}</td>
    <td class="level">${levelBadge}</td>
    <td class="message">${escapeHtml(displayMessage)}</td>
  `;

  // Click handler for detail panel
  row.addEventListener("click", () => {
    showEventDetail(event, row);
  });

  // Insert at top (newest first)
  elements.eventsBody.insertBefore(row, elements.eventsBody.firstChild);
  state.eventCount++;
}

// Update loading state indicator
function updateLoadingState(isLoading) {
  if (isLoading) {
    elements.eventCount.textContent = "Loading...";
    elements.eventsBody.classList.add("loading");
  } else {
    elements.eventsBody.classList.remove("loading");
    updateEventCount();
  }
}

// Export visible events as CSV
function exportCsv() {
  const visibleRows = elements.eventsBody.querySelectorAll(
    '.event-row:not([style*="display: none"])',
  );

  if (visibleRows.length === 0) {
    console.warn("No events to export");
    return;
  }

  // CSV header
  const headers = ["Time", "Source", "Project", "Type", "Level", "Message"];
  const csvRows = [headers.join(",")];

  // Extract data from visible rows
  visibleRows.forEach((row) => {
    const cells = row.querySelectorAll("td");
    const rowData = [
      cells[0]?.textContent || "", // Time
      cells[1]?.textContent || "", // Source
      cells[2]?.textContent || "", // Project
      cells[3]?.textContent || "", // Type
      cells[4]?.textContent || "", // Level
      cells[5]?.textContent || "", // Message
    ];

    // Escape fields for CSV (quote fields containing commas, quotes, or newlines)
    const escapedRow = rowData.map((field) => {
      if (field.includes(",") || field.includes('"') || field.includes("\n")) {
        return '"' + field.replace(/"/g, '""') + '"';
      }
      return field;
    });

    csvRows.push(escapedRow.join(","));
  });

  // Create and download CSV file
  const csvContent = csvRows.join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = `argus-events-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.csv`;
  link.click();

  URL.revokeObjectURL(url);
  console.log(`Exported ${visibleRows.length} events to CSV`);
}

// Load session tree from API
async function loadSessionTree() {
  try {
    // Fetch sessions
    const sessionsResponse = await fetch("/sessions");
    if (!sessionsResponse.ok) {
      console.error("Failed to load sessions:", sessionsResponse.status);
      return;
    }

    const sessionsData = await sessionsResponse.json();
    const sessions = sessionsData.sessions || [];

    // Fetch all agents (we'll group by session_id client-side)
    const agentsResponse = await fetch("/agents");
    if (!agentsResponse.ok) {
      console.error("Failed to load agents:", agentsResponse.status);
      return;
    }

    const agentsData = await agentsResponse.json();
    const agents = agentsData.agents || [];

    // Group agents by session_id
    const agentsBySession = {};
    agents.forEach((agent) => {
      if (agent.session_id) {
        if (!agentsBySession[agent.session_id]) {
          agentsBySession[agent.session_id] = [];
        }
        agentsBySession[agent.session_id].push(agent);
      }
    });

    // Render the tree
    renderSessionTree(sessions, agentsBySession);

    console.log(
      `Loaded ${sessions.length} sessions with ${agents.length} agents`,
    );
  } catch (error) {
    console.error("Error loading session tree:", error);
  }
}

// Render session tree to DOM
function renderSessionTree(sessions, agentsBySession) {
  // Update session count
  updateSessionCount(sessions.length);

  // Show/hide empty state
  if (sessions.length === 0) {
    elements.treeEmpty.style.display = "";
    return;
  }
  elements.treeEmpty.style.display = "none";

  // Clear existing tree items (keep empty state element)
  const existingItems = elements.sessionTree.querySelectorAll(".tree-item");
  existingItems.forEach((item) => item.remove());

  // Render each session
  sessions.forEach((session) => {
    const sessionAgents = agentsBySession[session.id] || [];
    const sessionElement = createSessionElement(session, sessionAgents);
    elements.sessionTree.appendChild(sessionElement);
  });
}

// Create session tree item element
function createSessionElement(session, agents) {
  const item = document.createElement("div");
  item.className = "tree-item session";
  item.dataset.sessionId = session.id;

  // Determine status class
  const statusClass = session.status === "active" ? "active" : "ended";

  // Session label - use project name or truncated session ID
  const label = session.project || session.id.substring(0, 8);

  // Agent count text
  const agentText = agents.length === 1 ? "1 agent" : `${agents.length} agents`;

  // Has agents to expand?
  const hasAgents = agents.length > 0;
  const expandedAttr = hasAgents ? 'aria-expanded="false"' : "";
  const leafClass = hasAgents ? "" : " leaf";

  item.innerHTML = `
    <button class="tree-toggle${leafClass}" ${expandedAttr}>
      ${hasAgents ? '<span class="toggle-icon"></span>' : ""}
      <span class="status-dot ${statusClass}"></span>
      <span class="tree-label">${escapeHtml(label)}</span>
      <span class="tree-meta">${escapeHtml(agentText)}</span>
    </button>
    ${hasAgents ? '<div class="tree-children"></div>' : ""}
  `;

  // Add agents to children container
  if (hasAgents) {
    const childrenContainer = item.querySelector(".tree-children");
    agents.forEach((agent) => {
      const agentElement = createAgentElement(agent, session.id);
      childrenContainer.appendChild(agentElement);
    });

    // Add expand/collapse handler to toggle icon only
    const toggleIcon = item.querySelector(".toggle-icon");
    if (toggleIcon) {
      toggleIcon.addEventListener("click", handleTreeToggle);
    }
  }

  // Add filter click handler to the button (entire row)
  const toggleButton = item.querySelector(".tree-toggle");
  toggleButton.addEventListener("click", (event) => {
    // Ignore if clicking on toggle icon (handled separately)
    if (event.target.classList.contains("toggle-icon")) {
      return;
    }
    handleSessionClick(session.id, item);
  });

  return item;
}

// Create agent tree item element
function createAgentElement(agent, sessionId) {
  const item = document.createElement("div");
  item.className = "tree-item agent";
  item.dataset.agentId = agent.id;
  item.dataset.sessionId = sessionId;

  // Determine status class
  let statusClass = "running";
  if (agent.status === "completed") {
    statusClass = "completed";
  } else if (agent.status === "failed") {
    statusClass = "failed";
  }

  // Agent label - use name or type
  const label = agent.name || agent.type || "agent";

  // Event count text
  const eventCount = agent.event_count || 0;
  const eventText = eventCount === 1 ? "1 event" : `${eventCount} events`;

  item.innerHTML = `
    <button class="tree-toggle leaf">
      <span class="status-dot ${statusClass}"></span>
      <span class="tree-label">${escapeHtml(label)}</span>
      <span class="tree-meta">${escapeHtml(eventText)}</span>
    </button>
  `;

  // Add filter click handler
  const toggleButton = item.querySelector(".tree-toggle");
  toggleButton.addEventListener("click", () => {
    handleAgentClick(agent.id, sessionId, item);
  });

  return item;
}

// Handle tree toggle click (expand/collapse)
function handleTreeToggle(event) {
  event.stopPropagation(); // Prevent triggering filter click
  const toggleIcon = event.currentTarget;
  const button = toggleIcon.closest(".tree-toggle");
  const isExpanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", !isExpanded);
}

// Handle session click for filtering
function handleSessionClick(sessionId, treeItem) {
  // Toggle selection - if already selected, deselect
  if (state.selectedSessionId === sessionId && !state.selectedAgentId) {
    clearTreeSelection();
  } else {
    // Clear previous selection and select this session
    clearTreeSelection();
    state.selectedSessionId = sessionId;
    state.selectedAgentId = null;
    treeItem.classList.add("selected");
    // Sync dropdown to match tree selection
    syncDropdownToTree(sessionId);
  }
  applyFilters();
}

// Handle agent click for filtering
function handleAgentClick(agentId, sessionId, treeItem) {
  // Toggle selection - if already selected, deselect
  if (state.selectedAgentId === agentId) {
    clearTreeSelection();
  } else {
    // Clear previous selection and select this agent (and its session)
    clearTreeSelection();
    state.selectedSessionId = sessionId;
    state.selectedAgentId = agentId;
    treeItem.classList.add("selected");
    // Sync dropdown to session (agent belongs to this session)
    syncDropdownToTree(sessionId);
  }
  applyFilters();
}

// Clear tree selection visual state and filter state
function clearTreeSelection() {
  state.selectedSessionId = null;
  state.selectedAgentId = null;

  // Remove .selected class from all tree items
  const selectedItems = elements.sessionTree.querySelectorAll(
    ".tree-item.selected",
  );
  selectedItems.forEach((item) => item.classList.remove("selected"));

  // Sync dropdown to cleared state
  elements.filterSession.value = "";
}

// Sync tree visual selection to match dropdown selection
function syncTreeToDropdown(sessionId) {
  // Remove existing selection
  const selectedItems = elements.sessionTree.querySelectorAll(
    ".tree-item.selected",
  );
  selectedItems.forEach((item) => item.classList.remove("selected"));

  // Find and select the session in tree
  const sessionItem = elements.sessionTree.querySelector(
    `.tree-item.session[data-session-id="${sessionId}"]`,
  );
  if (sessionItem) {
    sessionItem.classList.add("selected");
  }
}

// Sync dropdown to match tree selection (called when tree item clicked)
function syncDropdownToTree(sessionId) {
  elements.filterSession.value = sessionId || "";
}

// Update session count badge
function updateSessionCount(count) {
  elements.sessionCount.textContent = count;
}
