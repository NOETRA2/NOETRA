# Optional real-photo planar proof

This example is code only. No photographs, pretrained weights or generated models
are included in the npm core. See ../../docs/RECONSTRUCTION.md for scope and consent.

From a source checkout, explicitly download the small official OpenCV fixture:

```text
node scripts/fetch-reconstruction-fixture.mjs ABSOLUTE_NEW_FIXTURE_DIRECTORY
```

The downloader records URLs, hashes and upstream license. It never runs from MCP.
Create a dedicated project containing the reference files and operator config.
Use the SDK or configured MCP tools in this order:

```ts
const engine = new NoetraEngine({ projectRoot, reconstruction: {
  pythonExecutable, blenderExecutable, allowBlenderExecution: false
} });
const result = await engine.call('noetra.reconstruct_multiview', {
  pairs, pattern: [9, 6], holdoutPair: 0, initialScale: [1, 1]
});
// Check result.ok and keep result.data.runId. Square size remains relative unless supplied.
await engine.call('noetra.generate_3d_construction', { runId });
// Review the fixed script. Do not execute without human approval.
// A new engine/operator config with approved local execution can run:
await engine.call('noetra.optimize_reconstruction', { runId, maxEvaluations: 24 });
await engine.call('noetra.compare_reference_render', { runId });
await engine.call('noetra.export_reconstruction_report', { runId });
```

For the documented controlled correction benchmark only, initialScale was
[0.82, 1.18] intentionally. Do not present that deliberately perturbed baseline
as a naturally occurring failure or call the grid result a complete object/car.
The generic core noetra test does not require any optional reconstruction runtime.
