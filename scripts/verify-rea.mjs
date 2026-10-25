import { NoetraEngine } from '../dist/packages/sdk/src/index.js';
import { inspectPackage } from '../dist/packages/integrations/rea/src/index.js';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir, writeFile } from 'node:fs/promises';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const packageDirectory = process.argv[2];
if (!packageDirectory) throw new Error('Pass an already installed official rea-agents 6.7.0 package directory. Nothing will be downloaded.');
const identity = await inspectPackage(resolve(packageDirectory));
const target = resolve(root, 'examples/software-investigation/electron-sample');
const evidenceDirectory = resolve(root, '.noetra/verification');
await mkdir(evidenceDirectory, { recursive: true });
const engine = new NoetraEngine({ projectRoot: root, memoryPath: resolve(evidenceDirectory, 'rea.sqlite'), projectId: 'authorized-synthetic-fixture',
  rea: { enabled: true, packageDirectory: identity.root, allowedRoots: [target], version: '6.7.0' } });
try {
  const result = await engine.call('noetra.investigate_software', {
    target, scope: 'Static navigation IPC boundary in the NOETRA-owned synthetic Electron fixture.',
    authorization: 'User requested NOETRA development and real REA integration verification; this fixture was created solely for that test.',
    sourcePaths: ['package.json', 'main.js', 'preload.js']
  });
  await writeFile(resolve(evidenceDirectory, 'rea-investigation.json'), JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
  const record = result.data.record;
  if (result.ok) {
    const summary = record?.value?.rawResult?.structuredContent?.normalized_result?.summary;
    if (summary?.electron?.ipc?.unpaired_literal_renderer_transmissions !== 1 || record?.value?.sourceViews?.length !== 1) {
      throw new Error('The synthetic fixture investigation did not retain the expected static IPC finding/source view.');
    }
    const rows = record.value.sourceViews[0].structuredContent.normalized_result.rows;
    const invoke = rows.find(row => row.properties?.operation === 'invoke' && row.properties?.channel);
    const handler = rows.find(row => row.kind === 'ipc-handler' && row.properties?.channel);
    if (!invoke || !handler || invoke.properties.channel === handler.properties.channel) throw new Error('Expected the deliberately mismatched literal IPC channels in the actual REA evidence.');
    const sourceReference = row => `REA ${record.value.version}; ${record.value.parentEvidenceId}; ${row.observation_id}; ${JSON.stringify(row.evidence.location)}`;
    const world = await engine.call('noetra.build_world_model', { world: {
      goal: 'Explain the static navigation boundary in the authorized Electron fixture.',
      entities: [
        { id: 'preload-invoke', type: 'ipc-operation', properties: { channel: invoke.properties.channel } },
        { id: 'main-handler', type: 'ipc-handler', properties: { channel: handler.properties.channel } }
      ],
      relations: [{ from: 'preload-invoke', to: 'main-handler', kind: 'distinct-literal-channel-names', evidenceIds: [record.id] }],
      assertions: [invoke, handler].map((row, index) => ({ id: `static-channel-${index}`,
        proposition: `Selected static ${row.kind}: ${row.properties.operation} ${row.properties.channel}`,
        classification: 'premise', origin: { kind: 'tool', reference: sourceReference(row), timestamp: record.value.timestamp }, evidenceIds: [record.id] })),
      unknowns: ['Runtime registration/reachability was not tested.', 'The unselected HTML and unknown graph scopes may contain other behavior.']
    } });
    const plan = await engine.call('noetra.create_plan', { goal: 'Independently implement and test a matching navigation boundary; no GUI reconstruction.',
      available: ['static-ipc-evidence'], actions: [
        { id: 'contract', description: 'Define one literal channel and accepted HTTPS URL contract.', requires: ['static-ipc-evidence'], provides: ['channel-contract'] },
        { id: 'boundary', description: 'Build an independent pure URL boundary and use the same channel at both ends.', dependsOn: ['contract'], requires: ['channel-contract'], provides: ['boundary-code'] },
        { id: 'tests', description: 'Test allowed URLs and reject file, script and credential-bearing URLs.', dependsOn: ['boundary'], requires: ['boundary-code'], provides: ['tested-boundary'] }
      ] });
    if (!world.ok || !plan.ok || plan.status !== 'DERIVED') throw new Error('Evidence-to-world/planning workflow failed.');
    await writeFile(resolve(evidenceDirectory, 'rea-workflow.json'), JSON.stringify({ investigationId: record.id,
      world, plan, conclusions: [
        { status: 'OBSERVED', claim: 'REA retained different literal invoke and handler channels in the selected sources.', evidence: [invoke.observation_id, handler.observation_id] },
        { status: 'DERIVED', claim: 'Those two literal channel strings do not match; this is a static boundary defect in the intentionally incomplete fixture.' },
        { status: 'UNKNOWN', claim: 'Runtime behavior and complete application coverage were not verified.' }
      ] }, null, 2) + '\n', { mode: 0o600 });
  }
  console.log(JSON.stringify({ ok: result.ok, status: result.status, error: result.error,
    recordId: record?.id, tool: record?.value?.tool, version: record?.value?.version,
    discoveredToolCount: record?.value?.discoveredToolCount,
    evidenceFile: resolve(evidenceDirectory, 'rea-investigation.json'), limitations: result.limitations }, null, 2));
  if (!result.ok) process.exitCode = 1;
} finally { engine.close(); }
