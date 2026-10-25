import { NoetraEngine } from 'noetra';
const engine = new NoetraEngine({ projectRoot: process.cwd(), memoryPath: ':memory:' });
try {
  console.log(JSON.stringify(await engine.call('noetra.create_plan', {
    goal: 'Add articulated tail interaction to a mesh with no rig.', available: ['tail-mesh'],
    actions: [
      { id: 'animate', description: 'Implement tail animation', requires: ['tail-rig'] }
    ]
  }), null, 2));
} finally { engine.close(); }
