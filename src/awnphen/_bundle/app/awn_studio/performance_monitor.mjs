const percentile = (values, ratio) => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * ratio))];
};

export function createPerformanceMonitor({
  enabled = new URLSearchParams(globalThis.location?.search ?? '').has('perf'),
  sampleWindowMs = 10_000
} = {}) {
  if (!enabled) {
    return Object.freeze({
      enabled: false,
      start: () => 0,
      end: () => {},
      record: () => {},
      count: () => {},
      measureAction: (_name, fn) => fn(),
      measureActionAsync: async (_name, fn) => await fn(),
      snapshot: () => ({enabled: false}),
      reset: () => {},
      dispose: () => {}
    });
  }

  const measures = new Map();
  const counters = new Map();
  const events = [];
  const longTasks = [];
  const now = () => performance.now();

  const trim = entries => {
    const cutoff = now() - sampleWindowMs;
    while (entries.length && entries[0].time < cutoff) entries.shift();
  };

  const record = (map, name, value) => {
    let values = map.get(name);
    if (!values) map.set(name, values = []);
    values.push(value);
    if (values.length > 200) values.splice(0, values.length - 200);
  };

  try {
    const observer = new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        events.push({time: now(), duration: entry.duration, name: entry.name});
      }
      trim(events);
    });
    observer.observe({type: 'event', buffered: true, durationThreshold: 16});
  } catch {}

  try {
    const observer = new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        longTasks.push({time: now(), duration: entry.duration});
      }
      trim(longTasks);
    });
    observer.observe({type: 'longtask', buffered: true});
  } catch {}

  const panel = document.createElement('aside');
  panel.id = 'performance-monitor';
  panel.style.cssText = [
    'position:fixed','right:10px','bottom:10px','z-index:99999',
    'min-width:245px','max-width:320px','padding:10px 12px',
    'background:rgba(17,24,39,.9)','color:#f3f4f6','border-radius:8px',
    'font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace',
    'box-shadow:0 4px 18px rgba(0,0,0,.28)','pointer-events:none'
  ].join(';');
  document.body.appendChild(panel);

  function snapshot() {
    trim(events); trim(longTasks);
    const eventDurations = events.map(item => item.duration);
    const slowestEvent = events.reduce(
      (slowest, item) => !slowest || item.duration > slowest.duration ? item : slowest,
      null
    );
    const measureSummary = {};
    for (const [name, values] of measures) {
      measureSummary[name] = {
        last: values.at(-1) ?? 0,
        p95: percentile(values, .95),
        max: Math.max(...values)
      };
    }
    return {
      enabled: true,
      event_p50_ms: percentile(eventDurations, .5),
      event_p95_ms: percentile(eventDurations, .95),
      event_max_ms: eventDurations.length ? Math.max(...eventDurations) : 0,
      slowest_event_name: slowestEvent?.name ?? null,
      long_tasks_10s: longTasks.length,
      long_task_ms_10s: longTasks.reduce((sum, item) => sum + item.duration, 0),
      heap_mb: performance.memory?.usedJSHeapSize ? performance.memory.usedJSHeapSize / 1024 / 1024 : null,
      measures: measureSummary,
      counters: Object.fromEntries(counters)
    };
  }

  function renderPanel() {
    const s = snapshot();
    const heap = s.heap_mb == null ? 'n/a' : s.heap_mb.toFixed(1);
    const rows = [
      '<strong>Awn Studio Performance</strong>',
      `Event p50 / p95: ${s.event_p50_ms.toFixed(1)} / ${s.event_p95_ms.toFixed(1)} ms`,
      `Slowest event: ${s.event_max_ms.toFixed(1)} ms${s.slowest_event_name ? ` (${s.slowest_event_name})` : ''}`,
      `Long tasks (10s): ${s.long_tasks_10s} / ${s.long_task_ms_10s.toFixed(0)} ms`,
      `JS heap: ${heap} MB`,
      'Target: p95 < 50 ms · long tasks = 0'
    ];
    for (const name of [
      'render.flush',
      'render.panels',
      'render.images',
      'render.canvas',
      'render.tools',
      'asset.load',
      'inference.load',
      'persist.page',
      'persist.full',
      'action.select',
      'action.deselect',
      'action.double-click',
      'action.delete',
      'action.undo',
      'action.redo',
      'action.switch-page',
      'action.switch-layer',
      'action.drag-node-frame'
    ]) {
      const item = s.measures[name];
      if (item) rows.push(`${name}: ${item.last.toFixed(1)} ms (p95 ${item.p95.toFixed(1)})`);
    }
    panel.innerHTML = rows.join('<br>');
  }

  function measureAction(name, fn) {
    const started = now();
    try {
      return fn();
    } finally {
      record(measures, `action.${name}`, Math.max(0, now() - started));
    }
  }

  async function measureActionAsync(name, fn) {
    const started = now();
    try {
      return await fn();
    } finally {
      record(measures, `action.${name}`, Math.max(0, now() - started));
    }
  }

  function reset() {
    measures.clear();
    counters.clear();
    events.length = 0;
    longTasks.length = 0;
    renderPanel();
  }

  const timer = setInterval(renderPanel, 1000);
  let disposed = false;
  function dispose() {
    if (disposed) return;
    disposed = true;
    clearInterval(timer);
    panel.remove?.();
    if (globalThis.__awnPerf?.snapshot === snapshot) delete globalThis.__awnPerf;
  }
  globalThis.addEventListener?.('pagehide', dispose, {once: true});

  const api = Object.freeze({
    enabled: true,
    start: now,
    end(name, started) {
      record(measures, name, Math.max(0, now() - started));
    },
    record(name, durationMs) {
      record(measures, name, Math.max(0, Number(durationMs) || 0));
    },
    count(name, amount = 1) {
      counters.set(name, (counters.get(name) ?? 0) + amount);
    },
    measureAction,
    measureActionAsync,
    snapshot,
    reset,
    dispose
  });

  globalThis.__awnPerf = Object.freeze({snapshot, reset});
  renderPanel();
  return api;
}
