import { z } from 'zod';
import { NoetraEngine } from '../../../packages/core/src/index.js';
import type { Result } from '../../../packages/shared-types/src/index.js';

export const DemoInput = z.discriminatedUnion('example', [
  z.object({ example: z.literal('logic'), lowerBound: z.number().int().min(-100).max(100), claimBound: z.number().int().min(-100).max(100) }).strict(),
  z.object({ example: z.literal('planning'), testsPassed: z.boolean() }).strict(),
  z.object({ example: z.literal('evidence') }).strict()
]);

export async function runDemo(raw: unknown): Promise<{ title: string; summary: string; result: Result; privacy: string }> {
  const input = DemoInput.parse(raw);
  // Each run gets an independent, in-memory database. No visitor can retrieve
  // another visitor's records; REA and reconstruction are never configured.
  const engine = new NoetraEngine({ projectRoot: process.cwd(), memoryPath: ':memory:', projectId: 'isolated-demo' });
  let title: string, summary: string, result: Result;
  try {
    if (input.example === 'logic') {
      title = 'A formal claim, checked by Z3';
      result = await engine.call('noetra.verify_claim', {
        premises: [{ id: 'premise', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: input.lowerBound }],
        claim: { id: 'claim', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: input.claimBound }
      });
      summary = result.status === 'VERIFIED' ? `For integers, x ≥ ${input.lowerBound} entails x ≥ ${input.claimBound}.`
        : result.status === 'CONTRADICTED' ? `x ≥ ${input.lowerBound} does not guarantee x ≥ ${input.claimBound}. Inspect the counterexample below.`
          : 'No conclusion was obtained. Inspect the result below.';
    } else if (input.example === 'planning') {
      title = 'Plan a release with explicit prerequisites';
      result = await engine.call('noetra.create_plan', { goal: 'Release only when the test prerequisite is available', available: input.testsPassed ? ['tests-passed'] : [], actions: [
        { id: 'build', description: 'Build the package', provides: ['artifact'] },
        { id: 'review', description: 'Review the tested build', dependsOn: ['build'], requires: ['artifact', 'tests-passed'], provides: ['reviewed'] },
        { id: 'release', description: 'Prepare release', dependsOn: ['review'], requires: ['reviewed'] }
      ] });
      summary = input.testsPassed ? 'The supplied test prerequisite allows build → review → release.' : 'Review and release are blocked because tests-passed was not supplied.';
    } else {
      title = 'Keep an observation separate from a proof';
      result = await engine.call('noetra.record_evidence', { claim: 'One test installation succeeded',
        origin: { kind: 'tool', reference: 'Built-in demonstration fixture, not user telemetry', timestamp: '2026-10-25T00:00:00.000Z' },
        method: 'Store a fixed example observation', observation: 'CLI launched successfully in one controlled trial.',
        limitations: ['A single supplied observation does not establish universal installation success.'] });
      summary = 'The record is OBSERVED and untrusted, with a digest. It is not promoted to VERIFIED.';
    }
    return { title, summary, result, privacy: 'This run uses a fresh in-memory database, discarded afterward. No model API, telemetry, uploaded files or shared project memory.' };
  } finally { engine.close(); }
}
