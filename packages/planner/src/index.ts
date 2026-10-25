import { Action, uniqueIds, Id } from '../../shared-types/src/index.js';

export function createPlan(input: Action[], initial: string[] = []) {
  const actions = Action.array().max(300).parse(input); uniqueIds(actions);
  const available = new Set(Id.array().max(300).parse(initial));
  const indexed = new Map(actions.map(a => [a.id, a]));
  const completed = new Set(actions.filter(a => a.state === 'completed').map(a => a.id));
  for (const action of actions.filter(a => completed.has(a.id))) for (const effect of action.provides) available.add(effect);
  const pending = new Map(actions.filter(a => a.state === 'pending').map(a => [a.id, a]));
  const order: string[] = [], cycleNodes = new Set<string>(), stack: string[] = [], visited = new Set<string>();
  const visit = (id: string): void => {
    const position = stack.indexOf(id);
    if (position !== -1) { for (const item of stack.slice(position)) cycleNodes.add(item); return; }
    if (visited.has(id)) return;
    stack.push(id);
    for (const dep of indexed.get(id)?.dependsOn ?? []) if (indexed.has(dep)) visit(dep);
    stack.pop(); visited.add(id);
  };
  for (const a of actions) visit(a.id);
  let changed = true;
  while (changed) {
    changed = false;
    for (const [id, action] of pending) {
      if (cycleNodes.has(id) || !action.dependsOn.every(d => completed.has(d)) || !action.requires.every(r => available.has(r))) continue;
      order.push(id); completed.add(id); pending.delete(id);
      for (const effect of action.provides) available.add(effect);
      changed = true;
    }
  }
  const blocked = [...pending.values()].map(action => ({ id: action.id,
    missingDependencies: action.dependsOn.filter(id => !indexed.has(id)),
    unfinishedDependencies: action.dependsOn.filter(id => indexed.has(id) && !completed.has(id)),
    missingPreconditions: action.requires.filter(id => !available.has(id)),
    cycle: cycleNodes.has(action.id) }));
  return { order, blocked, cycles: [...cycleNodes],
    failed: actions.filter(a => a.state === 'failed').map(a => a.id),
    available: [...available], feasible: blocked.length === 0 && actions.every(a => a.state !== 'failed'),
    limitations: ['Effects and completed states are supplied premises. This monotonic planner does not model consumable resources, delete effects, action costs or general classical planning.'] };
}
