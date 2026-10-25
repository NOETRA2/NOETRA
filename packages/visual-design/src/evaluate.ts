import type { Feature, Observation, VisualAsset, VisualReview, VisualState } from './schemas.js';

export interface Finding {
  featureId: string; layer: Feature['layer']; importance: Feature['importance'];
  finding: 'match' | 'mismatch' | 'unknown'; reason: string;
}
export function evaluateFeature(feature: Feature, observation?: Observation): Finding {
  const base = { featureId: feature.id, layer: feature.layer, importance: feature.importance };
  if (!observation || observation.finding === 'unknown') return { ...base, finding: 'unknown', reason: 'No conclusive observation for this feature/view.' };
  if (observation.finding === 'mismatch') return { ...base, finding: 'mismatch', reason: observation.note };
  if (feature.measure.kind === 'appearance') return { ...base, finding: 'match', reason: 'Imported visual reviewer assessment, not independent semantic proof.' };
  if (observation.measuredValue === undefined) return { ...base, finding: 'unknown', reason: 'A numeric feature needs a recorded measurement, not an unsupported match claim.' };
  const tolerance = feature.measure.kind === 'count' ? 0 : feature.measure.tolerance;
  const value = observation.measuredValue;
  const integerCount = feature.measure.kind !== 'count' || (Number.isInteger(value) && value >= 0);
  const matches = integerCount && Math.abs(value - feature.measure.expected) <= tolerance;
  return { ...base, finding: matches ? 'match' : 'mismatch', reason: matches ? 'Supplied measurement satisfies the explicit feature condition.' : 'Supplied measurement contradicts the feature condition, regardless of the reviewer match label.' };
}
export function evaluateReview(state: VisualState, asset: VisualAsset, review?: VisualReview) {
  const features = [...state.brief.identityFeatures, ...state.brief.detailFeatures].filter(feature => feature.views.includes(asset.view));
  const findings = features.map(feature => evaluateFeature(feature, review?.observations.find(item => item.featureId === feature.id)));
  const identityIds = new Set(state.brief.identityFeatures.map(feature => feature.id));
  const identityDrift = findings.filter(f => identityIds.has(f.featureId) && f.finding === 'mismatch');
  const mismatches = findings.filter(f => f.finding === 'mismatch');
  const unknowns = findings.filter(f => f.finding === 'unknown');
  const job = state.jobs.find(j => j.id === asset.jobId);
  const anchor = state.assets.find(a => a.role === 'anchor');
  const frameAspectMatches = job?.mode !== 'detail-edit' || !anchor ? true
    : Math.abs((asset.width / asset.height) / (anchor.width / anchor.height) - 1) <= 0.02;
  return { assetId: asset.id, assetSha256: asset.sha256, view: asset.view,
    outcome: mismatches.length || !frameAspectMatches ? 'changes-required' as const : !features.length || unknowns.length || !review ? 'review-required' as const : 'reviewed' as const,
    frameAspectMatches,
    findings, identityDrift: identityDrift.map(f => f.featureId),
    missingOrUnknown: unknowns.map(f => f.featureId),
    nextLayer: (['silhouette','proportions','parts','materials','microdetail'] as const).find(layer => findings.some(f => f.layer === layer && f.finding !== 'match')) ?? null,
    semanticAuthority: review ? `${review.reviewer}: ${review.method}` : 'none',
    semanticVerification: 'not independently established by NOETRA' };
}
export function visualStatus(state: VisualState, selectedAssetId?: string) {
  const candidate = selectedAssetId ? state.assets.find(a => a.id === selectedAssetId)
    : [...state.assets].reverse().find(a => a.role === 'candidate');
  const latestReview = candidate ? [...state.reviews].reverse().find(r => r.assetId === candidate.id && r.assetSha256 === candidate.sha256) : undefined;
  const selected = candidate ? evaluateReview(state, candidate, latestReview) : null;
  const missing3dViews = state.brief.required3dViews.filter(view => {
    const asset = [...state.assets].reverse().find(a => a.role === 'candidate' && a.view === view);
    if (!asset) return true;
    const review = [...state.reviews].reverse().find(r => r.assetId === asset.id && r.assetSha256 === asset.sha256);
    return evaluateReview(state, asset, review).outcome !== 'reviewed';
  });
  return { selected, anchorLocked: state.assets.some(a => a.role === 'anchor'),
    imageAttempts: state.jobs.length, imageAttemptsRemaining: Math.max(0, state.brief.maxImageAttempts - state.jobs.length),
    readyFor3dBrief: missing3dViews.length === 0, missing3dViews,
    limitations: ['Image digests prove file identity/integrity, not object identity or image quality.',
      'Visual assessments are attributed reviewer observations; numeric checks use supplied measurements.',
      'Reviewed reference views still do not uniquely determine hidden geometry, scale, materials or engineering feasibility.'] };
}
