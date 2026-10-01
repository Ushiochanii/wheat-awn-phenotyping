function openDatabase({databaseName, storeName}) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(storeName)) {
        request.result.createObjectStore(storeName);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function splitProjectForStorage(project) {
  const inferenceRecords = new Map();
  const assetRecords = new Map();
  const pages = (project?.pages ?? []).map(page => {
    let manifestPage = page;

    if (!page?.sourcePageId && page?.src) {
      const assetRef = String(page.assetRef ?? page.id);
      assetRecords.set(assetRef, page.src);
      const {src: _src, ...withoutSource} = manifestPage;
      manifestPage = {...withoutSource, assetRef};
    }

    if (page?.inference) {
      const ref = String(page.inferenceRef ?? page.id);
      inferenceRecords.set(ref, page.inference);
      const {inference: _inference, ...withoutInference} = manifestPage;
      manifestPage = {
        ...withoutInference,
        pageKind: withoutInference.pageKind ?? 'measurement_result',
        inferenceRef: ref,
        inferenceMeta: {
          ...(withoutInference.inferenceMeta ?? {}),
          schema: page.inference?.schema ?? withoutInference.inferenceMeta?.schema ?? null,
          jobId: page.inference?.jobId ?? withoutInference.inferenceMeta?.jobId ?? null
        }
      };
    }

    return manifestPage;
  });
  return {
    manifest: {...project, pages},
    inferenceRecords,
    assetRecords
  };
}

export function createProjectStore({
  databaseName = 'awn-studio',
  storeName = 'projects',
  currentKey = 'current'
} = {}) {
  const databasePromise = openDatabase({databaseName, storeName});
  databasePromise.catch(() => {});

  async function loadCurrent() {
    const database = await databasePromise;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readonly');
      const store = transaction.objectStore(storeName);
      const baseRequest = store.get(currentKey);
      const patches = new Map();
      const cursorRequest = store.openKeyCursor();

      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;
        if (!cursor) return;
        const key = String(cursor.key);
        if (key.startsWith('edit:')) {
          const patchRequest = store.get(cursor.key);
          patchRequest.onsuccess = () => patches.set(key.slice(5), patchRequest.result);
          patchRequest.onerror = () => reject(patchRequest.error);
        }
        cursor.continue();
      };
      cursorRequest.onerror = () => reject(cursorRequest.error);
      baseRequest.onerror = () => reject(baseRequest.error);
      transaction.oncomplete = () => {
        const base = baseRequest.result;
        if (!base?.pages) return resolve(base);
        for (const page of base.pages) {
          const patch = patches.get(String(page.id));
          if (!patch) continue;
          if (Array.isArray(patch.groups)) page.groups = patch.groups;
          if ('calibration' in patch) page.calibration = patch.calibration;
        }
        resolve(base);
      };
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async function saveCurrent(project) {
    const database = await databasePromise;
    const {manifest, inferenceRecords, assetRecords} = splitProjectForStorage(project);
    const referencedInference = new Set(
      manifest.pages
        .map(page => page?.inferenceRef)
        .filter(Boolean)
        .map(String)
    );
    const referencedAssets = new Set(
      manifest.pages
        .map(page => page?.assetRef)
        .filter(Boolean)
        .map(String)
    );
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readwrite');
      const store = transaction.objectStore(storeName);
      store.put(manifest, currentKey);
      for (const [ref, inference] of inferenceRecords) {
        store.put(inference, `inference:${ref}`);
      }
      for (const [ref, source] of assetRecords) {
        store.put(source, `asset:${ref}`);
      }
      const cursorRequest = store.openKeyCursor();
      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;
        if (!cursor) return;
        const key = String(cursor.key);
        if (key.startsWith('edit:')) store.delete(cursor.key);
        if (key.startsWith('inference:') && !referencedInference.has(key.slice(10))) store.delete(cursor.key);
        if (key.startsWith('asset:') && !referencedAssets.has(key.slice(6))) store.delete(cursor.key);
        cursor.continue();
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async function clearCurrent() {
    const database = await databasePromise;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readwrite');
      const store = transaction.objectStore(storeName);
      const cursorRequest = store.openKeyCursor();
      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;
        if (!cursor) return;
        const key = String(cursor.key);
        if (
          key === currentKey ||
          key.startsWith('edit:') ||
          key.startsWith('inference:') ||
          key.startsWith('asset:')
        ) {
          store.delete(cursor.key);
        }
        cursor.continue();
      };
      cursorRequest.onerror = () => reject(cursorRequest.error);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async function loadInference(ref) {
    if (!ref) return null;
    const database = await databasePromise;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readonly');
      const request = transaction.objectStore(storeName).get(`inference:${ref}`);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  async function loadAsset(ref) {
    if (!ref) return null;
    const database = await databasePromise;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readonly');
      const request = transaction.objectStore(storeName).get(`asset:${ref}`);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  async function saveRecord(key, value) {
    const database = await databasePromise;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readwrite');
      transaction.objectStore(storeName).put(value, key);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  const saveInference = (ref, inference) =>
    saveRecord(`inference:${ref}`, inference);
  const saveAsset = (ref, source) =>
    saveRecord(`asset:${ref}`, source);

  async function savePageStates(pages) {
    const database = await databasePromise;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readwrite');
      const store = transaction.objectStore(storeName);
      for (const page of pages) {
        store.put({
          groups: structuredClone(page.groups ?? []),
          calibration: structuredClone(page.calibration ?? null)
        }, `edit:${page.id}`);
      }
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  return Object.freeze({
    loadCurrent,
    clearCurrent,
    loadInference,
    loadAsset,
    saveCurrent,
    saveInference,
    saveAsset,
    savePageStates
  });
}
