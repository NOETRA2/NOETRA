import { createHash, randomUUID } from 'node:crypto';
import { EvidenceInput } from '../../shared-types/src/index.js';
import type { Constraint, Evidence, Status } from '../../shared-types/src/index.js';
import { solve } from '../../logic/src/index.js';

export function recordObservation(input: EvidenceInput): Evidence {
  const evidence = EvidenceInput.parse(input);
  return { ...evidence, id: randomUUID(), digest: createHash('sha256').update(evidence.observation).digest('hex'),
    status: 'OBSERVED', untrusted: true };
}
export async function verifyFormal(constraints: Constraint[], claim: Constraint, signal?: AbortSignal) {
  const result = await solve(constraints, claim, signal);
  const status: Status = result.entailment === 'entailed' ? 'VERIFIED'
    : result.entailment === 'counterexample' || result.entailment === 'inconsistent-premises' ? 'CONTRADICTED' : 'UNKNOWN';
  return { status, ...result, scope: 'Claim follows from the supplied consistent integer premises; no claim of real-world truth.',
    nextExperiment: result.entailment === 'counterexample' ? 'Inspect the counterexample or revise the premises/claim.' : 'Independently measure whether the premises match the target system.' };
}
export function compareExperiment(predicted: boolean | number | string, observed: boolean | number | string, evidenceIds: string[]) {
  return { status: predicted === observed ? 'OBSERVED' : 'CONTRADICTED', predicted, observed, evidenceIds,
    limitations: ['Comparison checks exact equality of supplied values; imported evidence authenticity and causality remain unverified.'] };
}
