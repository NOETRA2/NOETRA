import { describe, expect, test } from 'vitest';
import { validateWorld } from '../../packages/world-model/src/index.js';
import { deduce, solve } from '../../dist/packages/logic/src/index.js';
import { createPlan } from '../../packages/planner/src/index.js';
import { intervene } from '../../packages/causality/src/index.js';
import { rankCandidates } from '../../packages/imagination/src/index.js';
import { compareExperiment } from '../../packages/verification/src/index.js';
import { approvedNavigation } from '../../examples/software-investigation/independent-navigation.js';
const origin = { kind: 'user' as const, reference: 'test premise', timestamp: '2026-10-24T00:00:00.000Z' };
const assertion = (id: string, proposition: string, classification: 'premise' | 'assumption' | 'unknown' = 'premise', negated = false) => ({ id, proposition, classification, negated, evidenceIds: [], origin });
const term = (id: string, variable: string, relation: 'eq' | 'ge' | 'le' | 'gt', value: number) => ({ id, terms: [{ variable, coefficient: 1 }], relation, value });
describe('actual deterministic reasoning', () => {
  test('deduces through rules, tracks assumptions and detects explicit opposite propositions', () => {
    const world = validateWorld({ goal: 'test', assertions: [assertion('a', 'power available', 'assumption'), assertion('b', 'motor moves', 'unknown'), assertion('c', 'motor moves', 'premise', true)], rules: [{ id: 'r1', when: ['a'], then: 'b' }] });
    const result = deduce(world);
    expect(result.active).toContain('b'); expect(result.assumptions).toEqual(['a']);
    expect(result.contradictions[0]?.assertionIds).toEqual(['b', 'c']); expect(result.complete).toBe(true);
  });
  test('does not infer meaning from unrelated natural language', () => {
    const result = deduce(validateWorld({ goal: 'ambiguous', assertions: [assertion('a', 'a cat'), assertion('b', 'not a cat')] }));
    expect(result.contradictions).toEqual([]);
  });
  test('rejects duplicate IDs, broken relation endpoints and dangling rule references', () => {
    expect(() => validateWorld({ goal: 'x', entities: [{ id: 'a', type: 'x' }, { id: 'a', type: 'y' }] })).toThrow();
    expect(() => validateWorld({ goal: 'x', relations: [{ from: 'a', to: 'b', kind: 'uses' }] })).toThrow();
    expect(() => validateWorld({ goal: 'x', rules: [{ id: 'r', when: ['a'], then: 'b' }] })).toThrow();
  });
  test('battery energy constraints conflict under explicit conservation encoding (A)', async () => {
    const result = await solve([term('no-energy', 'energy', 'eq', 0), term('needs-energy', 'energy', 'gt', 0)]);
    expect(result.consistency).toBe('unsat'); expect(result.method).toContain('Z3');
  });
  test('proves implication and produces a counterexample, not an invented proof', async () => {
    const positive = await solve([term('premise', 'x', 'ge', 2)], term('claim', 'x', 'ge', 1));
    expect(positive.entailment).toBe('entailed');
    const negative = await solve([term('premise', 'x', 'ge', 2)], term('claim', 'x', 'ge', 3));
    expect(negative.entailment).toBe('counterexample'); expect(negative.model?.x).toBe('2');
  });
  test('does not prove claims from inconsistent premises', async () => {
    const result = await solve([term('a', 'x', 'ge', 2), term('b', 'x', 'le', 1)], term('claim', 'x', 'ge', 10));
    expect(result.entailment).toBe('inconsistent-premises');
  });
  test('rejects arbitrary generated code and excessive solver variables', async () => {
    await expect(solve([{ ...term('x', 'a', 'eq', 1), code: 'process.exit()' } as never])).rejects.toThrow();
    await expect(solve(Array.from({ length: 33 }, (_, i) => term(`id${i}`, `v${i}`, 'eq', i)))).rejects.toThrow();
  });
  test('honors already-cancelled solver requests', async () => {
    await expect(solve([], undefined, AbortSignal.abort())).rejects.toThrow();
  });
  test('missing rig blocks animation until a rig-building action is added (D)', () => {
    const blocked = createPlan([{ id: 'animate', description: 'Animate tail', requires: ['tail-rig'], dependsOn: [], provides: [], state: 'pending' }], ['tail-mesh']);
    expect(blocked.feasible).toBe(false); expect(blocked.blocked[0]?.missingPreconditions).toEqual(['tail-rig']);
    const fixed = createPlan([{ id: 'animate', description: 'Animate', requires: ['tail-rig'], dependsOn: [], provides: [], state: 'pending' },
      { id: 'rig', description: 'Create rig', requires: ['tail-mesh'], dependsOn: [], provides: ['tail-rig'], state: 'pending' }], ['tail-mesh']);
    expect(fixed.order).toEqual(['rig', 'animate']); expect(fixed.feasible).toBe(true);
  });
  test('cycles, missing tasks and failed dependencies block planning', () => {
    const a = { id: 'a', description: 'A', dependsOn: ['b'], requires: [], provides: [], state: 'pending' as const };
    expect(createPlan([a, { ...a, id: 'b', dependsOn: ['a'] }]).cycles.sort()).toEqual(['a', 'b']);
    expect(createPlan([a]).blocked[0]?.missingDependencies).toEqual(['b']);
    expect(createPlan([a, { ...a, id: 'b', dependsOn: [], state: 'failed' }]).feasible).toBe(false);
  });
  test('ranks host concepts transparently without certifying subjective novelty (C)', () => {
    const concept = { id: 'a', concept: 'Gentle breathing navigation', origin, components: ['reduced motion'], satisfies: ['quiet'], estimatedCost: 2, risks: ['distraction'], testPlan: ['Compare task completion with reduced motion enabled.'] };
    const result = rankCandidates([concept, { ...concept, id: 'b', concept: 'Static focus mode', estimatedCost: 1 }], ['quiet'], 5);
    expect(result.candidates[0]?.id).toBe('b'); expect(result.candidates[0]?.status).toBe('HYPOTHESIS');
    expect(result.limitations.join(' ')).toContain('subjective');
  });
  test('causal intervention is a prediction and conflicting explanations are flagged', () => {
    const link = { id: 'r', cause: 'switch', effect: 'light', when: true, value: true, evidenceIds: [], rationale: 'assumed circuit' };
    expect(intervene({ state: { switch: false, light: false }, intervention: { switch: true }, links: [link] }).predicted.light).toBe(true);
    expect(intervene({ state: { switch: true }, intervention: {}, links: [link, { ...link, id: 'conflict', value: false }] }).status).toBe('CONTRADICTED');
    expect(intervene({ state: { switch: true }, intervention: { light: false }, links: [link] }).predicted.light).toBe(false);
  });
  test('predicted vs observed mismatch is a contradiction, not verification', () => {
    expect(compareExperiment(true, false, ['ev1']).status).toBe('CONTRADICTED');
    expect(compareExperiment(true, true, ['ev1']).status).toBe('OBSERVED');
  });
  test('independent navigation boundary rejects nonweb/credential-bearing URLs', () => {
    expect(approvedNavigation('https://example.com')).toBe('https://example.com/');
    for (const address of ['file:///private', 'javascript:alert(1)', 'https://user:pass@example.com']) expect(() => approvedNavigation(address)).toThrow();
  });
});
