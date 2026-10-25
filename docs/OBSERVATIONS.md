# Attributed observations and geometric matching

`packages/reconstruction/python/observations.py` and `shape_matching.py` are
local numerical building blocks. They do not run a semantic model, create a
template, upload images, download weights, execute supplied code, or add missing
3D parts. An image-space ellipse is not proof of a physical 3D circle.

## ObservationSet version 1

`validate_observation_set(project_root, spec, expected_sha256=None)` validates
all inputs and rechecks original image and mask bytes. Paths resolve within the
project, images are PNG/JPEG up to 8 million pixels/32 MB each, and total image
and retained mask pixel budgets are bounded. It returns `sha256`, stable `parts`
and `views` dictionaries, scale and explicit limitations. The hash identifies the
canonical complete specification, including annotations, camera, provenance and
part ownership; pass it as `expected_sha256` when continuing a saved correction.
The caller persists the specification and this digest in an immutable run.

Required top-level fields are `schemaVersion: 1`, `provenance`, `parts`, `views`
and `scale`. Unknown fields fail validation. `scale` contains `status` (relative
or measured), `units`, numeric `uncertainty` and `provenance`. Measured scale also
requires a positive `unitsPerMeter`; this is an attributed measurement.

Each part supplies `id`, `label`, `objects`, boolean `locked` and `provenance`.
IDs follow `[a-z][a-z0-9-]{0,63}` and persist across views and corrections. Object
ownership is exclusive. The module checks the contract; a scene adapter must
also verify that the actual named objects exist and fingerprint their geometry.

Each view supplies:

- `id`, `image: {path, sha256}`, `role` (fit, heldout or inspection).
- `origin: {kind, captureId, provenance}`. Kind is actual_photo,
  reference_artwork, generated or rendered. A primary desired design image,
  including AI-created artwork, can be reference_artwork and serve as a fit
  constraint. This means matching the intended drawing, not measuring a physical
  object. Reference artwork can optionally declare known `parentViewIds`.
  Generated auxiliary viewpoints and rendered mesh views additionally supply
  `parentViewIds` and can only serve as inspection. Reference artwork is never
  heldout independent physical evidence. Lineage cycles are rejected. Independent actual
  views must have different source bytes and capture IDs; changing filenames
  does not make a held-out view independent. Origin is an attributed claim,
  not an authenticity detector.
- `camera: {convention, K, R, t, uncertaintyPx, provenance}`. The sole supported
  convention is `opencv-world-to-camera-x-right-y-down-z-forward`:
  `X_camera = R @ X_world + t`; `pixel ~ K @ X_camera`. Rotation must be proper
  orthonormal. A Blender adapter converts conventions explicitly. Keep source
  observation cameras immutable and create separate presentation cameras.
- `observations`: per-part records containing `partId`, `provenance`,
  `uncertaintyPx`, and at least one of `mask`, `keypoints` or `ellipseBoundary`.
  Masks use `{path, sha256}`, match the image dimensions and contain only 0/255.
  They represent visible part pixels and cannot overlap another visible part.
  Keypoints map stable names to `[x,y]` in original-image pixels. Ellipse boundary
  samples are 12–4096 attributed outer-boundary pixel coordinates, not arbitrary
  spoke or center features. Optional `requireCompleteEllipse: true` fails closed
  when the mask/boundary support is incomplete.

Loaded view records expose `size: [width,height]`, a `parts` dictionary with
`maskArray` and optional `ellipse` diagnostics, and `independentValidation`.
`fit_observed_ellipse(mask=...)` or
`fit_observed_ellipse(keypoints=..., image_size=(width,height))` estimates center,
semi-axes and rotation. Diagnostics include angular support, radial residual,
mask/ellipse overlap and contact with the image boundary. Complete-wheel use
requires full boundary support; an occluded or cut-off wheel remains incomplete.
If both mask and boundary samples exist, both must support completeness.

## Proposals and acceptance

`measure_shape(observed_mask, rendered_mask, observed_keypoints=None,
rendered_keypoints=None)` measures silhouette IoU, symmetric boundary mean/p95
and named-landmark RMSE. Masks must come from actual projected geometry using
the observation camera; a texture image is not a geometry mask.

`propose_part_parameters(parameters, residual, jacobian, locked_parts=(),
uncertainty=None)` solves a bounded least-squares local step. Each parameter has
exactly `id`, `partId`, `value`, `minimum`, `maximum`, `maxStep`. Residuals are
predicted minus observed. Jacobian columns use the same parameter order and must
come from actual fixed-camera render finite differences. Positive uncertainty
values weight the residuals. Locked controls remain exactly unchanged; bounds
and the trust step cap apply together. Predicted improvement is only a proposal:
apply declared controls to a checkpoint, render actual candidate geometry and
measure it again before accepting it.

`correction_gate(before, after, before_fingerprints, after_fingerprints,
editable_parts, heldout_views=())` consumes maps of view IDs to
`{origin: "actual_photo", role: "fit", parts: {partId: metrics}}`, with
`origin: "reference_artwork"` also allowed for fit constraints. Pass
`origin["kind"]` from the ObservationSet. Fingerprints have exactly `cameras`
and `parts`, each mapping actual IDs to geometry/camera hashes. Before and after
must reference the same pinned ObservationSet. The gate rejects changed cameras,
locked geometry, changed view/part coverage, geometry regression, and generated
or rendered auxiliary hypotheses used as validation. At least one editable fit part must
improve. Held-out actual views must not regress. Without actual held-out views,
the result explicitly says source-view-only and hidden geometry unvalidated.
When all fit views are reference artwork, it instead says
`reference-artwork-only; hidden geometry unvalidated`. Artwork matching can
improve the intended design while independent photographic validation remains
unavailable. Relabeling a generated backview as primary reference artwork would
change the pinned ObservationSet and is not an automatic upgrade of evidence.

These modules validate attributed observations and local correction mathematics.
They do not prove source authenticity, watertightness, absence of intersections,
physical material recovery, correct hidden shape or end-to-end image-to-3D
completion. A dense reconstruction provider and scene adapter remain separate.
