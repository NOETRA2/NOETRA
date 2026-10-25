import { parentPort, workerData } from 'node:worker_threads';
import { init, killThreads } from 'z3-solver';
import type { Arith } from 'z3-solver';
import { Constraint } from '../../shared-types/src/index.js';
import type { FormalResult } from './index.js';

async function run(): Promise<void> {
  const data = workerData as { constraints: unknown; claim?: unknown };
  const constraints = Constraint.array().max(128).parse(data.constraints);
  const claim = data.claim === undefined ? undefined : Constraint.parse(data.claim);
  const api = await init();
  try {
    const context = new api.Context('noetra');
    const solver = new context.Solver();
    solver.set('timeout', 3000);
    const expression = (c: Constraint) => {
      const sum = c.terms.reduce<Arith<'noetra'>>((acc, term) => acc.add(context.Int.const(term.variable).mul(term.coefficient)), context.Int.val(0));
      switch (c.relation) {
        case 'eq': return sum.eq(c.value);
        case 'ne': return sum.neq(c.value);
        case 'lt': return sum.lt(c.value);
        case 'le': return sum.le(c.value);
        case 'gt': return sum.gt(c.value);
        case 'ge': return sum.ge(c.value);
      }
    };
    solver.add(...constraints.map(expression));
    const consistency = await solver.check();
    const output: FormalResult = { consistency, constraintIds: constraints.map(c => c.id),
      method: 'Z3 integer linear arithmetic', limitations: ['Formal validity is conditional on the supplied premises and integer encoding; it does not establish empirical truth.'] };
    const names = [...new Set([...constraints, ...(claim ? [claim] : [])].flatMap(c => c.terms.map(t => t.variable)))];
    if (claim) {
      if (consistency === 'unsat') output.entailment = 'inconsistent-premises';
      else if (consistency === 'unknown') output.entailment = 'unknown';
      else {
        solver.add(context.Not(expression(claim)));
        const counter = await solver.check();
        output.entailment = counter === 'unsat' ? 'entailed' : counter === 'sat' ? 'counterexample' : 'unknown';
        if (counter === 'sat') output.model = Object.fromEntries(names.map(name => [name, solver.model().eval(context.Int.const(name), true).toString()]));
      }
    } else if (consistency === 'sat') output.model = Object.fromEntries(names.map(name => [name, solver.model().eval(context.Int.const(name), true).toString()]));
    parentPort?.postMessage({ result: output });
  } finally { await killThreads(api.em); }
}
void run().catch(() => { parentPort?.postMessage({ error: 'SOLVER_FAILED' }); });
