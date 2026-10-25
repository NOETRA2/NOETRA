"""Offline contract tests; no model download or large inference."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("hunyuan_mini", Path(__file__).with_name("hunyuan_mini.py"))
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


class ProviderContractTests(unittest.TestCase):
    def setUp(self):
        # Windows sandbox TEMP may be creatable but have non-inheriting ACLs.
        # Keep fixtures inside this provider's writable workspace directory.
        self.temporary_parent = Path(__file__).parent / ".test-tmp"
        self.temporary_parent.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="noetra-provider-test-", dir=self.temporary_parent)
        self.root = Path(self.directory.name)
        self.options = {"sourceDirectory": str(self.root), "assetDirectory": str(self.root)}

    def tearDown(self):
        self.directory.cleanup()
        self.temporary_parent.rmdir()

    def test_upstream_identity_is_pinned_and_weight_is_not_a_pickle(self):
        manifest = provider._json(provider.MANIFEST)
        self.assertEqual(manifest["model"]["revision"], "f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6")
        self.assertEqual(manifest["source"]["commit"], "f8db63096c8282cb27354314d896feba5ba6ff8a")
        weight = manifest["model"]["files"][0]
        self.assertTrue(weight["path"].endswith(".safetensors"))
        self.assertEqual(weight["bytes"], 3822584202)
        self.assertEqual(weight["sha256"], "bdbcef30dd0149a281e17d5b5b1fdad1122c904e098a42f3100e04e03c247bc4")
        self.assertFalse(manifest["model"]["gated"])

    def test_rejects_unbounded_steps_resolution_unknown_and_bool_settings(self):
        for options, resolution in [({"steps": 31}, 256), ({"timeoutSeconds": 1801}, 256),
                                    ({"steps": True}, 256), ({"device": "auto"}, 256),
                                    ({"url": "https://example.com"}, 256), ({}, 1024)]:
            with self.subTest(options=options, resolution=resolution), self.assertRaises(provider.ProviderError):
                provider.normalize_options({**self.options, **options}, resolution)

    def test_same_length_modified_asset_is_rejected(self):
        data = b"verified local source\n"
        path = self.root / "source.py"
        path.write_bytes(data)
        record = {"path": "source.py", "bytes": len(data), "gitBlobSha1":
                  hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
        provider._verify_file(self.root, record)
        path.write_bytes(data.replace(b"verified", b"tampered"))
        with self.assertRaisesRegex(provider.ProviderError, "ASSET_CHANGED"):
            provider._verify_file(self.root, record)

    def test_checkpoint_sha256_and_missing_assets_fail_before_import(self):
        path = self.root / "model.safetensors"
        path.write_bytes(b"test checkpoint")
        record = {"path": path.name, "bytes": path.stat().st_size, "sha256": "0" * 64}
        with self.assertRaisesRegex(provider.ProviderError, "ASSET_CHANGED"):
            provider._verify_file(self.root, record)
        path.unlink()
        with self.assertRaisesRegex(provider.ProviderError, "ASSET_MISSING"):
            provider._verify_file(self.root, record)

    def test_absolute_escape_is_rejected(self):
        with self.assertRaisesRegex(provider.ProviderError, "PROVIDER_PATH"):
            provider._inside(self.root, "../outside.py")

    def test_cpu_torch_cannot_claim_cuda_from_an_nvidia_driver(self):
        class Cuda:
            @staticmethod
            def is_available():
                return False
        class Torch:
            __version__ = "test-cpu"
            cuda = Cuda()
        options = provider.normalize_options(self.options)
        with self.assertRaisesRegex(provider.ProviderError, "CUDA_UNAVAILABLE"):
            provider.resource_preflight(Torch(), options, self.root, available_ram=8 * provider.GIB)

    def test_cuda_free_memory_and_architecture_are_measured(self):
        class Properties:
            major, minor, name = 8, 6, "RTX 3050 test double"
        class Cuda:
            @staticmethod
            def is_available():
                return True
            @staticmethod
            def get_device_properties(index):
                return Properties()
            @staticmethod
            def mem_get_info(index):
                return 2 * provider.GIB, 4 * provider.GIB
        class Torch:
            __version__ = "test-cuda"
            cuda = Cuda()
        with self.assertRaisesRegex(provider.ProviderError, "PROVIDER_VRAM"):
            provider.resource_preflight(Torch(), provider.normalize_options(self.options), self.root,
                                        available_ram=8 * provider.GIB)

    def test_cpu_mode_does_not_silently_overcommit_laptop_ram(self):
        class Torch:
            __version__ = "test"
        options = provider.normalize_options({**self.options, "device": "cpu"})
        with self.assertRaisesRegex(provider.ProviderError, "PROVIDER_RAM"):
            provider.resource_preflight(Torch(), options, self.root, available_ram=2 * provider.GIB)

    def test_actual_memory_probe_reports_physical_and_windows_commit_separately(self):
        import os
        memory = provider._memory_snapshot()
        self.assertGreater(memory["availableRamBytes"], 0)
        self.assertIn("memoryProbe", memory)
        if os.name == "nt":
            self.assertGreaterEqual(memory["totalRamBytes"], memory["availableRamBytes"])
            self.assertGreaterEqual(memory["commitLimitBytes"], memory["availableCommitBytes"])
            self.assertIn("not extra physical RAM", memory["memoryProbe"])

    def test_low_ram_policy_is_explicit_boolean_and_cuda_only(self):
        for extra in ({"experimentalLowRam": 1}, {"experimentalLowRam": True, "device": "cpu"}):
            with self.subTest(extra=extra), self.assertRaisesRegex(provider.ProviderError, "LOW_RAM_POLICY"):
                provider.normalize_options({**self.options, **extra})
        self.assertFalse(provider.normalize_options(self.options)["experimentalLowRam"])

    def test_experimental_ram_policy_requires_measured_commit_and_preserves_gpu_checks(self):
        class Properties:
            major, minor, name = 8, 6, "RTX 3050 test double"
        class Cuda:
            @staticmethod
            def is_available():
                return True
            @staticmethod
            def get_device_properties(index):
                return Properties()
            @staticmethod
            def mem_get_info(index):
                return 3 * provider.GIB, 4 * provider.GIB
        class Version:
            cuda = "12.4"
        class Torch:
            __version__ = "test-cuda"
            cuda, version = Cuda(), Version()
        options = provider.normalize_options({**self.options, "experimentalLowRam": True})
        memory = {"availableRamBytes": provider.GIB, "availableCommitBytes": 20 * provider.GIB}
        with patch.object(provider, "_memory_snapshot", return_value=memory), patch.object(provider.os, "name", "nt"):
            result = provider.resource_preflight(Torch(), options, self.root)
            self.assertEqual(result["admissionPolicy"]["minimumAvailablePhysicalRamBytes"], 768 * 1024 * 1024)
            self.assertTrue(result["admissionPolicy"]["experimentalLowRam"])
        for available in (None, 5 * provider.GIB):
            memory = {"availableRamBytes": provider.GIB}
            if available is not None:
                memory["availableCommitBytes"] = available
            with patch.object(provider, "_memory_snapshot", return_value=memory), patch.object(provider.os, "name", "nt"), self.assertRaisesRegex(provider.ProviderError, "PROVIDER_COMMIT"):
                provider.resource_preflight(Torch(), options, self.root)

    def test_timeout_kills_worker_and_records_failure(self):
        class Process:
            returncode = 1
            killed = False
            def wait(self, timeout):
                if not self.killed:
                    raise subprocess.TimeoutExpired("fixed provider", timeout)
                return 1
            def kill(self):
                self.killed = True
        process = Process()
        with patch.object(provider.subprocess, "Popen", return_value=process), self.assertRaisesRegex(provider.ProviderError, "TIMEOUT"):
            provider._run_child(self.options, self.root, "preflight")
        self.assertTrue(process.killed)
        self.assertEqual(provider._json(self.root / "provider-result.json")["code"], "RECONSTRUCTION_PROVIDER_TIMEOUT")
        self.assertEqual(provider._json(self.root / "inference-progress.json")["stage"], "failed")

    def test_network_guard_rejects_dns_and_connections_in_isolated_process(self):
        code = ("import importlib.util,socket; "
                f"s=importlib.util.spec_from_file_location('p',{str(Path(provider.__file__))!r}); "
                "p=importlib.util.module_from_spec(s); s.loader.exec_module(p); p._disable_network(); "
                "socket.create_connection(('127.0.0.1',9),timeout=.1)")
        result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RECONSTRUCTION_PROVIDER_NETWORK_DISABLED", result.stderr)

    def test_library_caches_stay_under_this_run_without_changing_parent_environment(self):
        import os
        before = dict(os.environ)
        environment = provider._local_cache_environment(self.root)
        self.assertEqual(before, dict(os.environ))
        self.assertTrue((self.root / "provider-runtime-cache").is_dir())
        for path in environment.values():
            self.assertTrue(Path(path).is_relative_to(self.root))
        self.assertEqual(provider._offline_environment()["HF_HUB_OFFLINE"], "1")

    def test_meta_loader_assigns_actual_tensor_values_without_random_initialization(self):
        try:
            import torch
            from safetensors.torch import save_file
        except ImportError:
            self.skipTest("Optional PyTorch/safetensors unavailable in this interpreter")
        weights = torch.tensor([[1., 2.], [3., 4.]], dtype=torch.float16)
        checkpoint = self.root / "tiny.safetensors"
        save_file({"model.weight": weights, "model.bias": torch.tensor([5., 6.], dtype=torch.float16)}, checkpoint)
        model = provider._load_component(torch, lambda unused: torch.nn.Linear(2, 2), {"model": {}}, "model", str(checkpoint))
        self.assertFalse(model.weight.is_meta)
        self.assertEqual(model.weight.dtype, torch.float16)
        with torch.inference_mode():
            self.assertTrue(torch.equal(model(torch.ones(1, 2, dtype=torch.float16)), torch.tensor([[8., 13.]], dtype=torch.float16)))

    def _torch(self):
        try:
            import torch
            import safetensors
            return torch
        except ImportError:
            self.skipTest("Optional PyTorch/safetensors unavailable")

    def test_latent_cache_retains_exact_unscaled_sampling_tensor_and_identity(self):
        torch = self._torch()
        tensor = torch.linspace(-2, 2, 3072 * 64, dtype=torch.float32).reshape(provider.LATENT_SHAPE).half()
        manifest = provider._json(provider.MANIFEST)
        record = provider._save_latents(torch, tensor, self.root, manifest, provider.normalize_options(self.options))
        restored, metadata = provider._load_latents(torch, record["path"], record["sha256"], manifest)
        self.assertTrue(torch.equal(restored, tensor))
        self.assertEqual(metadata["semantics"], "final-sampling-output-before-vae-scale")
        self.assertEqual(metadata["modelRevision"], manifest["model"]["revision"])
        self.assertLess(record["bytes"], provider.LATENT_MAX_BYTES)
        self.assertEqual(provider._json(self.root / "shape-latents.json")["sha256"], record["sha256"])

    def test_latent_tamper_and_wrong_model_or_scale_metadata_are_rejected(self):
        torch = self._torch()
        from safetensors.torch import save_file
        manifest = provider._json(provider.MANIFEST)
        tensor = torch.ones(provider.LATENT_SHAPE, dtype=torch.float16)
        record = provider._save_latents(torch, tensor, self.root, manifest, provider.normalize_options(self.options))
        path = Path(record["path"])
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(provider.ProviderError, "LATENT_CHANGED"):
            provider._load_latents(torch, path, record["sha256"], manifest)
        for field, wrong in (("modelRevision", "other-model"), ("semantics", "already-vae-scaled"), ("vaeScaleFactor", "2.0")):
            metadata = {**provider._latent_identity(manifest), "seed": "1", "steps": "8", "samplingDevice": "cuda", "guidanceScale": "5.0", field: wrong}
            save_file({"latents": tensor}, str(path), metadata=metadata)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.subTest(field=field), self.assertRaisesRegex(provider.ProviderError, "LATENT_IDENTITY"):
                provider._load_latents(torch, path, digest, manifest)

    def test_latent_shape_dtype_and_finiteness_limits(self):
        torch = self._torch()
        for tensor in (torch.ones(1, 512, 64), torch.ones(provider.LATENT_SHAPE, dtype=torch.float64),
                       torch.full(provider.LATENT_SHAPE, float("nan"))):
            with self.subTest(shape=tuple(tensor.shape), dtype=tensor.dtype), self.assertRaises(provider.ProviderError):
                provider._validate_latent_tensor(torch, tensor)

    def test_extract_validates_and_copies_checkpoint_before_launching_fixed_child(self):
        torch = self._torch()
        checkpoint_folder = self.root / "source-cache"
        checkpoint_folder.mkdir()
        manifest = provider._json(provider.MANIFEST)
        record = provider._save_latents(torch, torch.ones(provider.LATENT_SHAPE, dtype=torch.float16),
                                        checkpoint_folder, manifest, provider.normalize_options(self.options))
        output = self.root / "new-output"
        output.mkdir()
        class Process:
            returncode = 0
            def wait(self, timeout):
                provider._write(output / "provider-result.json", {"ok": True})
        with patch.object(provider.subprocess, "Popen", return_value=Process()):
            provider._run_child(self.options, output, "extract", checkpoint=record["path"], expected_sha=record["sha256"])
        copied = output / "shape-latents-input.safetensors"
        self.assertEqual(copied.read_bytes(), Path(record["path"]).read_bytes())
        request = provider._json(output / "provider-request.json")
        self.assertEqual(request["operation"], "extract")
        self.assertEqual(request["expectedSha256"], record["sha256"])
        self.assertNotIn("image", request)

    def test_real_upstream_export_divides_cached_latent_by_scale_exactly_once(self):
        torch = self._torch()
        import ast
        # Extract the exact pinned upstream method without importing large model
        # libraries or allocating any model. The executed math is upstream code.
        source = Path(__file__).resolve().parents[4] / ".tools/Hunyuan3D-2/hy3dgen/shapegen/pipelines.py"
        if not source.is_file():
            self.skipTest("Pinned optional source is not provisioned")
        upstream = ast.parse(source.read_text(encoding="utf-8"))
        parent = next(n for n in upstream.body if isinstance(n, ast.ClassDef) and n.name == "Hunyuan3DDiTPipeline")
        method = next(n for n in parent.body if isinstance(n, ast.FunctionDef) and n.name == "_export")
        method.decorator_list = []
        namespace = {"export_to_trimesh": lambda value: value}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), "exec"), namespace)
        class Pipeline:
            _export = namespace["_export"]
        class Vae:
            scale_factor = provider.VAE_SCALE
            received = None
            calls = 0
            def __call__(self, latent):
                self.received = latent.clone()
                self.calls += 1
                return latent
            def latents2mesh(self, latent, **kwargs):
                return [latent]
        vae = Vae()
        cached = torch.tensor([[[2.0, -3.0]]], dtype=torch.float32)
        original = cached.clone()
        result = provider._official_decode(Pipeline, vae, cached, 256, 1024)
        self.assertTrue(torch.equal(vae.received, cached / provider.VAE_SCALE))
        self.assertTrue(torch.equal(cached, original))
        self.assertTrue(torch.equal(result[0], vae.received))
        self.assertEqual(vae.calls, 1)

    def test_reextraction_loads_only_vae_without_touching_sampling_or_conditioner(self):
        torch = self._torch()
        import numpy as np
        manifest = provider._json(provider.MANIFEST)
        source = self.root / "input"
        source.mkdir()
        options = provider.normalize_options({**self.options, "device": "cpu"})
        record = provider._save_latents(torch, torch.ones(provider.LATENT_SHAPE, dtype=torch.float16), source, manifest, options)
        output = self.root / "extracted"
        output.mkdir()
        class Mesh:
            vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
            faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
        vae = torch.nn.Identity()
        files = {"hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors": "unused-test-path"}
        with patch.object(provider, "_source_runtime", return_value=(object, object, {"mc": lambda: object()}, {})), \
             patch.object(provider, "_load_component", return_value=vae) as load, \
             patch.object(provider, "_official_decode", return_value=[Mesh()]) as decode:
            mesh, provenance = provider._extract(torch, self.root, files, options, 256, record["path"], record["sha256"],
                                                  lambda *args, **kwargs: None, output, manifest)
        self.assertEqual(load.call_count, 1)
        self.assertEqual(load.call_args.args[3], "vae")
        self.assertEqual(decode.call_count, 1)
        self.assertEqual(provenance["stageOrder"], ["vae"])
        self.assertFalse(provenance["conditioningExecuted"])
        self.assertFalse(provenance["samplingExecuted"])
        self.assertEqual(provenance["latentCheckpoint"]["sha256"], record["sha256"])
        self.assertEqual((output / "shape-latents.safetensors").read_bytes(), Path(record["path"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
