<script lang="ts">
  import metricsStore, { type Metrics } from '../stores/metrics.svelte';

  let metrics: Metrics = $state({
    activeSessions: 0,
    eventsPerMin: 0,
    errorCount: 0,
    avgLatency: '—',
  });

  // Poll metrics store for updates
  $effect(() => {
    const interval = setInterval(() => {
      metrics = metricsStore.getMetrics();
    }, 100);
    return () => clearInterval(interval);
  });
</script>

<div class="metrics-bar">
  <div class="metric-card">
    <span class="metric-label">active sessions</span>
    <span class="metric-value">{metrics.activeSessions}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">events/min</span>
    <span class="metric-value">{metrics.eventsPerMin}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">errors</span>
    <span class="metric-value" class:has-errors={metrics.errorCount > 0}>{metrics.errorCount}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">avg latency</span>
    <span class="metric-value">{metrics.avgLatency}</span>
  </div>
</div>

<style>
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
    color: var(--vw-cyan);
  }

  .metric-value.has-errors {
    color: var(--vw-danger);
  }
</style>
