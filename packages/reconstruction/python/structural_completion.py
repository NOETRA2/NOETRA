"""Opt-in data-driven prior completion. The prior is explicit evidence, not truth."""
from pathlib import Path
import os,subprocess,hashlib,shutil,json
from geometry import require
from part_correction import permission,save

def complete(root,spec,config,helpers):
    scope,new_run,image_record=helpers;executable=permission(config);source=scope(root,spec['blend'])
    require(source.suffix.lower()=='.blend' and source.stat().st_size<=64*1024*1024,'RECONSTRUCTION_PRIOR_FORMAT')
    require(len(set(spec['wheels']))==len(spec['wheels']),'RECONSTRUCTION_DUPLICATE_WHEEL')
    require(len({p['object'] for p in spec['patches']})==len(spec['patches']),'RECONSTRUCTION_DUPLICATE_PATCH')
    run=new_run(root);record,_=image_record(root,spec['reference'],run,0);source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    saved=run/'prior.blend';shutil.copyfile(source,saved);require(hashlib.sha256(saved.read_bytes()).hexdigest()==source_sha,'RECONSTRUCTION_SOURCE_CHANGED')
    save(run/'prior-spec.json',spec);save(run/'job.json',{'source':str(saved),'output':str(run),'spec':spec})
    resources=run/'blender-runtime';resources.mkdir()
    try:
        process=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('structural_blender.py')),'--',str(run/'job.json')],
            cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=480,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (run/'blender-log.txt').write_bytes(process.stdout[-262144:]);require(process.returncode==0,'RECONSTRUCTION_STRUCTURAL_BLENDER_FAILED')
        verification=json.loads((run/'structure-verification.json').read_text())
        require(verification['protectedObjectsUnchanged'] and all(w['completeCircle'] for w in verification['wheels']) and all(f['allVerticesInFrame'] for f in verification['framing']),'RECONSTRUCTION_STRUCTURE_VERIFICATION')
        require(hashlib.sha256(source.read_bytes()).hexdigest()==source_sha and hashlib.sha256(Path(record['source']).read_bytes()).hexdigest()==record['sha256'],'RECONSTRUCTION_SOURCE_CHANGED')
        report={'runId':run.name,'kind':'explicit-structural-prior-completion','images':[record],'prior':{'source':str(source),'preserved':str(saved),'sha256':source_sha,'provenance':spec['provenance']},
            'verification':verification,'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'render':str(run/'reference.png')},
            'views':[{'name':f['name'],'image':str(run/(f['name']+'.png'))} for f in verification['framing']],
            'unknowns':['This shape comes from an explicit authored template and constraints, not automatic reconstruction of invisible geometry.','Original photo is a reference only; no photo texture is projected on this model.','Separate modeled parts are not a watertight engineering solid; exact reference fidelity is not established.'],
            'artifactDigests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.suffix in ['.blend','.glb','.png','.npz','.json']}}
        save(run/'report.json',report);return {k:v for k,v in report.items() if k not in ['images','artifactDigests']}
    except Exception:
        import traceback
        (run/'failure-traceback.txt').write_text(traceback.format_exc(),encoding='utf8');raise
