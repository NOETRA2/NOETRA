# Third-party notices

NOETRA is MIT licensed. It is not affiliated with or endorsed by REA, Microsoft,
Anthropic, OpenAI, Cursor or the maintainers of its dependencies.

Pinned direct runtime dependencies:

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| @modelcontextprotocol/client | 2.4.0 | Apache-2.0 | Official MCP client |
| @modelcontextprotocol/server | 2.4.0 | Apache-2.0 | Official MCP server |
| zod | 4.6.7 | MIT | Runtime schemas |
| z3-solver | 5.3.1 | MIT | Z3 TypeScript bindings and WASM |

REA (`rea-agents` 6.7.0, MIT, https://github.com/morluto/rea) is a separately
versioned, optional integration. Its source is not copied into NOETRA, its
package is not a default dependency, and enabling it does not change any
pre-existing REA client registration. Underlying optional analysis providers may
have separate licenses and platform requirements.

The alpha.3 reconstruction proof can use independently installed Python, NumPy,
SciPy, OpenCV, Pillow and Blender; optional psutil provides process diagnostics.
Their binaries and model weights are NOT bundled or installed automatically by
NOETRA. Consult those installations' upstream licenses. Public OpenCV calibration
photographs are fetched only by an explicit benchmark downloader, kept outside
the core package with the upstream LICENSE and source/hash manifest. Generated
proof meshes are not shipped as core example assets. No VGGT, MapAnything,
COLMAP, Open3D or Mitsuba provider package/checkpoint is bundled.

The separately configured photo environment now uses locally installed PyTorch,
Torchvision, TripoSR, U2Net/rembg, PyCOLMAP, Open3D, Trimesh, scikit-image and
Mitsuba, with their independent dependencies and upstream license texts. The
official TripoSR repository states MIT for code and pretrained models. Its
reviewed source commit, checkpoint revision, hashes and local CPU extractor patch
are recorded in the accompanying workspace proof. These source/model/provider
binaries are not copied into the core npm archive. Ghidra 12.1.4 and JDK 21 are
also separately installed/reused local tools, not core bundled components.

Development uses TypeScript 7.0.2 (Apache-2.0), Vitest 5.0.5 (MIT) and @types/node
26.6.5 (MIT). Node.js includes SQLite; their upstream licenses apply. Dependency
license texts remain in the installed npm packages. The package lock records
direct/transitive versions and integrity information. Review the full dependency
tree and licenses again before a public release.

Official references consulted:

The optional local texturing runtime uses xatlas 0.0.11 (MIT, Python bindings
for the xatlas mesh-parameterization library), OpenCV, NumPy and SciPy under
their upstream licences. xatlas source and bindings are external dependencies;
they are not copied into the core npm package. The fixed runtime adapters record
the actual xatlas package version, original mesh hashes and UV correspondence.
See https://github.com/jpcy/xatlas and the installed distribution's licence text.
The generated lion material is an authored colour/roughness/normal design, not
an Adobe Substance asset or a Hunyuan texture-model output. Substance Painter
and Hunyuan Paint are not installed or bundled by this integration.

- https://ts.sdk.modelcontextprotocol.io/v2/
- https://github.com/Z3Prover/z3/tree/master/src/api/js
- https://nodejs.org/docs/latest-v24.x/api/sqlite.html
- https://zod.dev/
- https://vitest.dev/guide/
- https://github.com/morluto/rea
- https://learn.chatgpt.com/docs/extend/mcp
