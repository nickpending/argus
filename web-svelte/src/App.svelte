<script lang="ts">
  import { Activity, Settings, Download } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import websocket, { type ConnectionStatus } from './lib/stores/websocket.svelte';
  import eventsStore from './lib/stores/events.svelte';
  import sessionsStore from './lib/stores/sessions.svelte';
  import metricsStore from './lib/stores/metrics.svelte';
  import SessionTree from './lib/components/SessionTree.svelte';
  import EventTable from './lib/components/EventTable.svelte';
  import DetailPanel from './lib/components/DetailPanel.svelte';
  import MetricsBar from './lib/components/MetricsBar.svelte';
  import FilterBar from './lib/components/FilterBar.svelte';
  import CombinedTimeline from './lib/components/CombinedTimeline.svelte';

  let connectionStatus = $state<ConnectionStatus>('disconnected');

  // Sync connection status and update metrics from stores
  $effect(() => {
    const interval = setInterval(() => {
      connectionStatus = websocket.getStatus();
      metricsStore.updateMetrics();
    }, 100);
    return () => clearInterval(interval);
  });

  onMount(() => {
    // Initialize store handlers
    const unsubEvents = eventsStore.initializeHandlers();
    const unsubSessions = sessionsStore.initializeHandlers();

    // Load initial data from REST API, then connect WebSocket
    // Sessions must load first so events can update last_event_time for staleness detection
    sessionsStore.loadInitialData()
      .then(() => eventsStore.loadInitialEvents())
      .then(() => websocket.connect());

    return () => {
      unsubEvents();
      unsubSessions();
      websocket.disconnect();
    };
  });
</script>

<div class="app-grid">
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
  <div class="metrics-area">
    <MetricsBar />
  </div>

  <!-- Left Panel: Sessions -->
  <aside class="panel left-panel">
    <div class="panel-header">
      <h2>Sessions</h2>
    </div>
    <div class="panel-content">
      <SessionTree />
    </div>
  </aside>

  <!-- Center Panel: Filters + Events + Timeline -->
  <section class="center-area">
    <!-- Filter Bar -->
    <FilterBar />

    <!-- Events Table -->
    <EventTable />

    <!-- Timeline Section: Combined Swimlanes + Density -->
    <div class="timeline-section">
      <CombinedTimeline />
    </div>
  </section>

  <!-- Right Panel: Event Detail -->
  <aside class="panel right-panel">
    <DetailPanel />
  </aside>
</div>

<style>
  /* App Grid Layout */
  .app-grid {
    height: 100vh;
    display: grid;
    grid-template-areas:
      "header header header"
      "metrics metrics metrics"
      "left center right";
    grid-template-columns: minmax(240px, 280px) 1fr minmax(320px, 380px);
    grid-template-rows: var(--header-height) auto 1fr;
    overflow: hidden;
  }

  /* Header */
  .header {
    grid-area: header;
    background: var(--vw-bg-card);
    border-bottom: 1px solid var(--vw-border-bright);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.25rem;
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

  /* Metrics Area */
  .metrics-area {
    grid-area: metrics;
    border-bottom: 1px solid var(--vw-border);
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
    grid-area: left;
    border-right: 1px solid var(--vw-border);
  }

  .right-panel {
    grid-area: right;
    border-left: 1px solid var(--vw-border);
  }

  /* Center Area */
  .center-area {
    grid-area: center;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--vw-bg-card);
  }

  /* Timeline Section (Combined Swimlanes + Density) */
  .timeline-section {
    height: 300px;
    border-top: 1px solid var(--vw-border);
    flex-shrink: 0;
  }
</style>
