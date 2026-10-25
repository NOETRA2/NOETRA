import { World, uniqueIds, fail } from '../../shared-types/src/index.js';
import type { Memory, RecordEntry } from '../../memory/src/index.js';

export function validateWorld(input: unknown): World {
  const world = World.parse(input);
  uniqueIds(world.entities); uniqueIds(world.assertions); uniqueIds(world.rules); uniqueIds(world.constraints);
  const entities = new Set(world.entities.map(x => x.id));
  for (const relation of world.relations) {
    if (!entities.has(relation.from) || !entities.has(relation.to)) fail('MISSING_ENTITY', 'Both relation endpoints must be present.');
  }
  const assertions = new Set(world.assertions.map(x => x.id));
  for (const rule of world.rules) {
    if (![...rule.when, rule.then].every(id => assertions.has(id))) fail('MISSING_ASSERTION', `Rule ${rule.id} references an absent assertion.`);
  }
  return world;
}
export function saveWorld(memory: Memory, input: unknown, id?: string, expectedRevision?: number): RecordEntry {
  return memory.put('world', validateWorld(input), { id, expectedRevision });
}
