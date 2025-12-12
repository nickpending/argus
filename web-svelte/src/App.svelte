<script lang="ts">
  import { Activity, Settings, Download } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import websocket, { type ConnectionStatus } from './lib/stores/websocket.svelte';
  import eventsStore from './lib/stores/events.svelte';
  import sessionsStore from './lib/stores/sessions.svelte';

  let connectionStatus = $state<ConnectionStatus>('disconnected');
  let eventCount = $state(0);
  let sessionCount = $state(0);

  // Sync connection status and counts from stores
  $effect(() => {
    const interval = setInterval(() => {
      connectionStatus = websocket.getStatus();
      eventCount = eventsStore.getEventCount();
      sessionCount = sessionsStore.getSessions().length;
    }, 100);
    return () => clearInterval(interval);
  });

  onMount(() => {
    // Initialize store handlers
    const unsubEvents = eventsStore.initializeHandlers();
    const unsubSessions = sessionsStore.initializeHandlers();

    // Connect to WebSocket
    websocket.connect();

    return () => {
      unsubEvents();
      unsubSessions();
      websocket.disconnect();
    };
  });
</script>

<header class="header">
  <div class="header-left">
    <h1 class="logo">
      <Activity size={24} strokeWidth={2} />
      ARGUS
    </h1>
    <div class="status-indicator">
      <span class="status-dot {connectionStatus}"></span>
      <span class="status-text">{connectionStatus === 'connected' ? 'Connected' : connectionStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}</span>
    </div>
  </div>
  <div class="header-controls">
    <button class="header-btn">
      <Settings size={18} />
      settings
    </button>
    <button class="header-btn">
      <Download size={18} />
      export
    </button>
  </div>
</header>

<!-- Metrics Bar -->
<div class="metrics-bar">
  <div class="metric-card">
    <span class="metric-label">Sessions</span>
    <span class="metric-value">{sessionCount}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">Events</span>
    <span class="metric-value">{eventCount}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">Errors</span>
    <span class="metric-value">0</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">Avg Latency</span>
    <span class="metric-value">&mdash;</span>
  </div>
</div>

<main class="main-container">
  <!-- Left Panel: Sessions -->
  <aside class="panel left-panel">
    <div class="panel-header">
      <h2>Sessions</h2>
    </div>
    <div class="panel-content">
      <p class="placeholder">Session tree</p>
    </div>
  </aside>

  <!-- Center Panel: Filters + Events + Timeline -->
  <section class="center-area">
    <!-- Filter Bar -->
    <div class="filter-bar">
      <select class="filter-select">
        <option>Source: All</option>
      </select>
      <select class="filter-select">
        <option>Project: All</option>
      </select>
      <select class="filter-select">
        <option>Type: All</option>
      </select>
      <select class="filter-select">
        <option>Level: All</option>
      </select>
      <input type="text" class="filter-search" placeholder="Search events..." />
      <div class="time-range-btns">
        <button class="time-btn active">1h</button>
        <button class="time-btn">24h</button>
        <button class="time-btn">7d</button>
      </div>
    </div>

    <!-- Events Table -->
    <div class="events-panel">
      <table class="events-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Source</th>
            <th>Project</th>
            <th>Type</th>
            <th>Level</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr class="placeholder-row">
            <td colspan="6">Events will appear here</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Timeline -->
    <div class="timeline-panel">
      <div class="timeline-header">Event Density Timeline</div>
      <div class="timeline-canvas">
        <p class="placeholder">Canvas timeline</p>
      </div>
    </div>
  </section>

  <!-- Right Panel: Event Detail -->
  <aside class="panel right-panel">
    <div class="panel-header">
      <h2>Event Detail</h2>
    </div>
    <div class="panel-content">
      <p class="placeholder">Select an event to view details</p>
    </div>
  </aside>
</main>

<style>
  /* Header */
  .header {
    height: var(--header-height);
    background: var(--vw-bg-card);
    border-bottom: 1px solid var(--vw-border-bright);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.25rem;
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }

  .logo {
    font-size: var(--text-xl);
    font-weight: 700;
    letter-spacing: 0.15em;
    color: var(--vw-cyan);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .header-controls {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .header-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: var(--vw-bg-elevated);
    border: 1px solid var(--vw-border);
    border-radius: 4px;
    color: var(--vw-text);
    font-size: var(--text-sm);
    text-transform: lowercase;
    cursor: pointer;
    transition: border-color var(--transition-fast), background var(--transition-fast);
  }

  .header-btn:hover {
    border-color: var(--vw-cyan);
    background: var(--vw-cyan-bg);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: var(--text-sm);
    padding: 0.375rem 0.75rem;
    background: var(--vw-bg-elevated);
    border: 1px solid var(--vw-border);
    border-radius: 4px;
    text-transform: lowercase;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--vw-danger);
  }

  .status-dot.connected {
    background: var(--vw-success);
  }

  .status-dot.connecting {
    background: var(--vw-warning);
    animation: pulse 1s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .status-text {
    color: var(--vw-gray);
  }

  /* Metrics Bar */
  .metrics-bar {
    display: flex;
    gap: 1rem;
    padding: 1rem 1.25rem;
    background: var(--vw-bg-deep);
    border-bottom: 1px solid var(--vw-border);
    flex-shrink: 0;
  }

  .metric-card {
    flex: 1;
    padding: 0.75rem 1rem;
    background: var(--vw-bg-card);
    border: 1px solid var(--vw-border);
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    transition: border-color var(--transition-fast);
  }

  .metric-card:hover {
    border-color: var(--vw-border-bright);
  }

  .metric-label {
    font-size: var(--text-xs);
    color: var(--vw-gray);
    text-transform: lowercase;
    letter-spacing: 0.05em;
  }

  .metric-value {
    font-size: var(--text-xl);
    font-weight: 600;
    color: var(--vw-white);
  }

  /* Main Container */
  .main-container {
    flex: 1;
    display: grid;
    grid-template-columns: var(--panel-left-width) 1fr var(--panel-right-width);
    gap: var(--panel-gap);
    overflow: hidden;
  }

  /* Panels */
  .panel {
    background: var(--vw-bg-card);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .panel-header {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--vw-border);
    flex-shrink: 0;
  }

  .panel-header h2 {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--vw-gray);
    text-transform: lowercase;
    letter-spacing: 0.05em;
  }

  .panel-content {
    flex: 1;
    overflow: auto;
    padding: 1rem;
  }

  .placeholder {
    color: var(--vw-gray);
    font-size: var(--text-sm);
    text-align: center;
    padding: 2rem;
  }

  .left-panel {
    border-right: 1px solid var(--vw-border);
  }

  .right-panel {
    border-left: 1px solid var(--vw-border);
  }

  /* Center Area */
  .center-area {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--vw-bg-card);
  }

  /* Filter Bar */
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--vw-border);
    flex-shrink: 0;
  }

  .filter-select {
    padding: 0.5rem 0.75rem;
    background: var(--vw-bg-elevated);
    border: 1px solid var(--vw-border);
    border-radius: 4px;
    color: var(--vw-text);
    font-size: var(--text-sm);
    text-transform: lowercase;
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }

  .filter-select:hover {
    border-color: var(--vw-border-bright);
  }

  .filter-select:focus {
    border-color: var(--vw-cyan);
    outline: none;
  }

  .filter-search {
    flex: 1;
    padding: 0.5rem 0.75rem;
    background: var(--vw-bg-elevated);
    border: 1px solid var(--vw-border);
    border-radius: 4px;
    color: var(--vw-text);
    font-size: var(--text-sm);
    transition: border-color var(--transition-fast);
  }

  .filter-search:hover {
    border-color: var(--vw-border-bright);
  }

  .filter-search:focus {
    border-color: var(--vw-cyan);
    outline: none;
  }

  .filter-search::placeholder {
    color: var(--vw-gray);
    text-transform: lowercase;
  }

  .time-range-btns {
    display: flex;
    gap: 0;
  }

  .time-btn {
    padding: 0.5rem 0.75rem;
    background: var(--vw-bg-elevated);
    border: 1px solid var(--vw-border);
    color: var(--vw-gray);
    font-size: var(--text-sm);
    text-transform: lowercase;
    cursor: pointer;
    margin-left: -1px;
    transition: border-color var(--transition-fast), background var(--transition-fast);
  }

  .time-btn:first-child {
    margin-left: 0;
    border-radius: 4px 0 0 4px;
  }

  .time-btn:last-child {
    border-radius: 0 4px 4px 0;
  }

  .time-btn.active {
    background: var(--vw-cyan-bg);
    border-color: var(--vw-cyan);
    color: var(--vw-cyan);
    z-index: 1;
  }

  .time-btn:hover:not(.active) {
    border-color: var(--vw-border-bright);
    background: var(--vw-bg-card);
  }

  /* Events Panel */
  .events-panel {
    flex: 1;
    overflow: auto;
  }

  .events-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }

  .events-table th {
    position: sticky;
    top: 0;
    background: var(--vw-bg-elevated);
    padding: 0.75rem 1rem;
    text-align: left;
    font-weight: 500;
    color: var(--vw-gray);
    text-transform: lowercase;
    font-size: var(--text-xs);
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--vw-border);
  }

  .events-table td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--vw-border);
    color: var(--vw-text);
  }

  .placeholder-row td {
    text-align: center;
    color: var(--vw-gray);
    padding: 2rem;
  }

  /* Timeline Panel */
  .timeline-panel {
    height: 120px;
    border-top: 1px solid var(--vw-border);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
  }

  .timeline-header {
    padding: 0.5rem 1rem;
    font-size: var(--text-xs);
    color: var(--vw-gray);
    text-transform: lowercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--vw-border);
  }

  .timeline-canvas {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
</style>
