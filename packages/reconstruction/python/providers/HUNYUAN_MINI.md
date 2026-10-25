# Local Hunyuan3D-2mini Turbo provider

This opt-in adapter executes the actual upstream Hunyuan3D shape pipeline. It
produces an untextured triangle mesh from one foreground RGBA image. It never
downloads dependencies, source, weights, DINO models or background models during
inference. It does not imply exact hidden geometry, measured scale, semantic
parts, multi-view fusion, textures, or PBR materials.

## Provisioning contract

Use an isolated environment; keep the existing TripoSR/vision environment intact.
The source is pinned to official commit
`f8db63096c8282cb27354314d896feba5ba6ff8a` of
[Tencent-Hunyuan/Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/tree/f8db63096c8282cb27354314d896feba5ba6ff8a).
Required source files are `hy3dgen/__init__.py`, all `.py` files under
`hy3dgen/shapegen/`, and the source `LICENSE` and `NOTICE`. Their exact sizes and
Git blob hashes are in
`../../provider-manifests/hunyuan3d-2mini-turbo.json`. Binary remesh utilities,
texture dependencies, a CUDA compiler, and custom rasterizers are not used.

Model assets come from the public, ungated
[official model repository](https://huggingface.co/tencent/Hunyuan3D-2mini/tree/f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6)
at revision `f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6`:

| Relative file inside assetDirectory | Bytes | Verification |
| --- | ---: | --- |
| `hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors` | 3,822,584,202 | SHA256 `bdbcef30dd0149a281e17d5b5b1fdad1122c904e098a42f3100e04e03c247bc4` |
| `hunyuan3d-dit-v2-mini-turbo/config.yaml` | 1,664 | Git blob SHA1 `70a77756aaa5429626f4106e2cd882ca494221ab` |
| `LICENSE` | 17,828 | Git blob SHA1 `58e0779d576cb14caed1d443cf4d5785c2497fe1` |
| `NOTICE` | 32,064 | Git blob SHA1 `0e623667e16ed2034540ca9ace4ebc8b33865baf` |

The combined safetensors file includes the DiT, VAE decoder and DINOv2-Giant
conditioner. A separate DINO checkpoint is unnecessary. The config contains the
DINO architecture rather than requiring a hub fetch. The additional standalone
VAE-Turbo checkpoint is unnecessary for this baseline; FlashVDM is not enabled.
Do not replace safetensors with a pickle checkpoint.

The official requirements are mostly unpinned. A concrete isolated starting
environment for testing is Python 3.12, PyTorch 2.6.0 with CUDA 12.4,
torchvision 0.21.0 from the matching PyTorch index, transformers 4.46.3,
diffusers 0.32.2, safetensors >=0.4.3, PyYAML 6, einops >=0.8, NumPy <3,
Pillow, tqdm, SciPy, scikit-image, opencv-python-headless, trimesh and pymeshlab.
This is an adapter testing baseline, not an official upstream lockfile or a claim
that these packages have been installed or inference has passed. `pymeshlab` is
needed because the official shape package eagerly imports postprocessors even
though this adapter does not invoke their mesh simplifier. `accelerate`, `diso`,
`torch_cluster`, `rembg`, and texture packages are not required by this inference
path. Test actual imports in the isolated environment.

The [Tencent community license](https://huggingface.co/tencent/Hunyuan3D-2mini/blob/f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6/LICENSE)
has territorial exclusions (EU, UK, South Korea), acceptable-use, distribution and
deployment-scale terms. Source files and dependencies can carry their own notices.
Provisioning and deploying must retain these; this adapter does not accept gated
terms or represent that Tencent endorses NOETRA. The shipped manifest is an
identity/attribution record, not a new model license.

## Calling contract

```python
from pathlib import Path
from PIL import Image
from providers.hunyuan_mini import generate_geometry, preflight

options = {
    "sourceDirectory": str(Path(".tools/Hunyuan3D-2").resolve()),
    "assetDirectory": str(Path(".tools/models/Hunyuan3D-2mini").resolve()),
    "pythonExecutable": str(Path(".tools/shape-env/Scripts/python.exe").resolve()),
    "device": "cuda",
    "steps": 8,
    "seed": 12345,
    "timeoutSeconds": 900,
    "numChunks": 2048,
    "cpuThreads": 4,
    "experimentalLowRam": False,
}
resources = preflight(options)  # Uses the selected interpreter's actual CUDA.
output = Path("existing-empty-absolute-run-directory").resolve()
with Image.open("foreground-with-alpha.png") as image:
    mesh, provenance = generate_geometry(image.copy(), options, output, resolution=256)
```

`output` must already exist and contain no previous provider request/result. It
may contain earlier pipeline evidence. Input RGBA must have a meaningful alpha
channel. Preserve a full-resolution foreground image; do not pass TripoSR's gray
RGB composite because the Hunyuan processor handles its own recentering and white
background. The caller owns foreground-mask provenance and image scope checking.
Source image and mask processing must stay local.

The fixed child process writes `provider-conditioning.png`, `provider-request.json`,
`provider-runtime.log`, `inference-progress.json` and `provider-result.json`.
Successful execution also writes `learned-mesh.glb` and `learned-mesh.ply`, with
model/source identity, seed, grid, steps, actual resources, peak allocated CUDA
bytes, stage order and explicit geometry/appearance limitations in provenance.
Failure returns a typed error and records the actual exception. There is no
placeholder mesh or silent fallback. A wall-clock timeout kills the process so
CUDA state is released even if native code stops responding.

The API returns `(trimesh.Trimesh, provenance)` for integration with subsequent
NOETRA appearance and validation stages. Keep the original scale/orientation for
evaluation before downstream alignment. Existing TripoSR-specific field color
sampling cannot be applied to a Hunyuan mesh: it has no TripoSR scene code.
Use the independent appearance pipeline if source-photo color projection is
desired and identify that projection explicitly.

## Memory behavior and laptop limits

The official family README documents approximately 6 GB VRAM for shape generation;
it does not promise that the 2mini path fits a 4 GB card. The smaller 0.6B DiT
does not make the complete checkpoint 0.6B: the DINO conditioner is substantial.
The adapter avoids the upstream loader's float32 model allocation by constructing
on the meta device and assigning verified mapped FP16 tensors directly. It drops
the unused training encoder, rebuilds only the deterministic Fourier buffers,
requests DINO SDPA, and puts only one of conditioner, DiT and VAE on CUDA at a
time. Previous stages are discarded to meta, not copied back to host RAM.

CUDA preflight requires an actual CUDA-enabled PyTorch interpreter, compute
capability >=7, total VRAM >=3.5 GiB, free VRAM >=2.75 GiB, available system RAM
>=1.25 GiB, and free output disk >=512 MiB. These are conservative experimental
admission limits, **not measured peak-memory guarantees**. CPU is an explicit
alternative using float32 per active stage and requires >=6 GiB currently
available RAM; the 7.4 GB laptop will often fail that check while other apps run.
CUDA math attention fallback is disabled to avoid unexpectedly materializing
large quadratic attention matrices. Unsupported kernels fail clearly.

An operator can explicitly set trusted `experimentalLowRam: true` for CUDA on
Windows. This changes admission to at least 768 MiB available physical RAM **and**
6 GiB measured available Windows commit headroom. It remains disabled by default
and is rejected for CPU. The policy follows the mapped, staged loading strategy;
commit headroom is not extra physical RAM and does not establish that inference
will fit. A real out-of-memory error still fails; there is no silent fallback.
Resource snapshots and provenance identify the experimental policy and exact
thresholds. Two initial laptop attempts with about 0.97 GiB available physical
RAM failed the default guard before loading weights; the second measured about
20.3 GiB available commit. Those measurements motivated this explicit experiment,
not a claim that the full model has succeeded.

The subsequent **actual public SDK lion test succeeded** on 2026-10-24 with this
explicit policy: RTX 3050 Laptop GPU, PyTorch 2.6.0+cu124, 192 grid, 8 sampling
steps, 1024 query chunks and seed 12345. Shape execution took 86.985 seconds and
reported 2,571,237,376 peak allocated CUDA bytes (about 2.39 GiB). It produced
81,326 vertices and 162,196 triangles; the downstream SDK reported a watertight,
winding-consistent mesh and completed eight real Blender inspection renders.
End-to-end SDK time was 177.532 seconds. The run used only the primary lion image,
not generated extra viewpoints. Clay renders show recognizable body, legs, mane
and tail, with coarse face/mane details; they do not establish accurate hidden
shape or recovered appearance. This single tested configuration does not certify
arbitrary inputs or higher resolution. Evidence run ID:
`1fce6a45-1f52-4731-923d-8d420dac729e` under the local lion project.

Steps, extraction resolution, query chunk count, thread count and wall time are
bounded. The adapter does not quantize weights or reduce the trained DINO input
resolution. Those would be separate quality/performance experiments. Higher
extraction resolution does not prove more accurate unseen geometry.

## Verification

```powershell
.tools/vision-env/Scripts/python.exe -m unittest discover -s packages/reconstruction/python/providers -p 'test_*.py' -v
```

The targeted tests cover upstream identity, asset corruption/missing assets, path
escape, settings limits, actual-device preflight rejection, memory checks,
timeout cleanup, network denial and numerical correctness of the meta-assignment
loader using a tiny local safetensors fixture. These do not establish real-model
quality or GPU fit. An actual reference run must separately record complete
progress/provenance, peak memory and clay/orbit views before making such claims.

For distribution, copy `providers/*.py` under the Python runtime and copy
`provider-manifests/` beside that runtime's `python/` directory. Keeping the
manifest location consistent preserves validation in both source and dist trees.

## Controlled extraction from the same learned latent

Successful new `generate_geometry` calls retain `shape-latents.safetensors` and
`shape-latents.json`. The cached tensor is the **final sampling
`outputs.prev_sample`, before VAE scaling**, named `latents`, shaped `[1,3072,64]`,
and FP16 or FP32. Its original bytes, SHA256, shape/dtype, seed/step count,
sampling device, provider/source/model identities, scale factor and precise
semantics appear in `provenance['latentCheckpoint']`. Safetensors is used; pickle
is never loaded for the cache. The whole file is limited to 2 MiB.

```python
from providers.hunyuan_mini import extract_geometry

cache = original_provenance['latentCheckpoint']
refined_mesh, refined_provenance = extract_geometry(
    cache['path'], cache['sha256'], options, fresh_output_directory,
    resolution=256,
)
```

The caller must scope the checkpoint to its project and obtain the expected hash
from its trusted original run. The provider checks the supplied SHA256, bounded
file/header/tensor shape, dtype, finite values and embedded model/scale/semantics
metadata. It rejects linked paths and copies verified bytes to the fresh output
as `shape-latents-input.safetensors` before launching its fixed child. Source and
all model assets, including the full model weight hash, are verified again.

Extraction instantiates and loads **only the pinned embedded VAE**. It executes no
image conditioner or DiT sampling and creates no new random noise. It calls the
unmodified upstream `_export` method with the cached unscaled latent, so the VAE
scale factor is applied exactly once. The original cached bytes are also retained
as the output's `shape-latents.safetensors`, with the same hash, allowing chained
comparisons without repeated scaling or resampling. `shape-latents.json` is a
readable record; trusted integrity comes from the expected checkpoint SHA256 and
the caller's original run provenance, not from treating arbitrary metadata as a
signature.

The same offline, interpreter/device/RAM/commit/VRAM/disk and wall-time guards
apply. Extraction provenance reports `operation='extract'`, `resampled=False`,
`stageOrder=['vae']`, `conditioningExecuted=False`, `samplingExecuted=False`,
`inputLatentSha256`, `latentScaleApplications=1`, and the original sampling seed
and step count. Resolution changes are denser sampling of the same learned field,
not proof that facial anatomy or fur improved. Keep decoder precision/device,
Marching Cubes level, cameras and comparison lighting fixed.

Runs created before latent caching was added have no recoverable latent checkpoint;
their mesh alone cannot be re-extracted exactly. Do not invent one. The targeted
tests exercise real bounded safetensors round trips, tampering/model/scale
rejection, unchanged cache bytes, VAE-only invocation and the actual pinned
upstream export's single scale division with a tiny recording VAE. Full-model
refinement must still be validated through the public SDK on the intended image.
