import { Candidate, Id, fail, uniqueIds } from '../../shared-types/src/index.js';

export interface ModelAdapter {
  readonly name: string;
  generate(request: { goal: string; requirements: string[]; maxCandidates: number; signal: AbortSignal }): Promise<unknown>;
}
export function rankCandidates(input: Candidate[], requirements: string[], maxCost: number) {
  const candidates = Candidate.array().max(32).parse(input); uniqueIds(candidates);
  const requested = Id.array().max(50).parse(requirements);
  if (!Number.isFinite(maxCost) || maxCost < 0 || maxCost > 1e9) fail('INVALID_BUDGET', 'Cost budget must be finite and nonnegative.');
  return { candidates: candidates.map(candidate => ({ ...candidate, status: 'HYPOTHESIS',
    missingRequirements: requested.filter(id => !candidate.satisfies.includes(id)),
    withinEstimatedBudget: candidate.estimatedCost <= maxCost
  })).sort((a, b) => a.missingRequirements.length - b.missingRequirements.length || Number(b.withinEstimatedBudget) - Number(a.withinEstimatedBudget) || a.estimatedCost - b.estimatedCost),
    model: 'host-supplied structured candidates; no hidden provider call',
    limitations: ['Requirement coverage and cost use supplied estimates, not empirical feasibility.', 'Novelty and subjective preferences are not verified; run the candidate test plans.'] };
}
