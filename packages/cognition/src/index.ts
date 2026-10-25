import { randomUUID } from 'node:crypto';
import { World } from '../../shared-types/src/index.js';
import type { Assertion } from '../../shared-types/src/index.js';

export function perceive(text: string, assertions: Assertion[] = []): World {
  // No hidden LLM call: user wording remains an attributed statement, not an established fact.
  return World.parse({ goal: text, assertions: [{
    id: `input:${randomUUID()}`, proposition: text,
    classification: 'assumption', negated: false, evidenceIds: [],
    origin: { kind: 'user', reference: 'input text; semantics not independently verified', timestamp: new Date().toISOString() }
  }, ...assertions], unknowns: assertions.length ? [] : ['Host must supply structured assertions/constraints for formal reasoning.'] });
}
