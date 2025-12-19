<script lang="ts">
  import { onMount } from 'svelte';
  import timelineStore, { type TimeBucket } from '../stores/timeline.svelte';

  // Container reference for measuring width
  let container: HTMLDivElement;
  let containerWidth: number = $state(800);

  // Reactive data from store
  let buckets: TimeBucket[] = $state([]);
  let maxCount: number = $state(0);

  // Hover state
  let hoveredBucketIndex: number | null = $state(null);
  let mouseX: number = $state(0);
  let mouseY: number = $state(0);

  // Chart dimensions
  const HEIGHT = 80;
  const PADDING = { top: 10, right: 10, bottom: 20, left: 10 };

  // Event type colours matching Voidwire palette
  const TYPE_COLORS: Record<string, string> = {
    tool: '#00D9FF',      // cyan
    agent: '#9F4DFF',     // vibrant-purple
    session: '#E6CCFF',   // purple
    response: '#4a9e6b',  // success
    prompt: '#a68a4d',    // warning
  };

  // Stack order (bottom to top)
  const STACK_ORDER = ['tool', 'agent', 'session', 'response', 'prompt'] as const;

  // Error marker colour
  const ERROR_COLOR = '#D95C5C';

  // Setup resize observer on mount
  onMount(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth = entry.contentRect.width;
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  });

  // Poll store for updates
  $effect(() => {
    const interval = setInterval(() => {
      timelineStore.updateBuckets();
      buckets = timelineStore.getBuckets();
      maxCount = timelineStore.getMaxCount();
    }, 100);
    return () => clearInterval(interval);
  });

  // Computed dimensions
  let innerWidth = $derived(containerWidth - PADDING.left - PADDING.right);
  let innerHeight = $derived(HEIGHT - PADDING.top - PADDING.bottom);

  // Build smooth bezier path using Catmull-Rom spline
  function buildSmoothPath(points: { x: number; y: number }[], tension: number = 0.3): string {
    if (points.length < 2) return '';
    if (points.length === 2) {
      return `M ${points[0].x.toFixed(2)},${points[0].y.toFixed(2)} L ${points[1].x.toFixed(2)},${points[1].y.toFixed(2)}`;
    }

    const chartBottom = PADDING.top + innerHeight;
    let path = `M ${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;

    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];

      // Calculate control points
      const cp1x = p1.x + ((p2.x - p0.x) * tension) / 3;
      let cp1y = p1.y + ((p2.y - p0.y) * tension) / 3;
      const cp2x = p2.x - ((p3.x - p1.x) * tension) / 3;
      let cp2y = p2.y - ((p3.y - p1.y) * tension) / 3;

      // Clamp control points to not go below chart floor
      cp1y = Math.min(cp1y, chartBottom);
      cp2y = Math.min(cp2y, chartBottom);

      path += ` C ${cp1x.toFixed(2)},${cp1y.toFixed(2)} ${cp2x.toFixed(2)},${cp2y.toFixed(2)} ${p2.x.toFixed(2)},${p2.y.toFixed(2)}`;
    }

    return path;
  }

  // Generate points for each event type (stacked)
  function generateStackedPaths() {
    if (buckets.length === 0 || maxCount === 0) return [];

    const bucketWidth = innerWidth / buckets.length;
    const paths: { type: string; linePath: string; areaPath: string; color: string }[] = [];

    for (const type of STACK_ORDER) {
      const points: { x: number; y: number }[] = [];

      for (let i = 0; i < buckets.length; i++) {
        const bucket = buckets[i];
        const x = PADDING.left + i * bucketWidth + bucketWidth / 2;

        // Calculate cumulative height up to and including this type
        let cumulativeCount = 0;
        for (const t of STACK_ORDER) {
          cumulativeCount += bucket[t];
          if (t === type) break;
        }

        const y = PADDING.top + innerHeight - (cumulativeCount / maxCount) * innerHeight;
        points.push({ x, y });
      }

      const linePath = buildSmoothPath(points);

      // Build area path (closes to baseline of this stack layer)
      let areaPath = '';
      if (points.length > 1) {
        // Get the baseline points (previous type's top, or chart floor)
        const baselinePoints: { x: number; y: number }[] = [];
        const typeIndex = STACK_ORDER.indexOf(type);

        for (let i = 0; i < buckets.length; i++) {
          const bucket = buckets[i];
          const x = PADDING.left + i * bucketWidth + bucketWidth / 2;

          // Cumulative up to but NOT including this type
          let cumulativeCount = 0;
          for (let t = 0; t < typeIndex; t++) {
            cumulativeCount += bucket[STACK_ORDER[t]];
          }

          const y = cumulativeCount > 0
            ? PADDING.top + innerHeight - (cumulativeCount / maxCount) * innerHeight
            : PADDING.top + innerHeight;
          baselinePoints.push({ x, y });
        }

        const baselinePath = buildSmoothPath(baselinePoints.slice().reverse());

        areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(2)},${baselinePoints[baselinePoints.length - 1].y.toFixed(2)} ${baselinePath.replace('M', 'L')} Z`;
      }

      paths.push({
        type,
        linePath,
        areaPath,
        color: TYPE_COLORS[type],
      });
    }

    return paths;
  }

  // Error markers
  function getErrorMarkers() {
    if (buckets.length === 0) return [];

    const bucketWidth = innerWidth / buckets.length;
    const markers: { x: number; y: number }[] = [];

    for (let i = 0; i < buckets.length; i++) {
      if (buckets[i].errors > 0) {
        const x = PADDING.left + i * bucketWidth + bucketWidth / 2;
        markers.push({ x, y: PADDING.top + 8 });
      }
    }

    return markers;
  }

  // Time labels
  function getTimeLabels() {
    if (buckets.length === 0) return [];

    const labels: { x: number; label: string }[] = [];
    const labelCount = 5;
    const bucketWidth = innerWidth / buckets.length;

    for (let i = 0; i < labelCount; i++) {
      const bucketIndex = Math.floor((i / (labelCount - 1)) * (buckets.length - 1));
      if (bucketIndex < buckets.length) {
        const bucket = buckets[bucketIndex];
        const x = PADDING.left + bucketIndex * bucketWidth + bucketWidth / 2;
        const time = new Date(bucket.startTime);
        const label = time.toLocaleTimeString('en-US', {
          hour12: false,
          hour: '2-digit',
          minute: '2-digit'
        });
        labels.push({ x, label });
      }
    }

    return labels;
  }

  // Handle mouse interactions
  function handleMouseMove(event: MouseEvent): void {
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const scaleX = containerWidth / rect.width;
    const x = (event.clientX - rect.left) * scaleX;

    mouseX = event.clientX;
    mouseY = event.clientY;

    const bucketWidth = innerWidth / buckets.length;
    const relativeX = x - PADDING.left;

    if (relativeX >= 0 && relativeX <= innerWidth && buckets.length > 0) {
      const index = Math.floor(relativeX / bucketWidth);
      hoveredBucketIndex = Math.min(index, buckets.length - 1);
    } else {
      hoveredBucketIndex = null;
    }
  }

  function handleMouseLeave(): void {
    hoveredBucketIndex = null;
  }

  // Get tooltip content
  function getTooltipContent(): { time: string; counts: string; errors: number } | null {
    if (hoveredBucketIndex === null || hoveredBucketIndex >= buckets.length) return null;

    const bucket = buckets[hoveredBucketIndex];
    const time = new Date(bucket.startTime).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });

    const parts: string[] = [];
    if (bucket.tool > 0) parts.push(`tool: ${bucket.tool}`);
    if (bucket.agent > 0) parts.push(`agent: ${bucket.agent}`);
    if (bucket.session > 0) parts.push(`session: ${bucket.session}`);
    if (bucket.response > 0) parts.push(`response: ${bucket.response}`);
    if (bucket.prompt > 0) parts.push(`prompt: ${bucket.prompt}`);

    return {
      time,
      counts: parts.length > 0 ? parts.join(', ') : 'no events',
      errors: bucket.errors
    };
  }

  // Reactive computations
  let stackedPaths = $derived(generateStackedPaths());
  let errorMarkers = $derived(getErrorMarkers());
  let timeLabels = $derived(getTimeLabels());
  let tooltipData = $derived(getTooltipContent());
  let hoverX = $derived(hoveredBucketIndex !== null && buckets.length > 0
    ? PADDING.left + hoveredBucketIndex * (innerWidth / buckets.length) + (innerWidth / buckets.length) / 2
    : 0);
</script>

<div class="timeline-container" bind:this={container}>
  <svg
    viewBox="0 0 {containerWidth} {HEIGHT}"
    class="timeline-svg"
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Event density timeline"
    onmousemove={handleMouseMove}
    onmouseleave={handleMouseLeave}
  >
    <defs>
      <!-- Glow filter for lines -->
      <filter id="line-glow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="2" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>

      <!-- Gradient definitions for each event type -->
      {#each STACK_ORDER as type}
        <linearGradient id="gradient-{type}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color={TYPE_COLORS[type]} stop-opacity="0.5" />
          <stop offset="30%" stop-color={TYPE_COLORS[type]} stop-opacity="0.25" />
          <stop offset="60%" stop-color={TYPE_COLORS[type]} stop-opacity="0.1" />
          <stop offset="100%" stop-color={TYPE_COLORS[type]} stop-opacity="0" />
        </linearGradient>
      {/each}
    </defs>

    <!-- Placeholder when no data -->
    {#if buckets.length === 0 || maxCount === 0}
      <text
        x={containerWidth / 2}
        y={HEIGHT / 2}
        text-anchor="middle"
        fill="rgba(128, 128, 128, 0.5)"
        font-size="12"
        font-family="Inter, sans-serif"
      >
        Waiting for events...
      </text>
    {:else}
      <!-- Stacked area fills and lines -->
      {#each stackedPaths as { type, linePath, areaPath, color }}
        {#if areaPath}
          <path d={areaPath} fill="url(#gradient-{type})" />
        {/if}
        {#if linePath}
          <path
            d={linePath}
            fill="none"
            stroke={color}
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            filter="url(#line-glow)"
          />
        {/if}
      {/each}

      <!-- Error markers -->
      {#each errorMarkers as marker}
        <circle cx={marker.x} cy={marker.y} r="4" fill={ERROR_COLOR} />
        <circle cx={marker.x} cy={marker.y} r="6" fill={ERROR_COLOR} fill-opacity="0.3" />
      {/each}

      <!-- Hover indicator -->
      {#if hoveredBucketIndex !== null}
        <line
          x1={hoverX}
          y1={PADDING.top}
          x2={hoverX}
          y2={PADDING.top + innerHeight}
          stroke="rgba(255, 255, 255, 0.3)"
          stroke-width="1"
          stroke-dasharray="4,4"
        />
        <circle cx={hoverX} cy={PADDING.top + innerHeight / 2} r="4" fill="white" />
      {/if}

      <!-- Time labels -->
      {#each timeLabels as { x, label }}
        <text
          {x}
          y={HEIGHT - 4}
          text-anchor="middle"
          fill="rgba(128, 128, 128, 0.8)"
          font-size="10"
          font-family="JetBrains Mono, monospace"
        >
          {label}
        </text>
      {/each}
    {/if}
  </svg>

  {#if tooltipData}
    <div
      class="tooltip"
      style="left: {mouseX}px; top: {mouseY - 60}px;"
    >
      <div class="tooltip-time">{tooltipData.time}</div>
      <div class="tooltip-counts">{tooltipData.counts}</div>
      {#if tooltipData.errors > 0}
        <div class="tooltip-errors">errors: {tooltipData.errors}</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .timeline-container {
    width: 100%;
    height: 80px;
    padding: 0 0.5rem;
    position: relative;
  }

  .timeline-svg {
    width: 100%;
    height: 100%;
    display: block;
    cursor: crosshair;
  }

  .tooltip {
    position: fixed;
    background: var(--vw-bg-elevated);
    border: 1px solid var(--vw-border-bright);
    border-radius: 4px;
    padding: 0.5rem 0.75rem;
    font-size: var(--text-xs);
    pointer-events: none;
    z-index: 100;
    transform: translateX(-50%);
    white-space: nowrap;
  }

  .tooltip-time {
    color: var(--vw-cyan);
    font-family: var(--font-mono);
    margin-bottom: 0.25rem;
  }

  .tooltip-counts {
    color: var(--vw-text);
  }

  .tooltip-errors {
    color: var(--vw-danger);
    margin-top: 0.25rem;
  }
</style>
