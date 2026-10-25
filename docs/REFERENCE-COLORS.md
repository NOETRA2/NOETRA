# Reference colours on an existing reconstruction

For an authored coat without projecting photographic lighting, use the separate
[surface painting operation](SURFACE-PAINT.md). It builds real xatlas UVs and
separate PBR maps while preserving the mesh. Neither operation guarantees an
exact photographic material reconstruction.

`noetra.colorize_reconstruction` preserves an existing reconstruction's mesh and
creates an immutable colour version. Input is a run ID, attributed images,
explicit proposed camera directions/up vectors, weights, an sRGB fallback colour
and provenance. It accepts no executable code or caller-granted permissions.
Trusted local Blender execution must already be enabled.

The tool preserves and hashes source images and the parent GLB. It estimates
orthographic image alignment from the image foreground and model bounds, checks
surface orientation and ray visibility, and transfers linearized reference
radiance into vertex colours. Unsupported samples use the declared fallback.
A matte, non-metallic material reads those colours. The default GLB includes
`COLOR_0`; the Blender file retains the colour attribute and material nodes.
No generated reference image is substituted for a mesh render.

For a coherent source, set `mappingMode: "primary-view"` with exactly one global view.
Optional attributed `controlPoints: [{modelPixel:[x,y],referencePixel:[x,y]}]`
correct the 2D sampling coordinates with a thin-plate warp. Coordinates refer to
the full-resolution approximate orthographic registration, not screen pixels in
an unrelated camera. The controls change texture sampling only; image corners
remain pinned. Ray visibility anchors samples, including grazing visible faces.
Optional extra views must each declare an attributed, feathered ellipsoid
`region: {center, radii, feather, provenance}`. They act as bounded colour-paint
corrections only, preserving the primary mapping outside their surface region.
This allows a specifically aligned face patch without blending unrelated full
body poses. Region boundaries and controls are authored assumptions and need
visual review; they do not move the mesh.

Unknown colours propagate through indexed mesh-edge adjacency using a positive
Laplacian. Observed samples stay exactly fixed; solver residuals and convergence
are reported. Disconnected surfaces cannot exchange colours merely because they
are nearby. Failed solves fall back to graph-nearest seeds; entirely unobserved
components use the declared fallback. An optional attributed `symmetryPlane`
can supply explicitly inferred mirrored appearance anchors with distance and
normal checks. These are hypotheses about unseen colour, not new observations.

Set `textureResolution` (512–2048) to create a UV atlas and bake the surface
colours with emission, excluding scene lighting. The texture is packed in BLEND
and embedded as a base-colour image in GLB. Vertex colour attributes are removed
from the baked export to avoid GLB multiplying colour twice. UV unwrap spacing
is small enough to keep tiny fur islands from collapsing into black speckles.
Reimporting the GLB must retain its UVs and texture; view renders remain actual
geometry renders. UV seams may duplicate export vertices without changing any
triangle's geometric surface.

Geometry hashes before and after must match exactly. The output has new BLEND,
GLB and eight actual renders; the source run remains unchanged. Saved-run
inspection rechecks the parent model and images. Inputs are limited to twelve
views, 24 million total pixels and a 128 MiB GLB. The numerical alignment and
foreground tests are separate from the actual Blender/GLB round-trip proof.

This is approximate appearance transfer. Directions are supplied assumptions,
not recovered camera calibration. Differing source poses and silhouettes can
cause colour spill, patchiness or misplaced details. Observed image lighting is
not separated into intrinsic albedo or roughness, and vertex density limits fine
texture detail. Hidden appearance and the fallback are not measured. Geometry,
face/fur detail and mesh imperfections remain unchanged.
