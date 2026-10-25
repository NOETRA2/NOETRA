# Local surface painting

`noetra.paint_surface_material` is a reusable, data-only material operation. It
connects a configured Blender runtime to real xatlas UV parameterization in the
configured vision Python, then bakes portable PBR maps. It does not generate or
repair geometry. The selected local runtime must already contain xatlas 0.0.11
and the dependencies in `requirements-texturing.txt`; the operation installs
nothing and makes no network requests.

Blender execution must be enabled in trusted reconstruction configuration, with
absolute `blenderExecutable` and `vision.pythonExecutable` paths. Payloads cannot
grant execution permission, select another executable or submit Python code.
The original model is hash-checked and copied into a new immutable run. Failed
runs remain separate; the approved source is never overwritten.

## Input and output

Pass a project-local reconstruction `runId`, optional reference image paths, and
`design`. The design contains `baseSRGB`, `baseRoughness`, 1024 or 2048 resolution,
and 1–32 ordered paint layers. Each layer declares an ID, ellipsoidal world-space
region (`shape`: ellipsoid or box, `center`, `radii`, `feather`, `provenance`), sRGB colour, roughness,
opacity, fibre direction and provenance. An optional axis gradient blends to a
second colour. Masks and gradients are authored choices; reference images are
preserved as evidence and do not automatically determine those choices.

The current operation accepts one triangular mesh, bounded to 200,000 vertices
and 400,000 faces. Multiple objects and non-triangular input fail rather than
silently replacing materials or triangulating geometry. All original positions
and triangle indices are preserved. Per-corner xatlas UVs are restored to the
original face/corner order; UV seam vertices do not replace the Blender mesh.
The UV set is replaced together with the material so old render UVs cannot
silently redirect baking or export.

Outputs include a packed BLEND, an embedded-texture GLB, eight framed renders,
2048/1024 PNG base colour, roughness and tangent normal maps, design and geometry
hashes, atlas correspondence checks and source provenance. Base colour is sRGB;
roughness and normals are Non-Color. Blender/OCIO handles scene-linear shading
with an AgX presentation. Lighting is not baked into the authored albedo.

## Honest limits

`noetra.refine_base_surface` additionally accepts 1–16 bounded deformation masks
with a total displacement limit of 0.025 scene units. It edits only the original
vertices inside those masks, backtracks changes that reverse triangle normals,
and verifies unchanged topology and exact protected vertices. It creates no
extra mesh objects or facial overlay geometry. Anatomy is still an authored
approximation; a displacement check does not establish likeness.

The rejected photographic face-projection experiment is not exposed by this
operation. `referenceSurface` is rejected by the strict schema. A photograph on
a coarse mesh does not establish correctly modelled eyes, a nose or a mouth.

Fine fur is a mild procedural shading pattern baked to maps, not new strands or
reconstructed fur geometry. Palette, eye placement and part masks require
authored landmarks. Automatic semantic material recovery, photographic matching,
seam-aware image painting and intrinsic roughness recovery remain unfinished.

xatlas can leave tiny faces unparameterized. A tightly bounded allowance (at most
2% of faces and 0.2% of surface area) assigns those faces positive UV triangles in
a reserved strip and a declared base-coat prior; face IDs and measured area are
reported. Larger omissions fail. No geometry is deleted, and these faces are not
claimed as successful native charts.

Substance Painter and Hunyuan Paint are not part of this connection. No commercial
licence or large GPU texture model is implicitly required or installed.
