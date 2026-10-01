const cloneLine = points => (Array.isArray(points) ? points.map(point => [Number(point[0]), Number(point[1])]) : []);

function distance(a, b) {
  return Math.hypot(Number(a[0]) - Number(b[0]), Number(a[1]) - Number(b[1]));
}

export function pathLengthPx(points) {
  const line = Array.isArray(points) ? points : [];
  let total = 0;
  for (let i = 1; i < line.length; i++) total += distance(line[i - 1], line[i]);
  return total;
}

export function trimPathToLength(points, maxLengthPx) {
  const line = cloneLine(points);
  const limit = Math.max(0, Number(maxLengthPx) || 0);
  if (line.length < 2 || limit <= 0) return [];
  const total = pathLengthPx(line);
  if (limit >= total) return line;

  const out = [line[0]];
  let used = 0;
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const b = line[i];
    const segment = distance(a, b);
    if (segment <= 1e-9) continue;
    if (used + segment <= limit) {
      out.push(b);
      used += segment;
      continue;
    }
    const remain = Math.max(0, limit - used);
    const t = Math.max(0, Math.min(1, remain / segment));
    out.push([
      a[0] + (b[0] - a[0]) * t,
      a[1] + (b[1] - a[1]) * t
    ]);
    break;
  }
  return out.length >= 2 ? out : [];
}

export function confidenceFilteredLine({baseline, record, threshold, mmPerPx}) {
  const line = cloneLine(baseline);
  const cutoff = Math.max(0, Math.min(1, Number(threshold) || 0));
  const scale = Number(mmPerPx);
  if (line.length < 2 || cutoff <= 0 || !record || !Number.isFinite(scale) || scale <= 0) {
    return line;
  }

  const steps = Array.isArray(record.steps) ? record.steps : [];
  const firstRejected = steps.findIndex(step => {
    if (step?.support_confidence == null) return false;
    const confidence = Number(step.support_confidence);
    return Number.isFinite(confidence) && confidence < cutoff;
  });
  if (firstRejected < 0) return line;

  const removedMm = steps.slice(firstRejected).reduce((sum, step) => {
    const extension = Number(step?.extension_mm);
    return sum + (Number.isFinite(extension) && extension > 0 ? extension : 0);
  }, 0);
  if (removedMm <= 0) return line;

  const targetPx = pathLengthPx(line) - removedMm / scale;
  return trimPathToLength(line, targetPx);
}
