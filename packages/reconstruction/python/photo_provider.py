"""Configured, offline, attributed learned geometry. No model/source download here."""
from pathlib import Path
import sys,os,json,hashlib,gc,time
import numpy as np
from PIL import Image
from geometry import require

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def validate_models(vision):
    manifest=json.loads(Path(vision['modelManifest']).read_text(encoding='utf8'))
    source=Path(vision['sourceDirectory']).resolve()
    approvals=json.loads(Path(vision['sourceManifest']).read_text(encoding='utf8'))
    require(source.is_dir() and approvals['sourceCommit']==manifest['sourceCommit'],'RECONSTRUCTION_MODEL_SOURCE_IDENTITY')
    for name,expected in approvals['pythonFiles'].items():
        path=source/name;require(path.resolve().is_relative_to(source) and path.is_file() and digest(path)==expected,'RECONSTRUCTION_MODEL_SOURCE_CHANGED')
    for key in ['weights','config','dinoConfig','background']:
        record=manifest['files'][key];path=Path(record['path'])
        require(path.is_absolute() and path.is_file() and path.stat().st_size==record['bytes'] and digest(path)==record['sha256'],'RECONSTRUCTION_MODEL_CHANGED')
    return manifest

def foreground(image,manifest,output,supplied=None):
    import onnxruntime as ort
    from rembg import remove,new_session
    if supplied is not None:
        alpha=np.asarray(Image.open(supplied).convert('L'));require(alpha.shape==(image.height,image.width),'RECONSTRUCTION_IMAGE_SIZE')
        provenance='Caller-supplied foreground mask; authenticity and physical coverage not independently established'
    elif image.mode=='RGBA' and image.getextrema()[3][0]<255:
        alpha=np.asarray(image.getchannel('A'));provenance='Supplied image alpha'
    else:
        model=Path(manifest['files']['background']['path']);os.environ['U2NET_HOME']=str(model.parent)
        # The exact model exists and was hashed before rembg can look for it.
        require(model.name=='u2net.onnx','RECONSTRUCTION_BACKGROUND_MODEL')
        session=new_session('u2net',providers=['CPUExecutionProvider'])
        result=remove(image.convert('RGB'),session=session)
        alpha=np.asarray(result.getchannel('A'));del session,result;gc.collect()
        provenance='Local U2Net foreground estimate; not a physical/semantic ground-truth mask'
    require((alpha>127).sum()>=100,'RECONSTRUCTION_FOREGROUND_EMPTY')
    Image.fromarray(alpha.astype(np.uint8)).save(output/'foreground.png')
    rgb=np.asarray(image.convert('RGB'));rgba=np.dstack([rgb,alpha]).astype(np.uint8)
    yy,xx=np.where(alpha>127);x0,x1=int(xx.min()),int(xx.max())+1;y0,y1=int(yy.min()),int(yy.max())+1
    crop=rgba[y0:y1,x0:x1];side=max(crop.shape[:2]);canvas=int(np.ceil(side/.85));dx=(canvas-crop.shape[1])//2;dy=(canvas-crop.shape[0])//2
    square=np.zeros((canvas,canvas,4),np.uint8);square[dy:dy+crop.shape[0],dx:dx+crop.shape[1]]=crop
    square=np.asarray(Image.fromarray(square).resize((512,512),Image.Resampling.LANCZOS))
    a=square[:,:,3:4].astype(np.float32)/255.;conditioning=(square[:,:,:3]*a+127.5*(1-a)).clip(0,255).astype(np.uint8)
    picture=Image.fromarray(conditioning);picture.save(output/'conditioning.png');Image.fromarray(square[:,:,3]).save(output/'conditioning-mask.png')
    factor=512/canvas
    transform=[[factor,0,(dx-x0+.5)*factor-.5],[0,factor,(dy-y0+.5)*factor-.5],[0,0,1]]
    return picture,{'provenance':provenance,'sourceBBox':[x0,y0,x1,y1],'sourceToConditioning':transform,'conditioningSize':[512,512],'originalResampled':False}

def triposr(image,vision,manifest,output,resolution):
    cache=output/'model-runtime-cache';cache.mkdir(exist_ok=True)
    os.environ.update({'HF_HOME':str(cache),'HF_HUB_CACHE':str(cache/'hub'),'TRANSFORMERS_CACHE':str(cache/'transformers'),
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'})
    import torch
    from omegaconf import OmegaConf
    torch.set_num_threads(4);sys.path.insert(0,str(Path(vision['sourceDirectory']).resolve()))
    from tsr.system import TSR
    import tsr.models.tokenizers.image as tokenizer
    def local_config(repo_id,filename,**unused):
        require(repo_id=='facebook/dino-vitb16' and filename=='config.json','RECONSTRUCTION_OFFLINE_MODEL_CONFIG')
        return manifest['files']['dinoConfig']['path']
    tokenizer.hf_hub_download=local_config
    cfg=OmegaConf.load(manifest['files']['config']['path']);OmegaConf.resolve(cfg)
    expected={'image_tokenizer_cls':'tsr.models.tokenizers.image.DINOSingleImageTokenizer','tokenizer_cls':'tsr.models.tokenizers.triplane.Triplane1DTokenizer',
        'backbone_cls':'tsr.models.transformer.transformer_1d.Transformer1D','post_processor_cls':'tsr.models.network_utils.TriplaneUpsampleNetwork',
        'decoder_cls':'tsr.models.network_utils.NeRFMLP','renderer_cls':'tsr.models.nerf_renderer.TriplaneNeRFRenderer'}
    require(all(cfg[k]==v for k,v in expected.items()),'RECONSTRUCTION_MODEL_CLASS_ALLOWLIST')
    started=time.monotonic()
    def progress(stage):
        (output/'inference-progress.json').write_text(json.dumps({'stage':stage,'elapsedSeconds':time.monotonic()-started}))
    progress('initializing memory-efficient local model')
    with torch.device('meta'):model=TSR(cfg)
    state=torch.load(manifest['files']['weights']['path'],map_location='cpu',weights_only=True,mmap=True)
    model.load_state_dict(state,strict=True,assign=True);del state
    progress('weights loaded; preparing CPU precision')
    model.image_tokenizer.image_mean=torch.tensor([.485,.456,.406]).reshape(1,1,3,1,1)
    model.image_tokenizer.image_std=torch.tensor([.229,.224,.225]).reshape(1,1,3,1,1)
    require(not any(p.is_meta for p in model.parameters()) and not any(b.is_meta for b in model.buffers()),'RECONSTRUCTION_MODEL_UNINITIALIZED')
    model.eval();model.renderer.set_chunk_size(4096)
    precision=vision.get('cpuPrecision','float32')
    if precision=='int8':
        # Quantize the large feature networks only. Density/RGB interpolation must
        # remain continuous: int8 decoder activations create staircase surfaces.
        model.image_tokenizer=torch.ao.quantization.quantize_dynamic(model.image_tokenizer,{torch.nn.Linear},dtype=torch.qint8,inplace=True)
        model.backbone=torch.ao.quantization.quantize_dynamic(model.backbone,{torch.nn.Linear},dtype=torch.qint8,inplace=True)
    gc.collect()
    progress('inferring geometry from reference')
    with torch.inference_mode():
        code=model([image],device='cpu')
        np.save(output/'scene-code.npy',code.detach().cpu().numpy(),allow_pickle=False)
        progress('extracting actual triangle surface')
        meshes=model.extract_mesh(code,True,resolution=resolution)
    require(len(meshes)==1 and len(meshes[0].vertices)>100,'RECONSTRUCTION_EMPTY_MESH')
    mesh=meshes[0];mesh.export(output/'learned-mesh.glb');mesh.export(output/'learned-mesh.ply')
    del model,code;gc.collect()
    progress('triangle surface extracted')
    return mesh,{'provider':'TripoSR','sourceCommit':manifest['sourceCommit'],'modelRevision':manifest['modelRevision'],
        'weightsSha256':manifest['files']['weights']['sha256'],'device':'cpu','precision':precision,'densityAndColorPrecision':'float32; never quantized',
        'surfaceExtractor':'Explicit local scikit-image CPU compatibility fallback when torchmcubes is absent',
        'gridResolution':resolution,'seconds':time.monotonic()-started,'geometryStatus':'Single-view learned hypothesis; hidden shape and scale are not observed'}
