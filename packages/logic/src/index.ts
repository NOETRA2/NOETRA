import { Worker } from 'node:worker_threads';
import { Constraint, fail, uniqueIds } from '../../shared-types/src/index.js';
import type { World } from '../../shared-types/src/index.js';

export interface Deduction {
  active: string[]; derivations: Array<{ assertionId: string; ruleId: string; premises: string[] }>;
  contradictions: Array<{ proposition: string; assertionIds: string[] }>;
  assumptions: string[]; complete: boolean; iterations: number;
}
export function deduce(world: World, iterationLimit = 64): Deduction {
  const active = new Set(world.assertions.filter(a => a.classification !== 'unknown').map(a => a.id));
  const derivations: Deduction['derivations'] = [];
  let iterations = 0, changed = true;
  while (changed && iterations < Math.max(1, Math.min(64, iterationLimit))) {
    iterations++; changed = false;
    for (const rule of world.rules) if (!active.has(rule.then) && rule.when.every(id => active.has(id))) {
      active.add(rule.then); derivations.push({ assertionId: rule.then, ruleId: rule.id, premises: [...rule.when] }); changed = true;
    }
  }
  const byText = new Map<string, { positive: string[]; negative: string[] }>();
  for (const assertion of world.assertions.filter(a => active.has(a.id))) {
    const key = assertion.proposition.trim().toLowerCase().replace(/\s+/g, ' ');
    const group = byText.get(key) ?? { positive: [], negative: [] };
    (assertion.negated ? group.negative : group.positive).push(assertion.id); byText.set(key, group);
  }
  const contradictions = [...byText.entries()].filter(([, x]) => x.positive.length && x.negative.length)
    .map(([proposition, x]) => ({ proposition, assertionIds: [...x.positive, ...x.negative] }));
  return { active: [...active], derivations, contradictions,
    assumptions: world.assertions.filter(a => a.classification === 'assumption').map(a => a.id),
    complete: !changed, iterations };
}
export interface FormalResult {
  consistency: 'sat' | 'unsat' | 'unknown';
  entailment?: 'entailed' | 'counterexample' | 'unknown' | 'inconsistent-premises';
  model?: Record<string, string>; constraintIds: string[];
  method: 'Z3 integer linear arithmetic'; limitations: string[];
}
export async function solve(input: Constraint[], claim?: Constraint, signal?: AbortSignal): Promise<FormalResult> {
  const constraints = Constraint.array().max(128).parse(input);
  const parsedClaim = claim === undefined ? undefined : Constraint.parse(claim);
  uniqueIds(constraints);
  const names = new Set([...constraints, ...(parsedClaim ? [parsedClaim] : [])].flatMap(c => c.terms.map(t => t.variable)));
  if (names.size > 32) fail('VARIABLE_LIMIT', 'At most 32 integer variables per solver request.');
  signal?.throwIfAborted();
  return new Promise<FormalResult>((resolve, reject) => {
    // Process-independent worker termination bounds WASM initialization and solving as well as wall time.
    const worker = new Worker(new URL('./solver-worker.js', import.meta.url), {
      workerData: { constraints, claim: parsedClaim }, resourceLimits: { maxOldGenerationSizeMb: 128 }
    });
    let settled = false;
    const finish = (error?: unknown, result?: FormalResult): void => {
      if (settled) return; settled = true;
      clearTimeout(timer); signal?.removeEventListener('abort', abort);
      void worker.terminate();
      if (error) reject(error); else if (result) resolve(result);
    };
    const abort = (): void => finish(new Error('Solver request cancelled.'));
    const timer = setTimeout(() => finish(undefined, {
      consistency: 'unknown', entailment: parsedClaim ? 'unknown' : undefined,
      constraintIds: constraints.map(c => c.id), method: 'Z3 integer linear arithmetic',
      limitations: ['Solver worker exceeded the 10-second wall-time budget; no proof was obtained.']
    }), 10000);
    signal?.addEventListener('abort', abort, { once: true });
    worker.once('message', (message: { result?: FormalResult; error?: string }) => {
      if (message.error) finish(new Error('Z3 solver failed; no conclusion obtained.'));
      else finish(undefined, message.result);
    });
    worker.once('error', error => finish(error));
    worker.once('exit', code => { if (!settled) finish(new Error(`Solver worker exited before a result (${code}).`)); });
  });
}
