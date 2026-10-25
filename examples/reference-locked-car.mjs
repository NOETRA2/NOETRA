/** Explicit local demonstration. No provider invocation, host registration or external writes. */
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { NoetraEngine } from '../dist/packages/core/src/index.js';
const [operation, rootArgument, input] = process.argv.slice(2);
if (!rootArgument || !['prepare', 'refine', 'attach', 'review', 'status'].includes(operation)) throw new Error('Usage: node examples/reference-locked-car.mjs prepare|refine|attach|review|status PROJECT [INPUT]');
const root = resolve(rootArgument);
await mkdir(root, { recursive: true });
const sessionPath = resolve(root, 'session.json');
const engine = new NoetraEngine({ projectRoot: root });
const outputs = [];
async function call(action) {
  const result = await engine.call('noetra.design_visual', { action });
  if (!result.ok) throw new Error(JSON.stringify(result.error));
  outputs.push(result);
  return result.data;
}
try {
  let session;
  if (operation === 'prepare') {
    if (!input) throw new Error('Supply the original silver car reference PNG.');
    try { await readFile(sessionPath); throw new Error('Session exists; choose a new output folder.'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    const views = ['front-three-quarter', 'front', 'side', 'rear'];
    const feature = (id, description, layer, featureViews = ['front-three-quarter']) => ({ id, description, layer, importance: 'critical', views: featureViews, measure: { kind: 'appearance' } });
    const brief = {
      subject: 'The exact original silver futuristic sports coupe in the attached image, not a different hypercar.',
      goal: 'Refine existing details while preserving the original design and composition. Deliver one full-car front-three-quarter edit. Do not reinterpret geometry, invent a new fascia, add a wing, or claim unseen rear geometry is known.',
      identityFeatures: [
        feature('silhouette', 'Keep the original low, pointed nose, muscular silver wheel arches, sweeping low roof and exact visible body outline. Unseen views need additional reviewed references, not assumptions.', 'silhouette', views),
        feature('proportions', 'Keep wheelbase appearance, wheel size/placement, ground clearance, roof height and body overhangs unchanged.', 'proportions', views),
        feature('canopy', 'Keep the exact dark wraparound windshield, side-glass cutline, roof shape and mirror placement. Do not turn it into a bubble canopy.', 'parts'),
        feature('lamps', 'Keep the original angular cyan light outlines, their shape, location, scale and orientation; add no new lamp units.', 'parts'),
        feature('fascia', 'Keep the original black corner intakes, central intake, hood sculpting and black front splitter layout exactly as pictured.', 'parts'),
        feature('side-intake', 'Keep the existing behind-door vertical black intake and side sill geometry, with no extra vents or wing.', 'parts'),
        feature('wheels', 'Keep the original intricate dark split-spoke wheel pattern and orientation; do not substitute a different rim or add wheels.', 'parts'),
        feature('palette', 'Keep silver bodywork, dark glazing, black aerodynamic elements and restrained original cyan light accents. No logos.', 'materials', views),
        feature('composition', 'Keep camera position, lens perspective, full-car framing, neutral studio background and original light direction.', 'proportions')
      ],
      detailFeatures: [
        feature('panel-detail', 'Add fine, coherent panel seams and believable silver paint/reflections to existing surfaces only. No new body panels. Unseen views need review.', 'microdetail', views),
        feature('carbon-detail', 'Resolve subtle carbon-fibre texture on existing black splitter and sill areas without changing their outline.', 'microdetail'),
        feature('wheel-detail', 'Clarify existing wheel machining, visible brake rotors/calipers and natural tire sidewall/rubber tread; keep rim geometry and tire dimensions.', 'microdetail'),
        feature('lamp-detail', 'Refine the existing lamp lens, internal optics and cyan light diffusion without changing its outer shape.', 'microdetail'),
        feature('grille-detail', 'Add physically coherent depth and fine mesh only inside the existing black intake openings.', 'microdetail'),
        feature('glass-detail', 'Improve restrained windshield reflections and subtle visible cockpit detail without changing glazing boundaries or inventing seats outside the canopy.', 'microdetail')
      ], required3dViews: ['front', 'side', 'rear'], maxImageAttempts: 3
    };
    const created = await call({ kind: 'create', brief });
    const reference = resolve(root, 'original-car.png');
    await copyFile(resolve(input), reference);
    const anchored = await call({ kind: 'anchor', designId: created.record.id, expectedRevision: created.record.revision, path: reference, view: 'front-three-quarter' });
    const prepared = await call({ kind: 'prepare', designId: created.record.id, expectedRevision: anchored.record.revision, mode: 'detail-edit', view: 'front-three-quarter' });
    session = { designId: created.record.id, revision: prepared.record.revision, jobId: prepared.job.id, referenceIds: prepared.job.referenceIds };
    await writeFile(resolve(root, 'generation-handoff.json'), JSON.stringify(prepared.generation, null, 2));
    await writeFile(resolve(root, 'generation-prompt.txt'), prepared.generation.prompt);
  } else {
    session = JSON.parse(await readFile(sessionPath, 'utf8'));
    if (operation === 'attach') {
      const output = resolve(root, `car-${session.jobId}.png`);
      await copyFile(resolve(input), output);
      const attached = await call({ kind: 'attach-output', designId: session.designId, expectedRevision: session.revision, jobId: session.jobId, path: output, sourceReferenceIds: session.referenceIds, generator: 'Codex built-in imagegen; original-car.png supplied as the explicit reference-image input' });
      session.revision = attached.record.revision;
      session.assetId = attached.asset.id;
    }
    if (operation === 'review') {
      const observations = JSON.parse(await readFile(resolve(input), 'utf8'));
      const reviewed = await call({ kind: 'review', designId: session.designId, expectedRevision: session.revision, assetId: session.assetId, referenceIds: session.referenceIds, reviewer: 'host-model', method: 'Manual visual inspection of original and generated images by the host model; qualitative, not an independent vision metric or proof.', observations });
      session.revision = reviewed.record.revision;
    }
    if (operation === 'refine') {
      const prepared = await call({ kind: 'prepare', designId: session.designId, expectedRevision: session.revision, mode: 'detail-edit', view: 'front-three-quarter' });
      session.revision = prepared.record.revision;
      session.jobId = prepared.job.id;
      session.referenceIds = prepared.job.referenceIds;
      await writeFile(resolve(root, 'generation-handoff.json'), JSON.stringify(prepared.generation, null, 2));
      await writeFile(resolve(root, `generation-prompt-${session.jobId}.txt`), prepared.generation.prompt);
    }
    const status = await call({ kind: 'status', designId: session.designId, ...(session.assetId ? { assetId: session.assetId } : {}) });
    await writeFile(resolve(root, 'latest-status.json'), JSON.stringify(status, null, 2));
    if (session.assetId) {
      const modelling = await call({ kind: 'prepare', designId: session.designId, expectedRevision: session.revision, mode: '3d-brief', view: 'front' });
      await writeFile(resolve(root, '3d-gate.json'), JSON.stringify(modelling, null, 2));
    }
  }
  await writeFile(sessionPath, JSON.stringify(session, null, 2));
  await writeFile(resolve(root, `${operation}-results-r${session.revision}.json`), JSON.stringify(outputs, null, 2));
  console.log(JSON.stringify({ operation, root, ...session }));
} finally { engine.close(); }
