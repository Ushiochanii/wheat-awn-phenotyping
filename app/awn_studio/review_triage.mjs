// Operational review triage for Awn Studio.
// This module consumes existing pipeline diagnostics only. It must never
// participate in detection, reconstruction, representative selection, or measurement.

export const REVIEW_STATUS = Object.freeze({
  automatic: 'automatic',
  needsReview: 'needs_review',
  modified: 'modified',
  confirmed: 'confirmed',
  missing: 'missing'
});

export const REVIEW_REASON_LABELS = Object.freeze({
  degraded_orientation: 'Direction was defaulted from limited orientation evidence',
  low_support_confidence: 'Low-confidence evidence contributes to the final awn',
  ownership_competition: 'Awn evidence was contested between competing branches',
  large_fragment_gap: 'The final awn crosses an unusually large reconstructed gap',
  sharp_join: 'A reconstructed join is close to the geometric acceptance limit',
  long_reconstruction_chain: 'The final awn required several fragment-growth hops',
  branch_disagreement: 'Competing branches have similar scores but materially different lengths',
  crossing_continuation_unresolved: 'The awn continuation at a crossing requires review',
  foreign_spikelet_body: 'Growth stopped before entering another spikelet',
  ambiguous_junction: 'Growth stopped at an ambiguous branch'
});

const finite = value => Number.isFinite(Number(value)) ? Number(value) : null;

function bestAlternative(record) {
  const alternatives = Array.isArray(record?.alternatives) ? record.alternatives : [];
  if (!alternatives.length) return null;
  return alternatives.reduce((best, row) => {
    const score = finite(row?.branch_score) ?? -Infinity;
    return !best || score > best.score ? {row, score} : best;
  }, null);
}

export function assessAutomaticReview(record, orientation = {}) {
  const reasons = [];
  const signals = {};
  const winner = record?.winner ?? null;
  const seed = record?.winner_seed ?? null;
  const steps = Array.isArray(record?.steps) ? record.steps : [];

  const degradedOrientation =
    orientation?.policy === 'single_spikelet_default_polarity' ||
    orientation?.orientation_degraded === true;
  if (degradedOrientation) reasons.push('degraded_orientation');
  const stopReason = record?.representative?.review_reason;
  if (stopReason && Object.hasOwn(REVIEW_REASON_LABELS, stopReason)) {
    reasons.push(stopReason);
    signals.endpoint_status = record.representative.endpoint_status ?? 'unresolved';
  }

  if (winner) {
    const confidences = [];
    const seedConfidence = finite(seed?.confidence);
    if (seedConfidence !== null) confidences.push(seedConfidence);
    for (const step of steps) {
      const value = finite(step?.support_confidence);
      if (value !== null) confidences.push(value);
    }
    const minSupportConfidence = confidences.length ? Math.min(...confidences) : null;
    signals.min_support_confidence = minSupportConfidence;
    if (minSupportConfidence !== null && minSupportConfidence < 0.35) {
      reasons.push('low_support_confidence');
    }

    const ownershipEvents = Array.isArray(winner?.ownership_events) ? winner.ownership_events : [];
    const contestedOwnership = ownershipEvents.some(event => {
      const result = String(event?.result ?? '');
      return result === 'shared' || result.startsWith('denied');
    });
    signals.contested_ownership = contestedOwnership;
    if (contestedOwnership) reasons.push('ownership_competition');

    const distances = steps.map(step => finite(step?.distance_mm)).filter(value => value !== null);
    const maxGapMm = distances.length ? Math.max(...distances) : 0;
    signals.max_fragment_gap_mm = maxGapMm;
    if (maxGapMm >= 1.0) reasons.push('large_fragment_gap');

    const localTurns = steps.map(step => finite(step?.join_local_turn_deg)).filter(value => value !== null);
    const excessTurns = steps.map(step => finite(step?.join_excess_turn_deg)).filter(value => value !== null);
    const maxLocalTurnDeg = localTurns.length ? Math.max(...localTurns) : 0;
    const maxExcessTurnDeg = excessTurns.length ? Math.max(...excessTurns) : 0;
    signals.max_join_local_turn_deg = maxLocalTurnDeg;
    signals.max_join_excess_turn_deg = maxExcessTurnDeg;
    if (maxLocalTurnDeg >= 18 || maxExcessTurnDeg >= 6) reasons.push('sharp_join');

    const growthHops = finite(winner?.growth_hops) ?? steps.length;
    signals.growth_hops = growthHops;
    if (growthHops >= 3) reasons.push('long_reconstruction_chain');

    const winnerScore = finite(winner?.branch_score);
    const winnerLength = finite(winner?.final_length_mm);
    const alternative = bestAlternative(record);
    if (winnerScore !== null && winnerLength !== null && alternative) {
      const alternativeLength = finite(alternative.row?.final_length_mm);
      if (alternativeLength !== null) {
        const scoreGapRel = Math.abs(winnerScore - alternative.score) /
          Math.max(1, Math.abs(winnerScore), Math.abs(alternative.score));
        const lengthGapAbsMm = Math.abs(winnerLength - alternativeLength);
        const lengthGapRel = lengthGapAbsMm /
          Math.max(1, Math.abs(winnerLength), Math.abs(alternativeLength));
        signals.branch_score_gap_rel = scoreGapRel;
        signals.branch_length_gap_rel = lengthGapRel;
        signals.branch_length_gap_mm = lengthGapAbsMm;
        if (scoreGapRel <= 0.05 && lengthGapRel >= 0.15 && lengthGapAbsMm >= 2.0) {
          reasons.push('branch_disagreement');
        }
      }
    }
  }

  return {
    status: reasons.length ? REVIEW_STATUS.needsReview : REVIEW_STATUS.automatic,
    reasons: [...new Set(reasons)],
    signals
  };
}

export function effectiveReviewStatus(group) {
  if (!Array.isArray(group?.line) || group.line.length < 2) return REVIEW_STATUS.missing;
  // Provenance is more useful than confirmation for edited measurements.
  if (group?.modified || group?.origin === 'manual') return REVIEW_STATUS.modified;
  if (group?.confirmed) return REVIEW_STATUS.confirmed;
  if (group?.autoReviewStatus === REVIEW_STATUS.needsReview) return REVIEW_STATUS.needsReview;
  return REVIEW_STATUS.automatic;
}

export function reviewReasonLabels(group) {
  return (Array.isArray(group?.reviewReasons) ? group.reviewReasons : [])
    .map(reason => REVIEW_REASON_LABELS[reason] ?? String(reason));
}
