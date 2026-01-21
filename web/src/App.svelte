<script lang="ts">
  import { Activity, Settings, Download, Users, Zap, AlertTriangle } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import websocket, { type ConnectionStatus } from './lib/stores/websocket.svelte';
  import eventsStore from './lib/stores/events.svelte';
  import sessionsStore from './lib/stores/sessions.svelte';
  import metricsStore, { type Metrics } from './lib/stores/metrics.svelte';
  import SessionTree from './lib/components/SessionTree.svelte';
  import EventTable from './lib/components/EventTable.svelte';
  import DetailPanel from './lib/components/DetailPanel.svelte';
  import FilterBar from './lib/components/FilterBar.svelte';
  import CombinedTimeline from './lib/components/CombinedTimeline.svelte';

  let connectionStatus = $state<ConnectionStatus>('disconnected');
  let metrics = $state<Metrics>({
    activeSessions: 0,
    eventsPerMin: 0,
    errorCount: 0,
    avgLatency: '—',
  });

  // Sync connection status and update metrics from stores
  $effect(() => {
    const interval = setInterval(() => {
      connectionStatus = websocket.getStatus();
      metricsStore.updateMetrics();
      metrics = metricsStore.getMetrics();
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
        <span class="status-text">{connectionStatus === 'connected' ? 'connected' : connectionStatus === 'connecting' ? 'connecting...' : 'disconnected'}</span>
      </div>
      <div class="header-metrics">
        <span class="metric"><Users size={14} /><span class="metric-value">{metrics.activeSessions}</span></span>
        <span class="metric"><Zap size={14} /><span class="metric-value">{metrics.eventsPerMin}</span>/min</span>
        <span class="metric" class:has-errors={metrics.errorCount > 0}><AlertTriangle size={14} /><span class="metric-value">{metrics.errorCount}</span></span>
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
      "left center right";
    grid-template-columns: minmax(240px, 280px) 1fr minmax(320px, 380px);
    grid-template-rows: var(--header-height) 1fr;
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

  /* Header Metrics (inline) */
  .header-metrics {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding-left: 1rem;
    border-left: 1px solid var(--vw-border);
    margin-left: 0.5rem;
  }

  .metric {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: var(--text-sm);
    color: var(--vw-gray);
    white-space: nowrap;
  }

  .metric-value {
    font-weight: 600;
    color: var(--vw-cyan);
  }

  .metric.has-errors .metric-value {
    color: var(--vw-danger);
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
