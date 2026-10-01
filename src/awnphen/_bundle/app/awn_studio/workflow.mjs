export function isMeasurementResultPage(page) {
  return Boolean(page?.inference || page?.inferenceRef || page?.pageKind === 'measurement_result');
}

export function measurementResultModelId(page) {
  if (!isMeasurementResultPage(page)) return null;
  return (
    page?.modelId ??
    page?.inference?.model_id ??
    page?.inference?.run?.model?.id ??
    page?.inferenceMeta?.modelId ??
    // Public releases use one canonical model identity.
    'yolo11n-canonical'
  );
}

export function hasMeasurementResult(pages, sourcePageId, modelId = null) {
  return pages.some(
    page =>
      page?.sourcePageId === sourcePageId &&
      isMeasurementResultPage(page) &&
      (!modelId || measurementResultModelId(page) === modelId)
  );
}

export function pendingSourcePages(pages, modelId = null) {
  return pages.filter(
    page =>
      !page?.demo &&
      !isMeasurementResultPage(page) &&
      Boolean(page?.calibration) &&
      !hasMeasurementResult(pages, page.id, modelId)
  );
}

export function uncalibratedPendingSourcePages(pages, modelId = null) {
  return pages.filter(
    page =>
      !page?.demo &&
      !isMeasurementResultPage(page) &&
      !page?.calibration &&
      !hasMeasurementResult(pages, page.id, modelId)
  );
}

export function measurementResultsForSource(pages, sourcePageId) {
  return pages.filter(
    page => page?.sourcePageId === sourcePageId && isMeasurementResultPage(page)
  );
}

export function latestMeasurementResult(pages, sourcePageId) {
  return measurementResultsForSource(pages, sourcePageId).at(-1) ?? null;
}

export function navigationPages(pages) {
  return pages.filter(page => !page?.sourcePageId);
}

export function navigationTarget(page, pages) {
  if (!page || isMeasurementResultPage(page)) return page ?? null;
  return latestMeasurementResult(pages, page.id) ?? page;
}

export function currentMeasurementPage(page, pages) {
  if (!page) return null;
  if (isMeasurementResultPage(page)) return page;
  const latest = latestMeasurementResult(pages, page.id);
  if (latest) return latest;
  return Array.isArray(page.groups) && page.groups.length ? page : null;
}

export function exportableMeasurementPages(pages) {
  const output = [];
  for (const root of navigationPages(pages)) {
    if (isMeasurementResultPage(root)) {
      output.push(root);
      continue;
    }
    const result = latestMeasurementResult(pages, root.id);
    if (result) output.push(result);
    else if (Array.isArray(root.groups) && root.groups.length) output.push(root);
  }
  return output;
}

export function matchingUncalibratedSources(pages, referencePage) {
  if (!referencePage || isMeasurementResultPage(referencePage)) return [];
  return navigationPages(pages).filter(
    page =>
      page.id !== referencePage.id &&
      !page?.demo &&
      !isMeasurementResultPage(page) &&
      !page?.calibration &&
      page?.width === referencePage.width &&
      page?.height === referencePage.height
  );
}

export function cascadePageIds(pages, pageIds) {
  const result = new Set(pageIds);
  for (const page of pages) {
    if (page?.sourcePageId && result.has(page.sourcePageId)) result.add(page.id);
  }
  return result;
}

export function projectPageStatus(page, pages) {
  if (isMeasurementResultPage(page)) return 'result';
  if (hasMeasurementResult(pages, page?.id)) return 'measured';
  if (page?.calibration) return 'ready';
  return 'needs_calibration';
}
