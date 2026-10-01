// Keep the entry and all of its imports on the same release across browser caches.
(async () => {
  const release = '20261001-model-manager1';
  const fail = error => {
    console.error('Workbench startup failed', error);
    const panel = document.createElement('div');
    panel.setAttribute('role', 'alert');
    panel.style.cssText = 'position:fixed;inset:0 0 auto;background:#fff1e9;color:#703b25;padding:20px;z-index:100;font:14px system-ui';
    const message = document.createElement('p');
    message.textContent = 'The workbench could not load, so its controls are temporarily unavailable. Reloading will not clear the locally cached project.';
    const retry = document.createElement('button');
    retry.textContent = 'Reload workbench';
    retry.onclick = () => {
      const url = new URL(location.href);
      url.searchParams.set('reload', Date.now());
      location.replace(url);
    };
    panel.append(message, retry);
    document.body.append(panel);
  };

  try {
    await import('./app.mjs?v=' + release);
  } catch (error) {
    fail(error);
  }
})();
