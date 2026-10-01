export function createRenderScheduler({
  handlers,
  order = Object.keys(handlers),
  schedule = callback => (
    typeof document !== 'undefined' && document.hidden
      ? setTimeout(callback, 0)
      : requestAnimationFrame(callback)
  ),
  onFlush = null
}) {
  const pending = new Set();
  let scheduled = false;

  function flush() {
    scheduled = false;
    const work = new Set(pending);
    pending.clear();
    const started = typeof performance !== 'undefined' ? performance.now() : 0;
    for (const domain of order) {
      if (!work.has(domain)) continue;
      handlers[domain]?.();
    }
    if (onFlush) {
      const ended = typeof performance !== 'undefined' ? performance.now() : started;
      onFlush({domains: [...work], durationMs: Math.max(0, ended - started)});
    }
  }

  function request(domains = order) {
    for (const domain of domains) {
      if (!(domain in handlers)) throw new Error(`Unknown render domain: ${domain}`);
      pending.add(domain);
    }
    if (!scheduled) {
      scheduled = true;
      schedule(flush);
    }
  }

  return Object.freeze({
    request,
    flush,
    pendingDomains: () => [...pending],
    get scheduled() {
      return scheduled;
    }
  });
}
