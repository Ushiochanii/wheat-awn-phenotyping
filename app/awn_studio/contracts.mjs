import {assessAutomaticReview} from './review_triage.mjs?v=20260929-20';

export const PROJECT_SCHEMA = 'awn-studio-v1';
export const PRODUCT_RESULT_SCHEMA = 'awn-studio-result-v2';

export const INSPECTION_STAGES = Object.freeze([
  'source',
  'detection_evidence',
  'spikelet_seed',
  'trajectory_growth',
  'representative_awn',
  'measurement_path'
]);

export const OBJECT_STATUS = Object.freeze({
  automatic: 'automatic',
  modified: 'modified',
  confirmed: 'confirmed',
  needsReview: 'needs_review',
  missingMeasurement: 'missing_measurement'
});

const clone = value => structuredClone(value);
const array = value => Array.isArray(value) ? value : [];
const finiteOrNull = value => Number.isFinite(value) ? Number(value) : null;
const normalizedResultCache = new WeakMap();

function reviewState(group) {
  if (array(group?.line).length < 2) return OBJECT_STATUS.missingMeasurement;
  if (group?.confirmed) return OBJECT_STATUS.confirmed;
  if (group?.modified || group?.origin === 'manual') return OBJECT_STATUS.modified;
  return OBJECT_STATUS.automatic;
}

function normalizeMeasurement(row, index) {
  const spikelet = row?.spikelet ?? {};
  const representative = row?.representative_awn ?? {};
  const path = array(representative.measurement_path).map(point => [Number(point[0]), Number(point[1])]);
  return {
    id: String(row?.id ?? spikelet.id ?? `measurement-${index + 1}`),
    label: String(row?.label ?? index + 1),
    origin: row?.origin === 'manual' ? 'manual' : 'automatic',
    review: {
      status: row?.review?.status ?? (path.length >= 2 ? OBJECT_STATUS.automatic : OBJECT_STATUS.missingMeasurement),
      modified: Boolean(row?.review?.modified),
      confirmed: Boolean(row?.review?.confirmed),
      reasons: clone(array(row?.review?.reasons)),
      signals: clone(row?.review?.signals ?? {})
    },
    spikelet: {
      id: String(spikelet.id ?? row?.id ?? `spikelet-${index + 1}`),
      polygon: array(spikelet.polygon).map(point => [Number(point[0]), Number(point[1])])
    },
    representative_awn: {
      id: representative.id == null ? null : String(representative.id),
      measurement_path: path,
      length_mm: finiteOrNull(representative.length_mm)
    },
    provenance: clone(row?.provenance ?? {})
  };
}

function fromLegacyResult(input) {
  const groups = array(input?.groups);
  return {
    schema: PRODUCT_RESULT_SCHEMA,
    source: {
      sha256: input?.source_sha256 ?? null
    },
    measurements: groups.map((group, index) => ({
      id: String(group.uid ?? `measurement-${index + 1}`),
      label: String(group.name ?? index + 1),
      origin: group.origin === 'manual' ? 'manual' : 'automatic',
      review: {
        status: reviewState(group),
        modified: Boolean(group.modified),
        confirmed: Boolean(group.confirmed)
      },
      spikelet: {
        id: String(group.uid ?? `spikelet-${index + 1}`),
        polygon: clone(array(group.polygon))
      },
      representative_awn: {
        id: group.modelAwnId == null ? null : String(group.modelAwnId),
        measurement_path: clone(array(group.line)),
        length_mm: null
      },
      provenance: {
        legacy_group_uid: group.uid ?? null
      }
    })),
    display_layers: {
      detection_evidence: clone(array(input?.layers?.raw)),
      awn_candidates: clone(array(input?.layers?.candidates)),
      representative_awns: clone(array(input?.layers?.representatives))
    },
    inspection: {
      schema: input?.inspection?.schema ?? null,
      stages: clone(array(input?.inspection?.stages)),
      records: clone(input?.inspection?.records ?? {}),
      support_pool: clone(array(input?.inspection?.support_pool)),
      source_to_product_spikelet: clone(input?.inspection?.source_to_product_spikelet ?? {})
    },
    run: {
      model: {
        id: input?.model_id ?? null,
        name: input?.model ?? null,
        weights_sha256: input?.weights_sha256 ?? null
      },
      pipeline: {
        name: input?.pipeline ?? null,
        stages: clone(array(input?.pipeline_stages))
      },
      orientation: clone(input?.orientation ?? {}),
      device: input?.device ?? null,
      duration_seconds: finiteOrNull(input?.seconds),
      timings: clone(input?.timings ?? {}),
      diagnostics: {
        tile_count: finiteOrNull(input?.tile_count),
        evidence_count: finiteOrNull(input?.evidence_count),
        hypothesis_count: finiteOrNull(input?.hypothesis_count),
        awn_candidate_count: finiteOrNull(input?.awn_masks),
        spikelet_count: finiteOrNull(input?.spikelet_masks),
        measurement_path_count: finiteOrNull(input?.path_count)
      }
    },
    compatibility: {
      source_schema: 'legacy-workbench-result',
      path_simplification: input?.path_simplification ?? null,
      calibration_mm_per_px: finiteOrNull(input?.calibration_mm_per_px)
    }
  };
}

export function normalizeProductResult(input) {
  if (!input || typeof input !== 'object') throw new TypeError('Inference result must be an object.');
  const cached = normalizedResultCache.get(input);
  if (cached) return cached;

  const result = input.schema !== PRODUCT_RESULT_SCHEMA ? fromLegacyResult(input) : {
    schema: PRODUCT_RESULT_SCHEMA,
    source: clone(input.source ?? {}),
    measurements: array(input.measurements).map(normalizeMeasurement),
    display_layers: {
      detection_evidence: clone(array(input.display_layers?.detection_evidence)),
      awn_candidates: clone(array(input.display_layers?.awn_candidates)),
      representative_awns: clone(array(input.display_layers?.representative_awns))
    },
    inspection: {
      schema: input.inspection?.schema ?? null,
      stages: clone(array(input.inspection?.stages)),
      records: clone(input.inspection?.records ?? {}),
      support_pool: clone(array(input.inspection?.support_pool)),
      source_to_product_spikelet: clone(input.inspection?.source_to_product_spikelet ?? {})
    },
    run: clone(input.run ?? {}),
    compatibility: clone(input.compatibility ?? {})
  };

  if (!result.run.model) result.run.model = {};
  if (!result.run.pipeline) result.run.pipeline = {};
  if (!result.run.timings) result.run.timings = {};
  if (!result.run.diagnostics) result.run.diagnostics = {};
  normalizedResultCache.set(input, result);
  normalizedResultCache.set(result, result);
  return result;
}

export function editableGroupsFromProductResult(input) {
  const result = normalizeProductResult(input);
  const orientation = result.run?.orientation ?? {};
  return result.measurements.map(row => {
    const record = result.inspection?.records?.[String(row.spikelet.id)] ?? null;
    const derived = assessAutomaticReview(record, orientation);
    const suppliedNeedsReview = row.review?.status === OBJECT_STATUS.needsReview;
    const autoReviewStatus = suppliedNeedsReview ? OBJECT_STATUS.needsReview : derived.status;
    const reviewReasons = suppliedNeedsReview && row.review?.reasons?.length
      ? clone(row.review.reasons)
      : clone(derived.reasons);
    const reviewSignals = suppliedNeedsReview && row.review?.signals
      ? clone(row.review.signals)
      : clone(derived.signals);
    return {
      uid: row.spikelet.id,
      name: row.label,
      polygon: clone(row.spikelet.polygon),
      line: clone(row.representative_awn.measurement_path),
      origin: row.origin,
      modified: Boolean(row.review.modified),
      confirmed: Boolean(row.review.confirmed),
      autoReviewStatus,
      reviewReasons,
      reviewSignals,
      modelAwnId: row.representative_awn.id
    };
  });
}

export function inspectionRecordForSpikelet(input, spikeletId) {
  if (spikeletId == null) return null;
  const result = normalizeProductResult(input);
  return result.inspection?.records?.[String(spikeletId)] ?? null;
}

export function displayLayersFromProductResult(input) {
  const result = normalizeProductResult(input);
  return {
    raw: result.display_layers.detection_evidence,
    candidates: result.display_layers.awn_candidates,
    representatives: result.display_layers.representative_awns
  };
}

export function timingsFromProductResult(input) {
  return clone(normalizeProductResult(input).run.timings ?? {});
}

export function resultSummary(input) {
  const result = normalizeProductResult(input);
  const pathCount = result.measurements.filter(
    row => row.representative_awn.measurement_path.length >= 2
  ).length;
  return {
    spikelet_count: result.measurements.length,
    measurement_path_count: pathCount,
    duration_seconds: finiteOrNull(result.run.duration_seconds)
  };
}
