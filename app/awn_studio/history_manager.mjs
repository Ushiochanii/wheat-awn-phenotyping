export function createHistoryManager({limit = 70} = {}) {
  const past = [];
  const future = [];

  function checkpoint(snapshot) {
    past.push(snapshot);
    if (past.length > limit) past.shift();
    future.length = 0;
  }

  function undo(currentSnapshot) {
    if (!past.length) return null;
    const target = past.pop();
    future.push(currentSnapshot);
    return target;
  }

  function redo(currentSnapshot) {
    if (!future.length) return null;
    const target = future.pop();
    past.push(currentSnapshot);
    if (past.length > limit) past.shift();
    return target;
  }

  function clear() {
    past.length = 0;
    future.length = 0;
  }

  return Object.freeze({
    checkpoint,
    undo,
    redo,
    clear,
    peekUndo: () => past.at(-1) ?? null,
    peekRedo: () => future.at(-1) ?? null,
    get canUndo() {
      return past.length > 0;
    },
    get canRedo() {
      return future.length > 0;
    },
    sizes: () => ({past: past.length, future: future.length})
  });
}
