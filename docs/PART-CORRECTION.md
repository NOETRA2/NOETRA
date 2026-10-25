# Reusable part correction and guided outline construction

These are implemented local operations, not the complete 14-phase reconstruction
specification. They require the optional Python/Blender operator configuration
from RECONSTRUCTION.md. No dependencies, pretrained weights, cloud services,
credentials or global AI-client settings are installed or changed automatically.

## Initial shape from a front drawing

`noetra.build_outline_model` accepts a project-local PNG/JPEG reference and exactly
one of an attributed `outlinePx` polygon or a binary foreground-mask image. Mask
tracing supports one connected outer contour, without holes. The caller must
explicitly select `cameraAssumption: "front-orthographic"`.

The operation preserves originals and writes an editable SVG outline, front
boundary-to-vertex mapping, spatial JSON, an actual Blender scene and GLB. The
observed contour constrains the front. Proposed cross-sections and a caller-chosen
relative depth generate side/rear geometry. Front surface fill, hidden surfaces,
depth, physical scale and internal parts are **not recovered observations**.

A real front render is compared with the observed mask. The initial front fit is
accepted only if silhouette IoU is at least .98 and mean boundary distance at most
1.5 pixels. Failures remain labelled review drafts. A matching front silhouette
does not establish accurate depth, surfaces or missing parts. A separate side
render shows the proposed geometry; it is not compared to an invented side image.

Example SDK/MCP input:

```json
{
  "reference": "C:/project/front.png",
  "foregroundMask": "C:/project/front-mask.png",
  "provenance": "User-reviewed outer silhouette; side and rear unobserved",
  "cameraAssumption": "front-orthographic",
  "frontWidthUnits": 2,
  "proposedDepthRatio": 0.75,
  "proposedSections": [
    {"t": 0, "scaleX": 1, "scaleZ": 1},
    {"t": 0.3, "scaleX": 0.95, "scaleZ": 0.95},
    {"t": 1, "scaleX": 0.8, "scaleZ": 0.8}
  ]
}
```

This is suitable for a constrained front drawing, not an uncalibrated three-quarter
car photograph. Automatic general segmentation, perspective/depth inference and
semantic completion need additional configured vision/geometry capabilities.

## Correct an existing model without rebuilding it

1. `noetra.prepare_part_correction`: copy the source BLEND and reference images
   into a new run, preserve runtime snapshots, render initial images/masks and
   fingerprint scene objects, evaluated geometry, materials, lights and cameras.
2. `noetra.correct_parts`: rank the current annotated part mismatches, try bounded
   coordinate changes to declared controls, render each candidate and decide
   whether to keep it. Each trial records a prediction and accepted checkpoint
   before execution. Failed or worse candidates never replace the accepted best.
3. `noetra.inspect_part_correction`: verify source/artifact identity and return
   per-part measurements, decisions and exact BLEND/GLB checkpoint paths.

The controls are generic data bindings, not per-car Python:

- `translate`: move the named part's objects along one world-space axis.
- `mesh_offset`: offset selected vertex indices in one object's local axis.
- `curve_offset`: offset selected poly/Bezier controls in one local axis/spline.

Bounds, steps, object ownership and selected indices are validated. Shared mesh
data is copied before editing. Parent/child dependencies are not silently granted:
if an edit changes an undeclared child, the fingerprint gate rejects it. Changes
that require coordinated dependent parts must be explicitly grouped as one part.
The saved scene is loaded and only declared controls are edited; no car generator
is rerun and there are no asset templates or executable source strings in inputs.

Example:

```json
{
  "blend": "C:/project/source.blend",
  "collection": "PRODUCT",
  "parts": [{"id": "lamp", "objects": ["Lamp housing", "Lamp trim"]}],
  "parameters": [{
    "id": "lamp-x", "partId": "lamp", "kind": "translate", "axis": "X",
    "minimum": -0.2, "maximum": 0.2, "step": 0.02
  }],
  "views": [{
    "id": "front", "camera": "Front camera", "reference": "C:/project/front.png",
    "annotations": [{"partId": "lamp", "polygon": [[20,20],[90,20],[90,40],[20,40]],
      "provenance": "User-reviewed visible lamp boundary"}]
  }]
}
```

Then call `correct_parts` with the returned `runId` and `maxCandidates` (1–6),
followed by `inspect_part_correction`. The correction module needs a supported
existing initial mesh; it does not infer a complete car from arbitrary images.

## Acceptance and preservation

- Every annotated view must retain or improve overlap and mean boundary error.
  A target's average boundary/overlap loss must measurably improve.
- All scene objects outside the active edit must have identical fingerprints.
  Cameras, lights, the world, frame and object inventory are protected.
- Flat geometric part-ID masks test visibility changes outside a fixed influence
  region derived from the reference and accepted baseline, not from the candidate.
  The candidate cannot grant itself a larger region.
- Per-part overlays use green for the attributed reference boundary and magenta
  for the actual rendered boundary. Masks and pixel arrays stay in files.
- Each immutable candidate has its own BLEND, GLB, actual beauty/ID renders,
  measurements and fingerprints. The best path points to an accepted checkpoint;
  rejected candidates stay available for diagnosis.

IDs are generated from stable object names in the prepared scene. Persistent part
IDs live in the manifest. Renaming/replacing the source requires a new run.
Original scene/reference changes or artifact mutations invalidate a run. Runtime
snapshots preserve new runs' evidence across application updates; continuing an
old correction after helper changes requires a new run/migration. Read-only
historical evidence remains distinct from a new experiment.

## Limits and execution

Polygon observations are supplied and attributed, not automatic semantic
segmentation or proof that a reflection is a physical edge. A curve can be treated
as its own part to compare a seam/contour, but unannotated internal details,
intrinsic materials, normal/depth fidelity and unknown geometry are not scored.
ID passes treat glass as opaque; they measure geometric coverage, not optics.

Strict preservation can reject a useful local change when a scene has overlapping
coplanar faces or ambiguous visibility elsewhere. Diagnose the conflicting
geometry; do not disable the gate and claim success. The bounded search is a
coordinate search, not a differentiable/global optimizer. It can stop at a local
optimum or after exhausting useful controls. Additional parts/topology need a new
explicitly authored or externally reconstructed initial model.

Only trusted project-local scenes are supported. Blender runs in fresh background
processes with automatic script execution disabled and task-local resource paths.
External textures/libraries/caches, dynamic/animated scenes and unsupported
modifiers are rejected by the adapter. This is not an OS sandbox for hostile BLEND
files. No remote image transmission occurs. If a process is interrupted, keep its
best checkpoint and start a new run from it rather than deleting unknown locks.

REA remains the integrated software-investigation service. It does not provide
photogrammetry or image-to-mesh inference. COLMAP/PyCOLMAP, VGGT, MapAnything,
Open3D and Mitsuba runtime integrations remain unfinished and are not claimed
as installed or tested by these operations.
