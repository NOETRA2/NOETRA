"""Direct pinned Hunyuan3D baseline: no NOETRA SDK, engine or modules imported.

The same mapped-fp16 / sequential offload strategy as the assisted run is kept
for a fair 4 GB hardware comparison. This is not the upstream default loader.
Input is a shared frozen RGBA image (including its earlier U2Net matte).
No network, asset download, new licence acceptance or reference-image repaint.
"""
from pathlib import Path
import argparse,os,sys,json,hashlib,time,gc,copy,socket,importlib.util

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main(args):
    out=Path(args.output).resolve();out.mkdir(exist_ok=True)
    assert not (out/'raw.glb').exists(),'Use a fresh output directory'
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME=str(out/'cache'),TORCH_HOME=str(out/'cache'),OMP_NUM_THREADS='3',MKL_NUM_THREADS='3')
    def blocked(*a,**kw):raise RuntimeError('Network disabled for offline baseline')
    socket.create_connection=blocked;socket.socket.connect=blocked
    started=time.monotonic();source=Path(args.source).resolve();assets=Path(args.assets).resolve();manifest=json.loads(Path(args.manifest).read_text())
    def progress(stage):
        (out/'progress.json').write_text(json.dumps({'stage':stage,'seconds':time.monotonic()-started}));print(stage,flush=True)
    progress('Verifying pinned upstream source and weights')
    for record in manifest['source']['files']:
        p=source/record['path'];raw=p.read_bytes()
        assert len(raw)==record['bytes'] and hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==record['gitBlobSha1'],record['path']
    weight=assets/'hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors'
    assert digest(weight)=='bdbcef30dd0149a281e17d5b5b1fdad1122c904e098a42f3100e04e03c247bc4'
    image=Path(args.image).resolve();image_sha=digest(image)
    import torch,yaml,numpy as np
    from PIL import Image
    from safetensors import safe_open
    torch.set_num_threads(3);assert torch.cuda.is_available()
    assert torch.cuda.mem_get_info()[0]>2700*1024**2,'Insufficient available GPU memory for controlled baseline'
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('hy3dgen',source/'hy3dgen/__init__.py',submodule_search_locations=[str(source/'hy3dgen')])
    package=importlib.util.module_from_spec(spec);sys.modules['hy3dgen']=package;spec.loader.exec_module(package)
    from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline,instantiate_from_config
    from hy3dgen.shapegen.models.autoencoders import SurfaceExtractors
    config=yaml.safe_load((assets/'hunyuan3d-dit-v2-mini-turbo/config.yaml').read_text());config=copy.deepcopy(config)
    config['conditioner']['params']['main_image_encoder']['kwargs']['config']['_attn_implementation']='sdpa'
    def load(name):
        progress('Loading direct upstream '+name)
        with torch.device('meta'):component=instantiate_from_config(config[name])
        if name=='vae':component.encoder=None;component.pre_kl=None
        with safe_open(weight,framework='pt',device='cpu') as handle:
            prefix=name+'.';state={k[len(prefix):]:handle.get_tensor(k) for k in handle.keys() if k.startswith(prefix)}
            if name=='vae':state={k:v for k,v in state.items() if not k.startswith(('encoder.','pre_kl.'))}
            component.load_state_dict(state,strict=True,assign=True)
        for module in component.modules():
            if module.__class__.__name__=='FourierEmbedder':
                module.frequencies=2.0**torch.arange(module.num_freqs,dtype=torch.float32,device='cpu')
                if config['vae']['params'].get('include_pi',True):module.frequencies*=torch.pi
        assert not any(p.is_meta for p in component.parameters())
        return component.eval().requires_grad_(False)
    components={name:load(name) for name in ['conditioner','model','vae']}
    pipeline=Hunyuan3DDiTFlowMatchingPipeline(**components,scheduler=instantiate_from_config(config['scheduler']),image_processor=instantiate_from_config(config['image_processor']),device='cpu',dtype=torch.float16)
    pipeline.device=torch.device('cuda');pipeline.dtype=torch.float16;pipeline.vae.surface_extractor=SurfaceExtractors['mc']()
    active={'name':None};stages=[]
    def activate(name):
        def hook(module,arguments):
            if active['name']==name:return
            if active['name'] is not None:components[active['name']].to('meta');gc.collect();torch.cuda.empty_cache()
            module.to(device='cuda',dtype=torch.float16);active['name']=name;stages.append(name);progress('Direct upstream '+name+' running')
        return hook
    handles=[m.register_forward_pre_hook(activate(n)) for n,m in components.items()]
    torch.backends.cuda.enable_flash_sdp(True);torch.backends.cuda.enable_mem_efficient_sdp(True);torch.backends.cuda.enable_math_sdp(False);torch.cuda.reset_peak_memory_stats()
    with Image.open(image) as opened:rgba=opened.copy()
    infer_start=time.monotonic()
    with torch.inference_mode():
        meshes=pipeline(image=rgba,num_inference_steps=8,guidance_scale=5.,generator=torch.Generator(device='cuda').manual_seed(12345),octree_resolution=192,num_chunks=1024,mc_algo='mc',output_type='trimesh',enable_pbar=False)
    inference=time.monotonic()-infer_start;assert len(meshes)==1 and meshes[0] is not None
    mesh=meshes[0];assert np.isfinite(mesh.vertices).all();mesh.export(out/'raw.glb');mesh.export(out/'raw.ply')
    assert digest(image)==image_sha
    report={'method':'Direct upstream Hunyuan pipeline, no NOETRA engine/SDK/runtime imports','provider':'Hunyuan3D-2mini Turbo',
      'sourceCommit':manifest['source']['commit'],'modelRevision':manifest['model']['revision'],'weightsSha256':digest(weight),
      'conditioningSha256':image_sha,'inputScope':'Same frozen RGBA conditioning image as the assisted run. Its U2Net alpha is shared, not independently re-estimated.',
      'seed':12345,'steps':8,'resolution':192,'numChunks':1024,'precision':'float16','stageOrder':stages,
      'inferenceSeconds':inference,'totalSeconds':time.monotonic()-started,'peakAllocatedVramBytes':torch.cuda.max_memory_allocated(),
      'vertices':len(mesh.vertices),'triangles':len(mesh.faces),'watertight':bool(mesh.is_watertight),'windingConsistent':bool(mesh.is_winding_consistent),
      'rawMeshSha256':digest(out/'raw.glb'),'accuracyPercent':None,'reason':'No ground-truth 3D lion or calibrated correspondence; no 90% claim.',
      'confounds':['Standalone benchmark keeps the same custom memory staging as the assisted provider. It is not the upstream default deployment.','A deterministic raw shape may match the assisted raw shape; this does not demonstrate an accuracy improvement.']}
    (out/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();[parser.add_argument('--'+key,required=True) for key in ['source','assets','manifest','image','output']]
    main(parser.parse_args())
