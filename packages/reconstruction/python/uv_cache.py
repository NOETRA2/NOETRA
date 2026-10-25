"""Reuse a verified atlas only for exact matching geometry and settings."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np

def find_verified_cache(root,model_sha256,resolution):
    base=Path(root)/'.noetra/reconstruction'
    for folder in sorted(base.iterdir(),reverse=True)[:64]:
        report_path=folder/'report.json'
        if not folder.is_dir() or folder.is_symlink() or not report_path.is_file() or report_path.stat().st_size>4_000_000:continue
        try:
            report=json.loads(report_path.read_text())
            if report.get('parentModel',{}).get('sha256')!=model_sha256 or report.get('baseRefinement'):continue
            if report.get('material',{}).get('geometryExactlyUnchanged') is not True:continue
            files={k:str(folder/v) for k,v in {'input':'atlas-input-0.npz','output':'atlas-output-0.npz','qa':'atlas-0.json'}.items()}
            hashes={}
            for key,path in files.items():
                p=Path(path)
                if not p.is_file() or p.is_symlink() or p.stat().st_size>64*1024*1024:raise ValueError()
                hashes[key]=hashlib.sha256(p.read_bytes()).hexdigest()
                if report['artifactDigests'][p.name]!=hashes[key]:raise ValueError()
            with np.load(files['input'],allow_pickle=False) as a:
                if int(a['resolution'])!=resolution or int(a['padding'])!=6:continue
            return {'files':files,'sha256':hashes,'sourceRun':folder.name}
        except (ValueError,KeyError,TypeError,OSError):continue
    return None

def reuse_cache(cache,points,faces,resolution,output,qa):
    if not cache:return False
    for key,path in cache['files'].items():
        p=Path(path)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=cache['sha256'][key]:return False
    with np.load(cache['files']['input'],allow_pickle=False) as a:
        if not (np.array_equal(a['vertices'],points) and np.array_equal(a['faces'],faces) and int(a['resolution'])==resolution and int(a['padding'])==6):return False
    with np.load(cache['files']['output'],allow_pickle=False) as a:
        uv=a['loop_uv']
        if uv.shape!=(len(faces),3,2) or not np.isfinite(uv).all() or uv.min()<0 or uv.max()>1:return False
        cross=(uv[:,1,0]-uv[:,0,0])*(uv[:,2,1]-uv[:,0,1])-(uv[:,1,1]-uv[:,0,1])*(uv[:,2,0]-uv[:,0,0])
        if (np.abs(cross)<1e-15).any():return False
    shutil.copyfile(cache['files']['output'],output)
    report=json.loads(Path(cache['files']['qa']).read_text());report['cacheReuse']={'sourceRun':cache['sourceRun'],'exactGeometryAndSettingsMatched':True,'sourceHashesRechecked':True}
    Path(qa).write_text(json.dumps(report,indent=2))
    return True
