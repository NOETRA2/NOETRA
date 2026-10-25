import { z } from 'zod';
import { Id, Text, fail, uniqueIds } from '../../shared-types/src/index.js';

export const CausalLink = z.object({
  id: Id, cause: Id, effect: Id, when: z.boolean(), value: z.boolean(),
  evidenceIds: z.array(Id).max(32), rationale: Text
}).strict();
export const CausalInput = z.object({
  state: z.record(Id, z.boolean()), intervention: z.record(Id, z.boolean()),
  links: z.array(CausalLink).max(200)
}).strict();
export function intervene(input: z.infer<typeof CausalInput>) {
  const { state, intervention, links } = CausalInput.parse(input); uniqueIds(links);
  if (Object.keys(state).length + Object.keys(intervention).length > 300) fail('STATE_LIMIT', 'At most 300 state/intervention entries.');
  const predicted = { ...state, ...intervention }, locked = new Set(Object.keys(intervention));
  const transitions: Array<{ link: string; effect: string; value: boolean; evidenceIds: string[] }> = [];
  const conflicts = new Set<string>();
  const assigned = new Map<string, boolean>();
  let changed = true, iteration = 0;
  while (changed && iteration++ < 64) {
    changed = false;
    for (const link of links) if (predicted[link.cause] === link.when && !locked.has(link.effect)) {
      if (assigned.has(link.effect) && assigned.get(link.effect) !== link.value) { conflicts.add(link.effect); continue; }
      assigned.set(link.effect, link.value);
      if (predicted[link.effect] !== link.value) {
        predicted[link.effect] = link.value; changed = true;
        transitions.push({ link: link.id, effect: link.effect, value: link.value, evidenceIds: link.evidenceIds });
      }
    }
  }
  return { status: conflicts.size ? 'CONTRADICTED' : 'HYPOTHESIS', predicted, transitions, conflicts: [...conflicts],
    limitations: ['Predictions use supplied deterministic causal hypotheses, not learned or experimentally established causation.', 'Conflicting effects require a new experiment; correlation is not proof of causation.'] };
}
