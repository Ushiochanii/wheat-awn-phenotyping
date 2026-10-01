const ENDPOINT = '/api/resolution-gate';

function ensureUI() {
  if (document.getElementById('resolution-gate-dialog')) return;

  const style = document.createElement('style');
  style.textContent = `
    #resolution-gate-dialog {
      width:min(470px,calc(100vw - 40px));
      border:1px solid #c8ccd0;
      border-radius:12px;
      padding:0;
      box-shadow:0 22px 70px rgba(0,0,0,.28);
      color:#23272b;
      background:#fff;
    }
    #resolution-gate-dialog::backdrop { background:rgba(15,18,21,.48); }
    .resolution-gate-body { padding:24px 24px 18px; }
    .resolution-gate-body h2 { margin:0 0 10px;font:600 18px/1.25 system-ui,sans-serif; }
    .resolution-gate-body p { margin:0;color:#555d65;font:14px/1.55 system-ui,sans-serif; }
    .resolution-gate-actions {
      display:flex;justify-content:flex-end;gap:10px;padding:14px 18px 18px;
    }
    .resolution-gate-actions button {
      border:1px solid #c4c9ce;border-radius:7px;background:#fff;color:#252a2f;
      padding:8px 13px;font:500 13px system-ui,sans-serif;cursor:pointer;
    }
    .resolution-gate-actions .primary {
      background:#2e6f55;border-color:#2e6f55;color:white;
    }
    #resolution-gate-notice {
      position:fixed;right:20px;top:20px;z-index:99999;max-width:430px;
      padding:11px 14px;border-radius:8px;background:#252a2f;color:#f7f8f8;
      box-shadow:0 8px 28px rgba(0,0,0,.24);font:13px/1.45 system-ui,sans-serif;
      opacity:0;transform:translateY(-6px);pointer-events:none;
      transition:opacity .16s ease,transform .16s ease;
    }
    #resolution-gate-notice.show { opacity:1;transform:translateY(0); }
  `;
  document.head.append(style);

  const dialog = document.createElement('dialog');
  dialog.id = 'resolution-gate-dialog';
  dialog.innerHTML = `
    <div class="resolution-gate-body">
      <h2>Image resolution is too low for reliable measurement.</h2>
      <p>You can continue by upscaling the image, but measurement accuracy may be reduced.</p>
    </div>
    <div class="resolution-gate-actions">
      <button type="button" data-action="cancel">Cancel</button>
      <button type="button" class="primary" data-action="continue">Upscale and Continue</button>
    </div>
  `;
  document.body.append(dialog);

  const notice = document.createElement('div');
  notice.id = 'resolution-gate-notice';
  notice.setAttribute('role', 'status');
  document.body.append(notice);
}

function notice(message, duration = 4200) {
  ensureUI();
  const node = document.getElementById('resolution-gate-notice');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => node.classList.remove('show'), duration);
}

function confirmForcedUpscale() {
  ensureUI();
  const dialog = document.getElementById('resolution-gate-dialog');
  return new Promise(resolve => {
    const cleanup = value => {
      dialog.removeEventListener('cancel', onCancel);
      dialog.querySelector('[data-action="cancel"]').removeEventListener('click', onCancelClick);
      dialog.querySelector('[data-action="continue"]').removeEventListener('click', onContinue);
      if (dialog.open) dialog.close();
      resolve(value);
    };
    const onCancel = event => { event.preventDefault(); cleanup(false); };
    const onCancelClick = () => cleanup(false);
    const onContinue = () => cleanup(true);
    dialog.addEventListener('cancel', onCancel);
    dialog.querySelector('[data-action="cancel"]').addEventListener('click', onCancelClick);
    dialog.querySelector('[data-action="continue"]').addEventListener('click', onContinue);
    dialog.showModal();
  });
}

async function requestGate(src, force = false) {
  const response = await fetch(ENDPOINT, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({src, force}),
  });
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.error ?? 'Resolution check failed.');
  return payload;
}

export async function prepareImportedImage({src, width, height, name = 'image'}) {
  let payload = await requestGate(src, false);
  const assessment = payload.resolution ?? {};

  if (assessment.status === 'too_low') {
    const proceed = await confirmForcedUpscale();
    if (!proceed) {
      notice(`${name}: import cancelled because the image resolution is too low.`);
      return null;
    }
    payload = await requestGate(src, true);
  }

  const resolution = payload.resolution ?? assessment;
  if (resolution.status === 'unassessed') {
    notice('Image resolution could not be assessed reliably. The original image was kept.');
  } else if (resolution.action === 'downscaled') {
    notice('High-resolution input · automatically downscaled to the model scale before measurement.');
  } else if (resolution.applied && resolution.forced) {
    notice('Low-resolution input · upscaled. Measurement accuracy may be reduced.', 6200);
  } else if (resolution.action === 'upscaled') {
    notice('Image resolution is low. The image has been automatically upscaled before measurement.');
  }

  const provenance = resolution.action === 'downscaled'
    ? 'High-resolution input · downscaled'
    : resolution.action === 'upscaled'
      ? 'Low-resolution input · upscaled'
      : 'Resolution checked · original retained';

  return {
    src: payload.src ?? src,
    width: payload.width ?? width,
    height: payload.height ?? height,
    resolutionEnhancement: {
      ...resolution,
      provenance,
    },
  };
}
