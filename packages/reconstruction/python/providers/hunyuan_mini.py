"""Pinned Hunyuan3D-2mini Turbo inference, isolated from NOETRA's CPU environment.

The public functions never download assets. A separate, explicitly provisioned
Python interpreter may be selected. All model execution happens in a disposable
child process with a wall-clock deadline and networking disabled.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

PROVIDER = "hunyuan3d-2mini-turbo"
MANIFEST = Path(__file__).resolve().parents[2] / "provider-manifests" / (PROVIDER + ".json")
GIB = 1024 ** 3
TARGETS = {
    "model": "hy3dgen.shapegen.models.Hunyuan3DDiT",
    "vae": "hy3dgen.shapegen.models.ShapeVAE",
    "conditioner": "hy3dgen.shapegen.models.SingleImageEncoder",
    "scheduler": "hy3dgen.shapegen.schedulers.ConsistencyFlowMatchEulerDiscreteScheduler",
    "image_processor": "hy3dgen.shapegen.preprocessors.ImageProcessorV2",
    "pipeline": "hy3dgen.shapegen.pipelines.Hunyuan3DDiTFlowMatchingPipeline",
}
LATENT_SHAPE = (1, 3072, 64)
LATENT_MAX_BYTES = 2 * 1024 * 1024
LATENT_SEMANTICS = "final-sampling-output-before-vae-scale"
VAE_SCALE = 1.0188137142395404


class ProviderError(RuntimeError):
    def __init__(self, code, message, **details):
        super().__init__(code + ": " + message)
        self.code, self.details = code, details


def check(condition, code, message, **details):
    if not condition:
        raise ProviderError(code, message, **details)


def _json(path):
    path = Path(path)
    check(path.is_file() and path.stat().st_size < 1024 * 1024,
          "RECONSTRUCTION_PROVIDER_JSON", "Provider JSON is missing or oversized", path=str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _root(path, name):
    path = Path(path)
    check(path.is_absolute() and path.is_dir(), "RECONSTRUCTION_PROVIDER_PATH",
          name + " must be an existing absolute directory")
    resolved = path.resolve()
    # Refuse junctions/symlinks in supplied directory chains as well as asset files.
    for current in [path, *path.parents]:
        check(not current.is_symlink() and not (hasattr(current, "is_junction") and current.is_junction()),
              "RECONSTRUCTION_PROVIDER_SYMLINK", "Provider paths cannot traverse symlinks/junctions")
    return resolved


def _inside(root, relative):
    path = root / relative
    check(path.resolve().is_relative_to(root), "RECONSTRUCTION_PROVIDER_PATH", "Asset path escapes its root")
    for current in [path, *path.parents]:
        if current == root:
            break
        check(not current.is_symlink() and not (hasattr(current, "is_junction") and current.is_junction()),
              "RECONSTRUCTION_PROVIDER_SYMLINK", "Provider asset cannot traverse a link")
    return path


def _verify_file(root, record, full=True):
    path = _inside(root, record["path"])
    check(path.is_file(), "RECONSTRUCTION_PROVIDER_ASSET_MISSING", "Provision the pinned provider asset explicitly",
          path=str(path))
    check(path.stat().st_size == record["bytes"], "RECONSTRUCTION_PROVIDER_ASSET_SIZE",
          "Provider asset differs from its pinned size", path=str(path))
    if full:
        if "sha256" in record:
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            expected = record["sha256"]
        else:
            data = path.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
            expected = record["gitBlobSha1"]
        check(actual == expected, "RECONSTRUCTION_PROVIDER_ASSET_CHANGED",
              "Provider file differs from the verified upstream revision", path=str(path))
    return path


def validate_assets(options, *, verify_weights=True):
    """Verify exact source/config/license bytes, and the checkpoint by default."""
    manifest = _json(MANIFEST)
    check(manifest["provider"] == PROVIDER and manifest["schemaVersion"] == 1,
          "RECONSTRUCTION_PROVIDER_MANIFEST", "Unexpected provider manifest")
    source = _root(options["sourceDirectory"], "sourceDirectory")
    assets = _root(options["assetDirectory"], "assetDirectory")
    for record in manifest["source"]["files"]:
        _verify_file(source, record)
    expected_python = {r["path"] for r in manifest["source"]["files"] if r["path"].endswith(".py")}
    actual_python = {str(p.relative_to(source)).replace("\\", "/") for p in (source / "hy3dgen" / "shapegen").rglob("*.py")}
    actual_python.add("hy3dgen/__init__.py")
    check(actual_python == expected_python, "RECONSTRUCTION_PROVIDER_SOURCE_EXTRA",
          "The shape source contains missing or additional Python files")
    files = {}
    for record in manifest["model"]["files"]:
        full = verify_weights or "sha256" not in record
        files[record["path"]] = str(_verify_file(assets, record, full=full))
    return manifest, source, files


def normalize_options(options, resolution=256):
    """Reject ambiguous/unbounded settings before loading any model or library."""
    check(isinstance(options, dict), "RECONSTRUCTION_PROVIDER_OPTIONS", "Provider options must be an object")
    allowed = {"sourceDirectory", "assetDirectory", "pythonExecutable", "device", "steps", "seed",
               "timeoutSeconds", "numChunks", "cpuThreads", "experimentalLowRam"}
    check(not set(options) - allowed, "RECONSTRUCTION_PROVIDER_OPTIONS", "Unknown provider option",
          unknown=sorted(set(options) - allowed))
    check(all(k in options for k in ("sourceDirectory", "assetDirectory")),
          "RECONSTRUCTION_PROVIDER_OPTIONS", "Source and asset directories are required")
    normalized = dict(options)
    defaults = {"device": "cuda", "steps": 8, "seed": 12345, "timeoutSeconds": 900,
                "numChunks": 2048, "cpuThreads": 4, "experimentalLowRam": False}
    for key, value in defaults.items():
        normalized.setdefault(key, value)
    check(normalized["device"] in ("cuda", "cpu"), "RECONSTRUCTION_PROVIDER_DEVICE", "Choose cuda or cpu explicitly")
    check(type(normalized["experimentalLowRam"]) is bool and
          (not normalized["experimentalLowRam"] or normalized["device"] == "cuda"),
          "RECONSTRUCTION_PROVIDER_LOW_RAM_POLICY", "Experimental low-RAM admission is an explicit CUDA-only option")
    for key, lower, upper in [("steps", 1, 30), ("seed", 0, 2147483647), ("timeoutSeconds", 30, 1800),
                              ("numChunks", 256, 8192), ("cpuThreads", 1, 4)]:
        value = normalized[key]
        check(type(value) is int and lower <= value <= upper,
              "RECONSTRUCTION_PROVIDER_LIMIT", key + " is outside its bounded range")
    check(type(resolution) is int and 64 <= resolution <= 384,
          "RECONSTRUCTION_PROVIDER_LIMIT", "Grid resolution must be an integer from 64 through 384")
    if "pythonExecutable" in normalized:
        interpreter = Path(normalized["pythonExecutable"])
        check(interpreter.is_absolute() and interpreter.is_file(),
              "RECONSTRUCTION_PROVIDER_INTERPRETER", "Configured Python interpreter does not exist")
    return normalized


def _memory_snapshot():
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ("totalPhys", "availPhys", "totalPage", "availPage", "totalVirtual", "availVirtual", "availExtended")]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        check(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)),
              "RECONSTRUCTION_PROVIDER_MEMORY_PROBE", "Windows memory probe failed")
        return {"availableRamBytes": int(status.availPhys), "totalRamBytes": int(status.totalPhys),
                "availableCommitBytes": int(status.availPage), "commitLimitBytes": int(status.totalPage),
                "memoryProbe": "Windows GlobalMemoryStatusEx; commit is not extra physical RAM"}
    if Path("/proc/meminfo").is_file():
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return {"availableRamBytes": int(line.split()[1]) * 1024, "memoryProbe": "Linux MemAvailable"}
    if hasattr(os, "sysconf"):
        return {"availableRamBytes": int(os.sysconf("SC_AVPHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE")),
                "memoryProbe": "sysconf available physical pages"}
    raise ProviderError("RECONSTRUCTION_PROVIDER_MEMORY_PROBE", "Available RAM could not be measured")


def _available_ram():
    return _memory_snapshot()["availableRamBytes"]


def resource_preflight(torch, options, output, available_ram=None):
    """Probe the selected interpreter's actual CUDA device, never nvidia-smi alone."""
    memory = _memory_snapshot() if available_ram is None else {"availableRamBytes": available_ram}
    available = memory["availableRamBytes"]
    experimental = options.get("experimentalLowRam", False)
    required = 6 * GIB if options["device"] == "cpu" else (.75 if experimental else 1.25) * GIB
    check(available >= required, "RECONSTRUCTION_PROVIDER_RAM", "Insufficient currently available system memory",
          availableBytes=available, requiredBytes=int(required), memory=memory)
    if experimental:
        check(os.name == "nt" and memory.get("availableCommitBytes", 0) >= 6 * GIB,
              "RECONSTRUCTION_PROVIDER_COMMIT", "Experimental low-RAM admission requires at least 6 GiB of measured Windows commit headroom",
              requiredBytes=6 * GIB, memory=memory)
    check(shutil.disk_usage(output).free >= 512 * 1024 * 1024,
          "RECONSTRUCTION_PROVIDER_DISK", "Provider output needs at least 512 MiB of free disk space")
    resources = {**memory, "torchVersion": str(torch.__version__), "device": options["device"],
                 "admissionPolicy": {"experimentalLowRam": experimental, "minimumAvailablePhysicalRamBytes": int(required),
                                     "minimumWindowsCommitHeadroomBytes": 6 * GIB if experimental else None,
                                     "status": "experimental measured-headroom admission; not a guarantee of successful inference or memory fit" if experimental else "default conservative admission"},
                 "fitStatus": "preflight passed; successful inference and visual quality still require measurement"}
    if options["device"] == "cuda":
        check(torch.cuda.is_available(), "RECONSTRUCTION_PROVIDER_CUDA_UNAVAILABLE",
              "The selected Python interpreter has no usable CUDA device; no CPU fallback was selected")
        properties = torch.cuda.get_device_properties(0)
        free, total = torch.cuda.mem_get_info(0)
        check(properties.major >= 7, "RECONSTRUCTION_PROVIDER_GPU_ARCH", "Staged fp16 provider requires a modern NVIDIA GPU")
        check(total >= int(3.5 * GIB) and free >= int(2.75 * GIB),
              "RECONSTRUCTION_PROVIDER_VRAM", "Insufficient CUDA memory for the experimental staged provider",
              availableBytes=free, totalBytes=total, requiredFreeBytes=int(2.75 * GIB))
        resources.update({"gpuName": properties.name, "cudaVersion": str(torch.version.cuda),
                          "availableVramBytes": free, "totalVramBytes": total,
                          "computeCapability": [properties.major, properties.minor]})
    return resources


def _offline_environment():
    return {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "DIFFUSERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HY3DGEN_DEBUG": "0",
            "USE_SAGEATTN": "0", "TOKENIZERS_PARALLELISM": "false"}


def _local_cache_environment(output):
    """Keep all imported library cache metadata inside the current run."""
    output = _root(output, "output")
    cache = output / "provider-runtime-cache"
    check(not cache.is_symlink() and not (hasattr(cache, "is_junction") and cache.is_junction()),
          "RECONSTRUCTION_PROVIDER_SYMLINK", "Provider cache cannot be a link")
    cache.mkdir(exist_ok=True)
    return {"HF_HOME": str(cache / "huggingface"), "HF_HUB_CACHE": str(cache / "huggingface" / "hub"),
            "TRANSFORMERS_CACHE": str(cache / "transformers"), "TORCH_HOME": str(cache / "torch"),
            "XDG_CACHE_HOME": str(cache), "HF_ASSETS_CACHE": str(cache / "huggingface" / "assets")}


def _disable_network():
    def denied(*args, **kwargs):
        raise ProviderError("RECONSTRUCTION_PROVIDER_NETWORK_DISABLED", "Provider inference cannot access the network")
    socket.create_connection = denied
    socket.getaddrinfo = denied
    socket.socket.connect = denied
    socket.socket.connect_ex = denied


def _checkpoint_bytes(path, expected_sha):
    path = Path(path)
    check(isinstance(expected_sha, str) and len(expected_sha) == 64 and all(c in "0123456789abcdef" for c in expected_sha),
          "RECONSTRUCTION_PROVIDER_LATENT_HASH", "A lowercase SHA256 is required for the supplied latent checkpoint")
    check(path.is_absolute() and path.is_file() and path.suffix == ".safetensors",
          "RECONSTRUCTION_PROVIDER_LATENT_PATH", "Supply an existing absolute safetensors checkpoint path")
    for current in [path, *path.parents]:
        check(not current.is_symlink() and not (hasattr(current, "is_junction") and current.is_junction()),
              "RECONSTRUCTION_PROVIDER_SYMLINK", "Latent checkpoint cannot traverse a link")
    check(0 < path.stat().st_size <= LATENT_MAX_BYTES, "RECONSTRUCTION_PROVIDER_LATENT_LIMIT", "Latent checkpoint exceeds the bounded size")
    with path.open("rb") as stream:
        data = stream.read(LATENT_MAX_BYTES + 1)
    check(len(data) <= LATENT_MAX_BYTES and hashlib.sha256(data).hexdigest() == expected_sha,
          "RECONSTRUCTION_PROVIDER_LATENT_CHANGED", "Latent checkpoint differs from the expected SHA256")
    return data


def _latent_identity(manifest):
    return {"schemaVersion": "1", "provider": PROVIDER, "sourceCommit": manifest["source"]["commit"],
            "modelRevision": manifest["model"]["revision"], "weightsSha256": manifest["model"]["files"][0]["sha256"],
            "semantics": LATENT_SEMANTICS, "vaeScaleFactor": repr(VAE_SCALE)}


def _validate_latent_tensor(torch, tensor):
    check(tuple(tensor.shape) == LATENT_SHAPE and tensor.dtype in (torch.float16, torch.float32),
          "RECONSTRUCTION_PROVIDER_LATENT_TENSOR", "Cached latent must be [1,3072,64] FP16 or FP32")
    check(bool(torch.isfinite(tensor).all()), "RECONSTRUCTION_PROVIDER_LATENT_NONFINITE", "Cached latent contains nonfinite values")


def _save_latents(torch, tensor, output, manifest, options):
    from safetensors.torch import save_file
    _validate_latent_tensor(torch, tensor)
    path = Path(output) / "shape-latents.safetensors"
    check(not path.exists(), "RECONSTRUCTION_PROVIDER_OUTPUT_EXISTS", "Latent output already exists")
    metadata = {**_latent_identity(manifest), "seed": str(options["seed"]), "steps": str(options["steps"]),
                "samplingDevice": options["device"], "guidanceScale": "5.0"}
    save_file({"latents": tensor.detach().to(device="cpu").contiguous()}, str(path), metadata=metadata)
    data = path.read_bytes()
    check(len(data) <= LATENT_MAX_BYTES, "RECONSTRUCTION_PROVIDER_LATENT_LIMIT", "Generated latent cache exceeds its size limit")
    record = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
              "shape": list(tensor.shape), "dtype": str(tensor.dtype), **metadata}
    _write(Path(output) / "shape-latents.json", record)
    return record


def _load_latents(torch, path, expected_sha, manifest):
    from safetensors import safe_open
    _checkpoint_bytes(path, expected_sha)
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        metadata = handle.metadata() or {}
        check(all(metadata.get(key) == value for key, value in _latent_identity(manifest).items()),
              "RECONSTRUCTION_PROVIDER_LATENT_IDENTITY", "Cached latent has a different provider, model, scale, or tensor semantics")
        check(list(handle.keys()) == ["latents"], "RECONSTRUCTION_PROVIDER_LATENT_TENSOR", "Checkpoint must contain only the named latent tensor")
        entry = handle.get_slice("latents")
        check(tuple(entry.get_shape()) == LATENT_SHAPE and entry.get_dtype() in ("F16", "F32"),
              "RECONSTRUCTION_PROVIDER_LATENT_TENSOR", "Cached latent header must be [1,3072,64] FP16 or FP32")
        tensor = handle.get_tensor("latents")
        _validate_latent_tensor(torch, tensor)
    check(metadata.get("samplingDevice") in ("cuda", "cpu") and metadata.get("guidanceScale") == "5.0",
          "RECONSTRUCTION_PROVIDER_LATENT_IDENTITY", "Cached sampling metadata is invalid")
    for key, lower, upper in (("steps", 1, 30), ("seed", 0, 2147483647)):
        value = metadata.get(key, "")
        check(value.isdigit() and lower <= int(value) <= upper,
              "RECONSTRUCTION_PROVIDER_LATENT_IDENTITY", "Cached sampling metadata is invalid")
    return tensor, {"path": str(path), "sha256": expected_sha, "bytes": Path(path).stat().st_size,
                    "shape": list(tensor.shape), "dtype": str(tensor.dtype), **metadata}


def _run_child(options, output, operation, resolution=256, image=None, checkpoint=None, expected_sha=None):
    options = normalize_options(options, resolution)
    output = _root(output, "output")
    request_path = output / "provider-request.json"
    result_path = output / "provider-result.json"
    check(not request_path.exists() and not result_path.exists(), "RECONSTRUCTION_PROVIDER_OUTPUT_EXISTS",
          "Use a fresh provider output directory to avoid stale results")
    check(not any((output / name).exists() for name in ("learned-mesh.glb", "learned-mesh.ply", "provider-conditioning.png", "shape-latents.safetensors", "shape-latents-input.safetensors")),
          "RECONSTRUCTION_PROVIDER_OUTPUT_EXISTS", "Provider outputs already exist; preserve them in their original run")
    request = {"operation": operation, "options": options, "resolution": resolution, "output": str(output)}
    if operation == "extract":
        data = _checkpoint_bytes(checkpoint, expected_sha)
        copied = output / "shape-latents-input.safetensors"
        copied.write_bytes(data)
        _checkpoint_bytes(copied, expected_sha)
        request.update({"checkpoint": str(copied), "expectedSha256": expected_sha})
    if image is not None:
        check(image.mode == "RGBA" and image.width * image.height <= 24_000_000 and max(image.size) <= 8192,
              "RECONSTRUCTION_PROVIDER_IMAGE", "Pass one foreground RGBA image, at most 24 megapixels and 8192 pixels per side")
        alpha = image.getextrema()[3]
        check(alpha[0] < 255 and alpha[1] > 0, "RECONSTRUCTION_PROVIDER_FOREGROUND",
              "Hunyuan requires a foreground alpha mask; no background service or download will be invoked")
        image.save(output / "provider-conditioning.png")
        request["image"] = str(output / "provider-conditioning.png")
    _write(request_path, request)
    env = dict(os.environ)
    env.update(_offline_environment())
    env.update(_local_cache_environment(output))
    env.update({"OMP_NUM_THREADS": str(options["cpuThreads"]), "MKL_NUM_THREADS": str(options["cpuThreads"])})
    interpreter = options.get("pythonExecutable", sys.executable)
    command = [interpreter, "-I", str(Path(__file__).resolve()), "--child", str(request_path)]
    with (output / "provider-runtime.log").open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   cwd=str(output), env=env, shell=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            process.wait(timeout=options["timeoutSeconds"])
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=30)
            error = {"ok": False, "provider": PROVIDER, "code": "RECONSTRUCTION_PROVIDER_TIMEOUT",
                     "message": "Provider process exceeded the configured wall-clock deadline"}
            _write(result_path, error)
            _write(output / "inference-progress.json", {"stage": "failed", "provider": PROVIDER, "error": error})
            raise ProviderError(error["code"], error["message"], timeoutSeconds=options["timeoutSeconds"])
    check(result_path.is_file(), "RECONSTRUCTION_PROVIDER_PROCESS_FAILED", "Provider process exited without a result",
          exitCode=process.returncode, log=str(output / "provider-runtime.log"))
    result = _json(result_path)
    check(result.get("ok") is True and process.returncode == 0,
          result.get("code", "RECONSTRUCTION_PROVIDER_PROCESS_FAILED"), result.get("message", "Provider process failed"),
          providerDetails=result.get("details"), exitCode=process.returncode, log=str(output / "provider-runtime.log"))
    return result


def preflight(options, output=None):
    """Check pinned assets and real interpreter/device resources without inference."""
    if output is not None:
        return _run_child(options, output, "preflight")["resources"]
    with tempfile.TemporaryDirectory(prefix="noetra-shape-preflight-") as temporary:
        return _run_child(options, Path(temporary), "preflight")["resources"]


def generate_geometry(image, options, output, resolution=256):
    """Return (actual trimesh.Trimesh, attributed provenance), or an actual failure.

    `image` must retain a foreground alpha channel. Geometry is untextured and has
    arbitrary scale; the existing appearance pipeline can operate on it later.
    """
    result = _run_child(options, output, "generate", resolution, image)
    import trimesh
    mesh = trimesh.load(Path(output) / "learned-mesh.ply", force="mesh", process=False)
    _validate_mesh(mesh)
    return mesh, result["provenance"]


def extract_geometry(checkpoint_path, expected_sha, options, output, resolution=256):
    """Re-extract the same sampled latent with the pinned VAE; no conditioning or resampling."""
    result = _run_child(options, output, "extract", resolution, checkpoint=checkpoint_path, expected_sha=expected_sha)
    import trimesh
    mesh = trimesh.load(Path(output) / "learned-mesh.ply", force="mesh", process=False)
    _validate_mesh(mesh)
    return mesh, result["provenance"]


def _validate_mesh(mesh):
    import numpy as np
    check(hasattr(mesh, "vertices") and hasattr(mesh, "faces"), "RECONSTRUCTION_PROVIDER_EMPTY_MESH", "Model returned no triangle mesh")
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    check(vertices.ndim == 2 and vertices.shape[1] == 3 and 4 <= len(vertices) <= 2_000_000 and
          faces.ndim == 2 and faces.shape[1] == 3 and 4 <= len(faces) <= 4_000_000,
          "RECONSTRUCTION_PROVIDER_MESH_LIMIT", "Model mesh is empty, malformed, or exceeds the output limit")
    check(np.isfinite(vertices).all() and np.issubdtype(faces.dtype, np.integer) and faces.min() >= 0 and faces.max() < len(vertices),
          "RECONSTRUCTION_PROVIDER_INVALID_MESH", "Model mesh contains invalid coordinates or indices")
    check(np.max(np.ptp(vertices, axis=0)) > 1e-8, "RECONSTRUCTION_PROVIDER_EMPTY_MESH", "Model mesh has zero extent")


def _load_component(torch, instantiate, config, name, checkpoint):
    """Allocate no float32 weight copy; mapped safetensors directly replace meta parameters."""
    from safetensors import safe_open
    with torch.device("meta"):
        component = instantiate(config[name])
    if name == "conditioner":
        check(any(module.__class__.__name__ == "Dinov2SdpaSelfAttention" for module in component.modules()),
              "RECONSTRUCTION_PROVIDER_SDPA_UNAVAILABLE",
              "The installed Transformers DINO implementation must support and select SDPA (tested API: 4.46.3)")
    if name == "vae":
        # The official generation checkpoint omits its training-only encoder.
        # Never random-initialize or transfer an unused encoder to the device.
        component.encoder = None
        component.pre_kl = None
    prefix = name + "."
    with safe_open(checkpoint, framework="pt", device="cpu") as handle:
        state = {key[len(prefix):]: handle.get_tensor(key) for key in handle.keys() if key.startswith(prefix)}
        check(bool(state), "RECONSTRUCTION_PROVIDER_CHECKPOINT_KEYS", "Checkpoint component is missing", component=name)
        if name == "vae":
            state = {key: value for key, value in state.items() if not key.startswith(("encoder.", "pre_kl."))}
        component.load_state_dict(state, strict=True, assign=True)
    # Fourier frequencies are deterministic, non-persistent buffers and therefore
    # correctly absent from the checkpoint. Rebuild only this known buffer.
    for module in component.modules():
        if module.__class__.__name__ == "FourierEmbedder":
            frequencies = 2.0 ** torch.arange(module.num_freqs, dtype=torch.float32, device="cpu")
            if config["vae"]["params"].get("include_pi", True):
                frequencies *= torch.pi
            module.frequencies = frequencies
    check(not any(parameter.is_meta for parameter in component.parameters()) and
          not any(buffer.is_meta for buffer in component.buffers()),
          "RECONSTRUCTION_PROVIDER_UNINITIALIZED", "A used model tensor is absent from the pinned checkpoint", component=name)
    return component.eval().requires_grad_(False)


def _source_runtime(source, files):
    import yaml
    # Register only the verified package, instead of exposing arbitrary files at
    # the source checkout root as importable dependency modules.
    check("hy3dgen" not in sys.modules, "RECONSTRUCTION_PROVIDER_SOURCE_ALREADY_LOADED", "Shape source must load in a fresh process")
    sys.dont_write_bytecode = True
    package_spec = importlib.util.spec_from_file_location("hy3dgen", source / "hy3dgen" / "__init__.py",
                                                        submodule_search_locations=[str(source / "hy3dgen")])
    package = importlib.util.module_from_spec(package_spec)
    sys.modules["hy3dgen"] = package
    package_spec.loader.exec_module(package)
    from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline, instantiate_from_config
    from hy3dgen.shapegen.models.autoencoders import SurfaceExtractors

    key = "hunyuan3d-dit-v2-mini-turbo/"
    config = yaml.safe_load(Path(files[key + "config.yaml"]).read_text(encoding="utf-8"))
    check(all(config.get(name, {}).get("target") == target for name, target in TARGETS.items()),
          "RECONSTRUCTION_PROVIDER_CLASS_ALLOWLIST", "The checkpoint config contains unexpected executable classes")
    config = copy.deepcopy(config)
    encoder = config["conditioner"]["params"]["main_image_encoder"]
    check(encoder["type"] == "DinoImageEncoder" and isinstance(encoder["kwargs"].get("config"), dict),
          "RECONSTRUCTION_PROVIDER_LOCAL_ENCODER", "DINO must be configured locally without a hub model identifier")
    # Explicit SDPA prevents the quadratic attention matrix of 5329 DINO patches.
    encoder["kwargs"]["config"]["_attn_implementation"] = "sdpa"
    check(config["vae"]["params"]["scale_factor"] == VAE_SCALE,
          "RECONSTRUCTION_PROVIDER_LATENT_SCALE", "Unexpected pinned VAE scale factor")
    return Hunyuan3DDiTFlowMatchingPipeline, instantiate_from_config, SurfaceExtractors, config


def _infer(torch, source, files, options, resolution, image, progress, output, manifest):
    Hunyuan3DDiTFlowMatchingPipeline, instantiate_from_config, SurfaceExtractors, config = _source_runtime(source, files)
    key = "hunyuan3d-dit-v2-mini-turbo/"
    dtype = torch.float16 if options["device"] == "cuda" else torch.float32
    components = {}
    for name in ("conditioner", "model", "vae"):
        progress("loading pinned " + name + " tensors without float32 copies")
        components[name] = _load_component(torch, instantiate_from_config, config, name, files[key + "model.fp16.safetensors"])
    progress("constructing offline geometry pipeline")
    # Pipeline constructor only moves mapped fp16 tensors to CPU, where they are
    # already located. CUDA components are transferred lazily, one stage at a time.
    pipeline = Hunyuan3DDiTFlowMatchingPipeline(
        **components, scheduler=instantiate_from_config(config["scheduler"]),
        image_processor=instantiate_from_config(config["image_processor"]), device="cpu", dtype=torch.float16)
    pipeline.device = torch.device(options["device"])
    pipeline.dtype = dtype
    pipeline.vae.surface_extractor = SurfaceExtractors["mc"]()
    active = {"name": None}
    stage_order = []

    def activate(name):
        def hook(module, arguments):
            if active["name"] == name:
                return
            previous = active["name"]
            if previous is not None:
                components[previous].to(device="meta")
                gc.collect()
                if options["device"] == "cuda":
                    torch.cuda.empty_cache()
            progress("running " + name, precision=str(dtype), previousStageReleased=previous)
            module.to(device=pipeline.device, dtype=dtype)
            active["name"] = name
            stage_order.append(name)
        return hook

    hooks = [component.register_forward_pre_hook(activate(name)) for name, component in components.items()]
    checkpoint = {}
    try:
        if options["device"] == "cuda":
            torch.cuda.reset_peak_memory_stats()
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            torch.backends.cuda.enable_math_sdp(False)
        generator = torch.Generator(device=pipeline.device).manual_seed(options["seed"])
        def callback(index, timestep, outputs):
            if int(index) + 1 == options["steps"]:
                checkpoint.update(_save_latents(torch, outputs.prev_sample, output, manifest, options))
            progress("sampling learned shape", completedSteps=int(index) + 1, totalSteps=options["steps"])
        with torch.inference_mode():
            meshes = pipeline(image=image, num_inference_steps=options["steps"], guidance_scale=5.0,
                              generator=generator, octree_resolution=resolution, num_chunks=options["numChunks"],
                              mc_algo="mc", output_type="trimesh", enable_pbar=False, callback=callback, callback_steps=1)
        check(len(meshes) == 1 and meshes[0] is not None, "RECONSTRUCTION_PROVIDER_EMPTY_MESH", "Model failed to extract a surface")
        mesh = meshes[0]
        _validate_mesh(mesh)
        peak = torch.cuda.max_memory_allocated() if options["device"] == "cuda" else None
        check(stage_order == ["conditioner", "model", "vae"], "RECONSTRUCTION_PROVIDER_STAGE_ORDER", "Unexpected model stage execution")
        check(bool(checkpoint), "RECONSTRUCTION_PROVIDER_LATENT_MISSING", "Final sampling output was not retained")
        return mesh, {"stageOrder": stage_order, "peakAllocatedVramBytes": peak, "precision": str(dtype),
                      "latentCheckpoint": checkpoint, "operation": "generate", "resampled": True,
                      "loadedComponents": ["conditioner", "model", "vae"], "conditioningExecuted": True,
                      "samplingExecuted": True, "latentScaleApplications": 1, "latentInputSemantics": LATENT_SEMANTICS,
                      "memoryStrategy": "safetensors mapping + meta assignment; completed stages discarded, never concurrent CUDA residency",
                      "attention": "PyTorch SDPA; CUDA math fallback disabled", "surfaceExtractor": "official scikit-image Marching Cubes"}
    finally:
        for hook in hooks:
            hook.remove()
        for component in components.values():
            component.to(device="meta")
        del pipeline
        gc.collect()
        if options["device"] == "cuda":
            torch.cuda.empty_cache()


def _official_decode(pipeline_class, vae, tensor, resolution, num_chunks):
    """Use upstream export verbatim: its single scale division precedes VAE decoding."""
    from types import SimpleNamespace
    return pipeline_class._export(SimpleNamespace(vae=vae), tensor, output_type="trimesh", box_v=1.01,
                                  mc_level=0.0, num_chunks=num_chunks, octree_resolution=resolution,
                                  mc_algo="mc", enable_pbar=False)


def _extract(torch, source, files, options, resolution, checkpoint_path, expected_sha, progress, output, manifest):
    tensor, record = _load_latents(torch, checkpoint_path, expected_sha, manifest)
    pipeline_class, instantiate, surface_extractors, config = _source_runtime(source, files)
    progress("loading pinned VAE only; no image conditioning or shape resampling")
    vae = _load_component(torch, instantiate, config, "vae",
                          files["hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors"])
    dtype = torch.float16 if options["device"] == "cuda" else torch.float32
    try:
        if options["device"] == "cuda":
            torch.cuda.reset_peak_memory_stats()
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            torch.backends.cuda.enable_math_sdp(False)
        vae.surface_extractor = surface_extractors["mc"]()
        vae.to(device=options["device"], dtype=dtype)
        tensor = tensor.to(device=options["device"], dtype=dtype)
        progress("re-extracting cached learned surface with pinned VAE", inputLatentSha256=expected_sha,
                 gridResolution=resolution, scaleApplications=1)
        with torch.inference_mode():
            meshes = _official_decode(pipeline_class, vae, tensor, resolution, options["numChunks"])
        check(len(meshes) == 1 and meshes[0] is not None, "RECONSTRUCTION_PROVIDER_EMPTY_MESH", "Cached latent did not produce a surface")
        mesh = meshes[0]
        _validate_mesh(mesh)
        # Preserve the original unscaled tensor bytes for chained, controlled re-extraction.
        cached = Path(output) / "shape-latents.safetensors"
        cached.write_bytes(_checkpoint_bytes(checkpoint_path, expected_sha))
        record["path"] = str(cached)
        _write(Path(output) / "shape-latents.json", record)
        return mesh, {"operation": "extract", "resampled": False, "stageOrder": ["vae"],
                      "loadedComponents": ["vae"], "conditioningExecuted": False, "samplingExecuted": False,
                      "inputLatentSha256": expected_sha, "latentCheckpoint": record,
                      "latentScaleApplications": 1, "latentInputSemantics": LATENT_SEMANTICS,
                      "precision": str(dtype), "surfaceExtractor": "official scikit-image Marching Cubes",
                      "peakAllocatedVramBytes": torch.cuda.max_memory_allocated() if options["device"] == "cuda" else None,
                      "memoryStrategy": "mapped pinned VAE decoder only; no conditioner or DiT allocation",
                      "attention": "PyTorch SDPA; CUDA math fallback disabled",
                      "seed": int(record["seed"]), "steps": int(record["steps"]),
                      "samplingDevice": record["samplingDevice"],
                      "comparisonScope": "Re-extraction of the exact cached unscaled latent; denser geometry is not proof of better anatomy"}
    finally:
        vae.to(device="meta")
        del tensor, vae
        gc.collect()
        if options["device"] == "cuda":
            torch.cuda.empty_cache()


def _child(request_path):
    request = _json(request_path)
    output = _root(request["output"], "output")
    options = normalize_options(request["options"], request["resolution"])
    started = time.monotonic()
    def progress(stage, **extra):
        _write(output / "inference-progress.json", {"provider": PROVIDER, "stage": stage,
               "elapsedSeconds": time.monotonic() - started, **extra})
        check(time.monotonic() - started <= options["timeoutSeconds"], "RECONSTRUCTION_PROVIDER_TIMEOUT", "Provider deadline exceeded")
    try:
        os.environ.update(_offline_environment())
        os.environ.update(_local_cache_environment(output))
        _disable_network()
        progress("verifying pinned provider source, license, config and checkpoint")
        manifest, source, files = validate_assets(options)
        import torch
        torch.set_num_threads(options["cpuThreads"])
        resources = resource_preflight(torch, options, output)
        progress("resource preflight passed", resources=resources)
        if request["operation"] == "preflight":
            _write(output / "provider-result.json", {"ok": True, "provider": PROVIDER, "resources": resources})
            return 0
        check(request["operation"] in ("generate", "extract"), "RECONSTRUCTION_PROVIDER_OPERATION", "Unknown provider operation")
        if request["operation"] == "generate":
            from PIL import Image
            image_path = Path(request["image"])
            check(image_path == output / "provider-conditioning.png", "RECONSTRUCTION_PROVIDER_IMAGE", "Unexpected conditioning path")
            with Image.open(image_path) as opened:
                image = opened.copy()
            mesh, measured = _infer(torch, source, files, options, request["resolution"], image, progress, output, manifest)
        else:
            checkpoint_path = Path(request["checkpoint"])
            check(checkpoint_path == output / "shape-latents-input.safetensors",
                  "RECONSTRUCTION_PROVIDER_LATENT_PATH", "Unexpected copied latent checkpoint path")
            mesh, measured = _extract(torch, source, files, options, request["resolution"], checkpoint_path,
                                      request["expectedSha256"], progress, output, manifest)
        progress("exporting actual generated triangle mesh")
        mesh.export(output / "learned-mesh.glb")
        mesh.export(output / "learned-mesh.ply")
        provenance = {"provider": PROVIDER, "sourceCommit": manifest["source"]["commit"],
                      "modelRevision": manifest["model"]["revision"], "weightsSha256": manifest["model"]["files"][0]["sha256"],
                      "device": options["device"], "gridResolution": request["resolution"], "steps": options["steps"],
                      "seed": options["seed"], "seconds": time.monotonic() - started, "resources": resources,
                      "license": manifest["license"], "geometryStatus": "Single-view learned shape hypothesis; hidden shape and physical scale are not observed",
                      "appearanceStatus": "Untextured geometry; no source-photo projection or PBR texture synthesis performed",
                      "vertices": len(mesh.vertices), "faces": len(mesh.faces), **measured}
        _write(output / "provider-result.json", {"ok": True, "provider": PROVIDER, "provenance": provenance})
        progress("complete", vertices=len(mesh.vertices), faces=len(mesh.faces))
        return 0
    except Exception as error:
        import traceback
        traceback.print_exc()
        result = {"ok": False, "provider": PROVIDER,
                  "code": getattr(error, "code", "RECONSTRUCTION_PROVIDER_INFERENCE_FAILED"),
                  "message": str(error), "details": getattr(error, "details", {}), "type": type(error).__name__}
        _write(output / "provider-result.json", result)
        _write(output / "inference-progress.json", {"provider": PROVIDER, "stage": "failed", "error": result,
               "elapsedSeconds": time.monotonic() - started})
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", required=True, type=Path)
    sys.exit(_child(parser.parse_args().child))
