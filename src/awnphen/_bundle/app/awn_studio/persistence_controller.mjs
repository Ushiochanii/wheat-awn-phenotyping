export function createPersistenceController({
  store,
  getProject,
  encodeProject,
  debounceMs = 280,
  schedule = (fn, ms) => setTimeout(fn, ms),
  cancel = timer => clearTimeout(timer),
  onStatus = () => {},
  onError = () => {},
  onMeasure = () => {}
}) {
  const dirtyPageIds = new Set();
  let timer = null;
  let fullPending = false;
  let mutationVersion = 0;
  let running = null;

  const isDirty = () => Boolean(timer || running || fullPending || dirtyPageIds.size);

  async function persistNow() {
    if (running) return running;
    if (!fullPending && !dirtyPageIds.size) {
      onStatus('saved');
      return;
    }

    const version = mutationVersion;
    const full = fullPending;
    fullPending = false;
    const ids = [...dirtyPageIds];
    dirtyPageIds.clear();
    const started = performance.now();

    running = (async () => {
      try {
        if (full) {
          await store.saveCurrent(encodeProject(getProject()));
        } else {
          const project = getProject();
          const pages = ids.map(id => project.pages.find(page => page.id === id)).filter(Boolean);
          if (pages.length) await store.savePageStates(pages);
        }
        if (mutationVersion === version && !fullPending && !dirtyPageIds.size && !timer) {
          onStatus('saved');
        }
      } catch (error) {
        onStatus('failed');
        onError(error);
      } finally {
        onMeasure(full ? 'persist.full' : 'persist.page', performance.now() - started);
        running = null;
        if ((fullPending || dirtyPageIds.size) && !timer) {
          timer = schedule(() => {
            timer = null;
            void persistNow();
          }, debounceMs);
        }
      }
    })();
    return running;
  }

  function markChanged({full = false, pageIds = []} = {}) {
    mutationVersion++;
    onStatus('saving');
    if (full) fullPending = true;
    else for (const id of pageIds) if (id) dirtyPageIds.add(id);
    if (timer) cancel(timer);
    timer = schedule(() => {
      timer = null;
      void persistNow();
    }, debounceMs);
  }

  async function flush() {
    if (timer) {
      cancel(timer);
      timer = null;
    }
    await persistNow();
    if (running) await running;
  }

  async function discardPending() {
    mutationVersion++;
    if (timer) {
      cancel(timer);
      timer = null;
    }
    fullPending = false;
    dirtyPageIds.clear();
    if (running) await running;
  }

  return Object.freeze({
    markChanged,
    flush,
    discardPending,
    get dirty() {
      return isDirty();
    },
    pendingPageIds: () => [...dirtyPageIds],
    get fullPending() {
      return fullPending;
    }
  });
}
