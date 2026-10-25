import { NoetraEngine } from 'noetra';
// An explicit host encoding, not an automatic interpretation of arbitrary prose.
const engine = new NoetraEngine({ projectRoot: process.cwd(), memoryPath: ':memory:' });
try {
  const result = await engine.call('noetra.check_logic', { world: {
    goal: 'Build a battery-powered system that uses no stored or external energy.',
    constraints: [
      { id: 'no-energy', terms: [{ variable: 'energy', coefficient: 1 }], relation: 'eq', value: 0 },
      { id: 'positive-demand', terms: [{ variable: 'energy', coefficient: 1 }], relation: 'gt', value: 0 }
    ],
    unknowns: ['Actual power/load measurements are not available.', 'The positive energy-demand premise is a supplied physical model, not an observed measurement.']
  } });
  console.log(JSON.stringify({ result, alternatives: ['Allow stored battery energy.', 'Allow an external supply.', 'Specify zero powered operation rather than an operating powered device.'] }, null, 2));
} finally { engine.close(); }
