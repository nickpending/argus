<script lang="ts">
  import { onMount } from 'svelte';
  import timelineStore, { type TimeBucket } from '../stores/timeline.svelte';

  // Canvas element reference
  let canvas: HTMLCanvasElement;
  let container: HTMLDivElement;
  let containerWidth: number = $state(0);

  // Reactive data from store
  let buckets: TimeBucket[] = $state([]);
  let maxCount: number = $state(0);

  // Hover state
  let hoveredBucketIndex: number | null = $state(null);
  let mouseX: number = $state(0);
  let mouseY: number = $state(0);

  // Chart dimensions (stored for hit detection)
  const PADDING = { top: 10, right: 10, bottom: 25, left: 10 };

  // Event type colours (semi-transparent for stacking)
  const TYPE_COLORS = {
    tool: 'rgba(0, 217, 255, 0.6)',      // cyan
    agent: 'rgba(159, 77, 255, 0.6)',     // vibrant-purple
    session: 'rgba(230, 204, 255, 0.6)', // purple
    response: 'rgba(74, 158, 107, 0.6)', // success
    prompt: 'rgba(166, 138, 77, 0.6)',   // warning
  };

  // Error marker colour (--vw-danger)
  const ERROR_COLOR = 'rgb(217, 92, 92)';

  // Stack order (bottom to top)
  const STACK_ORDER: (keyof typeof TYPE_COLORS)[] = [
    'tool', 'agent', 'session', 'response', 'prompt'
  ];

  // Setup resize observer on mount
  onMount(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth = entry.contentRect.width;
        updateCanvasSize();
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

  // Redraw canvas when data or size changes
  $effect(() => {
    if (canvas && containerWidth > 0) {
      drawChart();
    }
  });

  // Redraw when hover changes
  $effect(() => {
    if (canvas && containerWidth > 0 && hoveredBucketIndex !== null) {
      drawChart();
    }
  });

  function handleMouseMove(event: MouseEvent): void {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;

    mouseX = event.clientX;
    mouseY = event.clientY;

    // Calculate which bucket is hovered
    const chartWidth = containerWidth - PADDING.left - PADDING.right;
    const bucketWidth = chartWidth / buckets.length;
    const relativeX = x - PADDING.left;

    if (relativeX >= 0 && relativeX <= chartWidth && buckets.length > 0) {
      const index = Math.floor(relativeX / bucketWidth);
      hoveredBucketIndex = Math.min(index, buckets.length - 1);
    } else {
      hoveredBucketIndex = null;
    }

    drawChart();
  }

  function handleMouseLeave(): void {
    hoveredBucketIndex = null;
    drawChart();
  }

  function drawChart(): void {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = containerWidth;
    const height = 80;

    // Clear canvas
    ctx.clearRect(0, 0, width * dpr, height * dpr);
    ctx.save();
    ctx.scale(dpr, dpr);

    const chartWidth = width - PADDING.left - PADDING.right;
    const chartHeight = height - PADDING.top - PADDING.bottom;

    // If no data, show placeholder
    if (buckets.length === 0 || maxCount === 0) {
      ctx.fillStyle = 'rgba(128, 128, 128, 0.5)';
      ctx.font = '12px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Waiting for events...', width / 2, height / 2);
      ctx.restore();
      return;
    }

    const bucketWidth = chartWidth / buckets.length;

    // Draw stacked areas for each event type
    for (const type of STACK_ORDER) {
      ctx.fillStyle = TYPE_COLORS[type];
      ctx.beginPath();

      // Start at bottom-left
      ctx.moveTo(PADDING.left, PADDING.top + chartHeight);

      // Draw top edge of this type's area
      for (let i = 0; i < buckets.length; i++) {
        const bucket = buckets[i];
        const x = PADDING.left + i * bucketWidth + bucketWidth / 2;

        // Calculate cumulative height up to and including this type
        let cumulativeCount = 0;
        for (const t of STACK_ORDER) {
          cumulativeCount += bucket[t];
          if (t === type) break;
        }

        const y = PADDING.top + chartHeight - (cumulativeCount / maxCount) * chartHeight;

        if (i === 0) {
          ctx.lineTo(PADDING.left, y);
        }
        ctx.lineTo(x, y);

        if (i === buckets.length - 1) {
          ctx.lineTo(PADDING.left + chartWidth, y);
        }
      }

      // Draw bottom edge (previous type's top, or baseline)
      for (let i = buckets.length - 1; i >= 0; i--) {
        const bucket = buckets[i];
        const x = PADDING.left + i * bucketWidth + bucketWidth / 2;

        // Calculate cumulative height up to but NOT including this type
        let cumulativeCount = 0;
        for (const t of STACK_ORDER) {
          if (t === type) break;
          cumulativeCount += bucket[t];
        }

        const y = PADDING.top + chartHeight - (cumulativeCount / maxCount) * chartHeight;

        if (i === buckets.length - 1) {
          ctx.lineTo(PADDING.left + chartWidth, y);
        }
        ctx.lineTo(x, y);

        if (i === 0) {
          ctx.lineTo(PADDING.left, y);
        }
      }

      ctx.closePath();
      ctx.fill();
    }

    // Draw error markers as red dots
    const errorMarkerY = PADDING.top + 8; // Fixed position near top of chart
    const errorMarkerRadius = 4;

    for (let i = 0; i < buckets.length; i++) {
      const bucket = buckets[i];
      if (bucket.errors > 0) {
        const x = PADDING.left + i * bucketWidth + bucketWidth / 2;

        // Draw filled circle
        ctx.fillStyle = ERROR_COLOR;
        ctx.beginPath();
        ctx.arc(x, errorMarkerY, errorMarkerRadius, 0, Math.PI * 2);
        ctx.fill();

        // Add subtle glow for visibility
        ctx.strokeStyle = 'rgba(217, 92, 92, 0.4)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, errorMarkerY, errorMarkerRadius + 2, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    // Draw hover indicator line and highlight
    if (hoveredBucketIndex !== null && hoveredBucketIndex < buckets.length) {
      const hoverX = PADDING.left + hoveredBucketIndex * bucketWidth + bucketWidth / 2;

      // Vertical indicator line
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(hoverX, PADDING.top);
      ctx.lineTo(hoverX, PADDING.top + chartHeight);
      ctx.stroke();

      // Dot at cursor position
      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.arc(hoverX, PADDING.top + chartHeight / 2, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Draw time labels on x-axis
    ctx.fillStyle = 'rgba(128, 128, 128, 0.8)';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';

    // Show 5 time labels evenly distributed
    const labelCount = 5;
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
        ctx.fillText(label, x, height - 5);
      }
    }

    ctx.restore();
  }

  // Update canvas size for high-DPI displays
  function updateCanvasSize(): void {
    if (!canvas || containerWidth <= 0) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = containerWidth * dpr;
    canvas.height = 80 * dpr;
    canvas.style.width = `${containerWidth}px`;
    canvas.style.height = '80px';

    drawChart();
  }

  // Format tooltip content
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

  // Reactive tooltip data
  let tooltipData = $derived(getTooltipContent());
</script>

<div class="timeline-container" bind:this={container}>
  <canvas
    bind:this={canvas}
    onmousemove={handleMouseMove}
    onmouseleave={handleMouseLeave}
  ></canvas>

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

  canvas {
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
