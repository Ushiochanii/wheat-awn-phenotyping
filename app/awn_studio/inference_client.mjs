export function resolveInferenceBase(locationLike = globalThis.location) {
  if (!locationLike) return '';
  if (String(locationLike.port) === '8000') {
    const host = ['localhost', '127.0.0.1'].includes(locationLike.hostname)
      ? '127.0.0.1'
      : locationLike.hostname;
    return `${locationLike.protocol}//${host}:8781`;
  }
  return locationLike.origin;
}

export function createInferenceClient({
  baseURL = resolveInferenceBase(),
  fetchImpl = globalThis.fetch,
  pollIntervalMs = 700
} = {}) {
  if (typeof fetchImpl !== 'function') throw new TypeError('A fetch implementation is required.');

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetchImpl(baseURL + path, options);
    } catch (cause) {
      const error = new Error('Inference service is unavailable.');
      error.code = 'service_unavailable';
      error.cause = cause;
      throw error;
    }
    let data;
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    if (!response.ok) {
      const error = new Error(data.error ?? `Inference request failed with HTTP ${response.status}.`);
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    return data;
  }

  const modelInfo = options => request('/api/model', options);
  const models = options => request('/api/models', options);
  const registerModel = payload => request('/api/models/register', {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
  });
  const removeModel = modelId => request('/api/models/remove', {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model_id:modelId})
  });
  const preloadModel = modelId => request('/api/models/preload', {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model_id:modelId})
  });
  const submit = payload => request('/api/jobs', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  const job = jobId => request(`/api/jobs/${jobId}`);
  const preview = jobId => request(`/api/jobs/${jobId}/preview`);

  async function wait(jobId, {
    onState = () => {},
    onPreview = () => {},
    signal
  } = {}) {
    let previewRevision = 0;
    let state;
    do {
      if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
      await new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, pollIntervalMs);
        if (!signal) return;
        signal.addEventListener('abort', () => {
          clearTimeout(timer);
          reject(new DOMException('The operation was aborted.', 'AbortError'));
        }, {once:true});
      });

      state = await job(jobId);
      onState(state);

      if (
        ['queued', 'running'].includes(state?.status)
        && (state.preview_revision ?? 0) > previewRevision
      ) {
        try {
          const nextPreview = await preview(jobId);
          previewRevision = nextPreview.revision ?? state.preview_revision ?? previewRevision;
          onPreview(nextPreview);
        } catch (error) {
          // A job can finish between the state poll and preview fetch. The
          // server drops transient preview data at completion, so a 404 here
          // is a harmless race rather than a measurement failure.
          if (error?.status !== 404) throw error;
        }
      }
    } while (['queued', 'running'].includes(state?.status));

    return state;
  }

  return Object.freeze({request, modelInfo, models, registerModel, removeModel, preloadModel, submit, job, preview, wait});
}
