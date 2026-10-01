import {pathLength} from './core.mjs?v=20260927-07';
import {normalizeProductResult,editableGroupsFromProductResult} from './contracts.mjs?v=20260929-20';
import {exportableMeasurementPages} from './workflow.mjs?v=20260927-07';
import {effectiveReviewStatus,reviewReasonLabels} from './review_triage.mjs?v=20260929-20';

function safeText(value) {
  const text = String(value ?? '');
  return /^[\s]*[=+@-]/.test(text) ? "'" + text : text;
}

function quote(value) {
  return '"' + safeText(value).replaceAll('"','""') + '"';
}

function ratioForPage(page) {
  const points = page?.calibration?.points;
  const mm = page?.calibration?.mm;
  const pixels = Array.isArray(points) ? pathLength(points) : 0;
  return Number.isFinite(mm) && mm > 0 && pixels > 0 ? mm / pixels : null;
}

function lengthFromPath(points, ratio) {
  if (!Array.isArray(points) || points.length < 2 || !Number.isFinite(ratio)) return null;
  return pathLength(points) * ratio;
}

function finalReviewStatus(group) {
  const status = effectiveReviewStatus(group);
  return {
    automatic: 'High confidence',
    needs_review: 'Review suggested',
    missing: 'Missing',
    modified: 'Edited',
    confirmed: 'Verified'
  }[status] ?? status;
}

function autoMeasurementsBySpikelet(page) {
  if (!page?.inference) return new Map();
  const result = normalizeProductResult(page.inference);
  return new Map(result.measurements.map(row => [String(row.spikelet.id), row]));
}

function modelMetadata(page) {
  if (!page?.inference) return {model:'', pipeline:''};
  const result = normalizeProductResult(page.inference);
  return {
    model: result.run?.model?.name ?? '',
    pipeline: result.run?.pipeline?.name ?? ''
  };
}

export function detailedProjectCsv(pages) {
  const measurementPages = exportableMeasurementPages(pages);
  const header = [
    'Source image',
    'ID',
    'Automatic awn length (mm)',
    'Final awn length (mm)',
    'Review status',
    'Review reasons',
    'Modified',
    'Confirmed',
    'Model',
    'Pipeline'
  ];

  const rows = [];
  for (const page of measurementPages) {
    const ratio = ratioForPage(page);
    const automaticById = autoMeasurementsBySpikelet(page);
    const reviewById = page?.inference
      ? new Map(editableGroupsFromProductResult(page.inference).map(group => [String(group.uid), group]))
      : new Map();
    const metadata = modelMetadata(page);
    const sourceName = page.sourceName ?? page.name ?? '';

    for (const group of page.groups ?? []) {
      const automatic = automaticById.get(String(group.uid));
      const derivedReview = reviewById.get(String(group.uid));
      const reviewGroup = derivedReview ? {
        ...group,
        autoReviewStatus: derivedReview.autoReviewStatus,
        reviewReasons: derivedReview.reviewReasons,
        reviewSignals: derivedReview.reviewSignals
      } : group;
      const automaticLength = lengthFromPath(
        automatic?.representative_awn?.measurement_path,
        ratio
      );
      const finalLength = lengthFromPath(group.line, ratio);
      rows.push([
        sourceName,
        group.name,
        automaticLength == null ? '' : automaticLength.toFixed(3),
        finalLength == null ? '' : finalLength.toFixed(3),
        finalReviewStatus(reviewGroup),
        reviewReasonLabels(reviewGroup).join('; '),
        group.modified ? 'true' : 'false',
        group.confirmed ? 'true' : 'false',
        metadata.model,
        metadata.pipeline
      ]);
    }
  }

  return '\ufeff' + [
    header.map(quote).join(','),
    ...rows.map(row => row.map(quote).join(','))
  ].join('\r\n');
}
