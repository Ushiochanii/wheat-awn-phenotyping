const GRID_ENDPOINT = '/api/grid-calibration';
const PLAUSIBILITY_ENDPOINT = '/api/calibration-plausibility';

export function installTwinCalibrationUI({autoGridEnabled=true}={}) {
  const modes = document.querySelector('.scale-modes');
  if (!modes) return;
  if (document.getElementById('scale-auto-fields')) {
    setAutoGridEnabled(autoGridEnabled);
    return;
  }

  const autoLabel = document.createElement('label');
  autoLabel.id = 'scale-auto-mode';
  autoLabel.innerHTML = '<input type="radio" name="scale-mode" value="auto"> <span>Auto grid calibration</span>';
  modes.prepend(autoLabel);

  const line = document.getElementById('scale-line-fields');
  if (line) {
    const oldHelp = line.querySelector('[data-i18n="calibration.lineHelp"]');
    if (oldHelp) oldHelp.remove();

    const step1 = document.createElement('div');
    step1.className = 'twin-calibration-step';
    step1.innerHTML = '<span class="twin-step-badge">1</span><div><strong>Draw a calibration line</strong><p>Draw one line spanning a known physical distance.</p></div>';

    const step2 = document.createElement('div');
    step2.className = 'twin-calibration-step';
    step2.innerHTML = '<span class="twin-step-badge">2</span><div><strong>Enter the real physical length</strong><p>Enter the physical distance represented by the calibration line.</p></div>';

    line.prepend(step1);
    const pixels = document.getElementById('scale-pixels');
    if (pixels) pixels.insertAdjacentElement('afterend', step2);
  }

  const auto = document.createElement('section');
  auto.id = 'scale-auto-fields';
  auto.innerHTML = `
    <p>Detect the 5 mm background grid and estimate the image scale automatically.</p>
    <p id="scale-auto-status" class="muted">The grid will be analysed when calibration is applied.</p>
    <p class="twin-grid-warning"><strong>Warning:</strong> This value is inferred from the background grid and may be inaccurate. Verify the calibration when measurement accuracy matters.</p>
  `;
  const lineSection = document.getElementById('scale-line-fields');
  lineSection?.parentNode?.insertBefore(auto, lineSection);

  const batch = document.getElementById('scale-apply-matching')?.closest('label');
  if (batch) batch.hidden = true;
  const batchHelp = document.querySelector('.calibration-batch-help');
  if (batchHelp) batchHelp.hidden = true;

  const style = document.createElement('style');
  style.textContent = `
    .twin-grid-warning { color:#b42318; margin-top:10px; line-height:1.45; }
    .twin-calibration-step { display:flex; gap:10px; align-items:flex-start; margin:10px 0; }
    .twin-calibration-step p { margin:3px 0 0; color:#687078; font-size:12px; line-height:1.4; }
    .twin-step-badge {
      width:20px; height:20px; min-width:20px; display:inline-grid; place-items:center;
      border-radius:999px; border:1px solid #9da5ad; font:600 11px system-ui,sans-serif;
      color:#3b4147; background:#fff;
    }
  `;
  document.head.append(style);
  setAutoGridEnabled(autoGridEnabled);

  for (const radio of document.querySelectorAll('[name="scale-mode"]')) {
    radio.addEventListener('change', () => {
      const mode = document.querySelector('[name="scale-mode"]:checked')?.value;
      document.getElementById('scale-auto-fields').hidden = mode !== 'auto';
      document.getElementById('scale-line-fields').hidden = mode !== 'line';
    });
  }
}

export function setAutoGridEnabled(enabled) {
  const allowed = enabled !== false;
  const label = document.getElementById('scale-auto-mode');
  const fields = document.getElementById('scale-auto-fields');
  if (label) label.hidden = !allowed;
  if (!allowed && document.querySelector('[name="scale-mode"]:checked')?.value === 'auto') {
    const fallback = document.querySelector('[name="scale-mode"][value="line"]');
    if (fallback) {
      fallback.checked = true;
      fallback.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }
  if (fields && !allowed) fields.hidden = true;
}

export function defaultMode(calibration,{autoGridEnabled=true}={}) {
  if (calibration?.source === 'manual') return 'line';
  return autoGridEnabled ? 'auto' : 'line';
}

export function describeExistingGridCalibration(calibration) {
  const node = document.getElementById('scale-auto-status');
  if (!node) return;
  const grid = calibration?.gridCalibration;
  if (!grid) {
    node.textContent = 'The grid will be analysed when calibration is applied.';
    return;
  }
  const ratio = Number(calibration.mm);
  const qc = grid.qc_adequate ? 'QC passed' : 'QC warning';
  node.textContent = Number.isFinite(ratio)
    ? `Previous estimate: ${ratio.toFixed(8)} mm/px · ${qc}`
    : `Previous grid estimate · ${qc}`;
}

export function setGridStatus(message) {
  const node = document.getElementById('scale-auto-status');
  if (node) node.textContent = message;
}

export async function calibrateFromGrid(src) {
  const response = await fetch(GRID_ENDPOINT, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({src}),
  });
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.error ?? 'Automatic grid calibration failed.');
  return payload;
}


export async function assessCalibrationPlausibility(src, mmPerPx) {
  const response = await fetch(PLAUSIBILITY_ENDPOINT, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({src, mm_per_px: mmPerPx}),
  });
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.error ?? 'Calibration plausibility check failed.');
  return payload.plausibility ?? null;
}

export function plausibilityErrorMessage(diagnostic) {
  if (!diagnostic || diagnostic.adequate !== false) return null;
  const current = Number(diagnostic.median_long_side_mm);
  const typicalMin = Number(diagnostic.reference_typical_min_mm);
  const typicalMax = Number(diagnostic.reference_typical_max_mm);
  const blockMin = Number(diagnostic.block_min_mm);
  const blockMax = Number(diagnostic.block_max_mm);
  const count = Number(diagnostic.spikelet_count);
  const conf = Number(diagnostic.confidence_min);
  return [
    'Automatic calibration looks biologically implausible.',
    '',
    `Under this scale, the median detected spikelet long side is ${current.toFixed(2)} mm.`,
    `Project reference: typical median-scale spikelets are about ${typicalMin.toFixed(0)}–${typicalMax.toFixed(0)} mm; the broad acceptable guard band is ${blockMin.toFixed(0)}–${blockMax.toFixed(0)} mm.`,
    `Diagnostic used ${count} high-confidence spikelets (confidence ≥ ${conf.toFixed(2)}).`,
    '',
    'This scale can distort millimetre-based post-processing thresholds and cause incorrect long-distance connections. Automatic measurement has been stopped. Please recalibrate before running.',
  ].join('\n');
}
