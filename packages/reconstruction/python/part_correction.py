"""Reusable part-level correction with attributed observations and measured gates.
No car-specific construction code, providers, uploads, eval or executable inputs.
"""
import os,json,math,time,shutil,hashlib,subprocess,uuid
from pathlib import Path
import numpy as np
import cv2 as cv
from geometry import require,boundary,symmetric_distance

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf8');os.replace(temporary,path)

def read(path):
    require(path.is_file() and path.stat().st_size<4_000_000,'RECONSTRUCTION_MANIFEST_LIMIT')
    return json.loads(path.read_text(encoding='utf8'))

def palette(index):return np.array([64+64*(index%3),64+64*((index//3)%3),64+64*((index//9)%3)])

def validate_spec(spec):
    parts={p['id']:p for p in spec['parts']};parameters={p['id']:p for p in spec['parameters']}
    require(len(parts)==len(spec['parts']) and len(parameters)==len(spec['parameters']),'RECONSTRUCTION_DUPLICATE_ID')
    names=[n for p in parts.values() for n in p['objects']]
    require(len(names)==len(set(names)),'RECONSTRUCTION_PART_OVERLAP')
    require(len({v['id'] for v in spec['views']})==len(spec['views']),'RECONSTRUCTION_DUPLICATE_ID')
    observed=set()
    for view in spec['views']:
        seen=set()
        for a in view['annotations']:
            require(a['partId'] in parts and a['partId'] not in seen,'RECONSTRUCTION_ANNOTATION_PART')
            seen.add(a['partId']);observed.add(a['partId'])
            polygon=np.array(a['polygon'],float)
            require(polygon.ndim==2 and polygon.shape[1]==2 and np.isfinite(polygon).all(),'RECONSTRUCTION_POLYGON')
            require(abs(cv.contourArea(polygon.astype(np.float32)))>=2,'RECONSTRUCTION_POLYGON_AREA')
    controls=set()
    for p in parameters.values():
        require(p['partId'] in parts and p['partId'] in observed,'RECONSTRUCTION_PARAMETER_PART')
        require(p['minimum']<p['maximum'] and p['step']<=p['maximum']-p['minimum'],'RECONSTRUCTION_PARAMETER_BOUNDS')
        require(p['minimum']<=0<=p['maximum'],'RECONSTRUCTION_PARAMETER_BOUNDS')
        require(all(math.isfinite(p[k]) for k in ['minimum','maximum','step']),'RECONSTRUCTION_NONFINITE')
        if p['kind']=='translate':
            require(not any(k in p for k in ['object','indices','spline']),'RECONSTRUCTION_TRANSLATION_CONTROL')
            keys=[(n,'translate',p['axis']) for n in parts[p['partId']]['objects']]
        else:
            require(p.get('object') in parts[p['partId']]['objects'] and p.get('indices'),'RECONSTRUCTION_PARAMETER_PART_OWNERSHIP')
            require(len(p['indices'])==len(set(p['indices'])),'RECONSTRUCTION_DUPLICATE_CONTROL')
            require((p['kind']=='curve_offset')==('spline' in p),'RECONSTRUCTION_SPLINE_CONTROL')
            keys=[(p['object'],p['kind'],p.get('spline'),i,p['axis']) for i in p['indices']]
        require(not any(k in controls for k in keys),'RECONSTRUCTION_OVERLAPPING_CONTROL');controls.update(keys)

def check_sources(root,run,report,scope):
    source=scope(root,report['sceneSource']);copy=scope(root,run/'source.blend')
    require(source.is_file() and sha(source)==report['sceneSha256'] and sha(copy)==report['sceneSha256'],'RECONSTRUCTION_SCENE_CHANGED')
    for name,digest in report['runtimeDigests'].items():
        if report.get('runtimeSnapshot'):
            path=scope(root,run/'runtime'/name)
        else:
            # Legacy observations remain readable after helper upgrades. Their
            # adapter/math identity is checked; continuing edits needs migration.
            if name=='part_correction.py':continue
            path=Path(__file__).with_name(name)
        require(sha(path)==digest,'RECONSTRUCTION_SCRIPT_CHANGED')

def permission(config):
    require(config.get('allowBlenderExecution') is True,'RECONSTRUCTION_EXECUTION_NOT_APPROVED')
    blender=Path(config.get('blenderExecutable',''))
    require(blender.is_absolute() and blender.is_file(),'RECONSTRUCTION_BLENDER_UNAVAILABLE')
    return blender

def render(root,run,spec,values,config,label,scope,beauty=False,export=False):
    blender=permission(config);folder=scope(root,run/label,False)
    require(not folder.exists(),'RECONSTRUCTION_EXISTING_EXPERIMENT');folder.mkdir()
    job={'source':str(run/'source.blend'),'output':str(folder),'spec':spec,'values':values,'beauty':beauty,'export':export}
    save(folder/'job.json',job)
    resources=scope(root,run/'blender-runtime',False);resources.mkdir(exist_ok=True)
    adapter=run/'runtime'/'part_adapter.py' if (run/'runtime'/'part_adapter.py').is_file() else Path(__file__).with_name('part_adapter.py')
    process=subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1',
        '--python',str(adapter),'--',str(folder/'job.json')],cwd=str(run),
        env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=100,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (folder/'blender-log.txt').write_bytes(process.stdout[-262144:])
    require(process.returncode==0 and b'NOETRA_PART_RENDER_COMPLETE' in process.stdout,'RECONSTRUCTION_PART_RENDER_FAILED')
    return folder

def masks(folder,view,parts):
    image=cv.imread(str(folder/(view['id']+'-ids.png')),cv.IMREAD_UNCHANGED)
    require(image is not None and image.shape==(view['height'],view['width'],4),'RECONSTRUCTION_PART_RENDER_MISSING')
    rgb=image[:,:,:3][:,:,::-1].astype(np.int16);alpha=image[:,:,3]>127
    return {p['id']:(np.max(np.abs(rgb-palette(i)),axis=2)<16)&alpha for i,p in enumerate(parts)},alpha

def measure(folder,spec):
    result={}
    for view in spec['views']:
        rendered,_=masks(folder,view,spec['parts']);result[view['id']]={}
        reference=cv.imread(view['reference']);require(reference is not None,'RECONSTRUCTION_REFERENCE_MISSING')
        overlay=reference.copy();diag=math.hypot(view['width'],view['height'])
        for a in view['annotations']:
            target=np.zeros((view['height'],view['width']),np.uint8)
            cv.fillPoly(target,[np.rint(a['polygon']).astype(np.int32)],255);target=target>0;prediction=rendered[a['partId']]
            union=(target|prediction).sum();iou=float((target&prediction).sum()/union)
            distance=symmetric_distance(boundary(target),boundary(prediction))
            loss=(1-iou)+(distance['mean_px']/diag if distance else 1)
            result[view['id']][a['partId']]={'iou':iou,'boundary':distance,'loss':float(loss),
                'reference_pixels':int(target.sum()),'rendered_pixels':int(prediction.sum()),'observation':view['id']+'/'+a['partId']}
            overlay[boundary(target)]=(0,255,0);overlay[boundary(prediction)]=(255,0,255)
        cv.imwrite(str(folder/(view['id']+'-overlay.png')),overlay)
    save(folder/'measurements.json',result);return result

def part_loss(measurements,part):
    values=[p[part]['loss'] for p in measurements.values() if part in p]
    require(bool(values),'RECONSTRUCTION_UNOBSERVED_PART');return sum(values)/len(values)

def gate(before,after,old_fingerprint,new_fingerprint,allowed,spec,part,mask_pairs=None):
    """Gate is shared by experiments/tests. Missing evidence never counts as success."""
    reasons=[];old=old_fingerprint['objects'];new=new_fingerprint['objects']
    if set(old)!=set(new):reasons.append('object_set_changed')
    changed=[name for name in old if name not in new or old[name]!=new[name]]
    if set(changed)-set(allowed):reasons.append('protected_object_changed')
    for key in ['world','frame','active_camera']:
        if old_fingerprint[key]!=new_fingerprint[key]:reasons.append('protected_scene_changed')
    if set(before)!=set(after):reasons.append('view_set_changed')
    target_views=0
    for view,parts in before.items():
        for identifier,prior in parts.items():
            now=after.get(view,{}).get(identifier)
            if not now:reasons.append('missing_measurement');continue
            if identifier==part:target_views+=1
            if now['loss']>prior['loss']+1e-8 or now['iou']<prior['iou']-1e-8:reasons.append('part_view_regressed')
            if prior['boundary'] and (not now['boundary'] or now['boundary']['mean_px']>prior['boundary']['mean_px']+1e-8):reasons.append('part_boundary_regressed')
    if not target_views:reasons.append('missing_target_observation')
    else:
        gain=part_loss(before,part)-part_loss(after,part)
        if gain<spec['minimumLossImprovement']:reasons.append('insufficient_measured_improvement')
    pixel_changes={}
    if mask_pairs is not None:
        for view,bm,ba,am,aa in mask_pairs:
            # Allow local overlap at the target's observed/baseline location.
            # Candidate geometry cannot enlarge its own permitted influence area.
            region=bm[part].copy()
            for a in view['annotations']:
                if a['partId']==part:
                    polygon=np.zeros(region.shape,np.uint8);cv.fillPoly(polygon,[np.rint(a['polygon']).astype(np.int32)],1);region|=polygon>0
            pad=spec['influencePaddingPixels']
            if pad:region=cv.dilate(region.astype(np.uint8),np.ones((2*pad+1,2*pad+1),np.uint8))>0
            changed_pixels=(ba!=aa)
            for identifier in bm:
                if identifier!=part:changed_pixels|=bm[identifier]!=am[identifier]
            count=int((changed_pixels&~region).sum());pixel_changes[view['id']]=count
            if count:reasons.append('protected_visibility_changed_outside_target_region')
    return {'accepted':not reasons,'reasons':sorted(set(reasons)),'changedObjects':changed,'protectedPixelChanges':pixel_changes}

def artifacts(run,report):
    # Only immutable inputs/checkpoints/render evidence, never runtime caches.
    names=['source.blend','correction-spec.json']
    if report.get('runtimeSnapshot'):names.extend('runtime/'+n for n in report['runtimeDigests'])
    for stage in report['stages']:
        names.extend(p.relative_to(run).as_posix() for p in (run/stage['folder']).iterdir() if p.is_file())
    report['artifactDigests']={name:sha(run/name) for name in names}

def summary(run,report):
    best=next(s for s in report['stages'] if s['folder']==report['best'])
    history=[]
    for e in report['history'][-12:]:
        item={k:e[k] for k in ['parameter','targetPart','checkpoint','beforeValue','proposedValue','accepted','reasons','folder','protectedPixelChanges','predictionFile'] if k in e}
        changes=e.get('changedObjects',[]);item['changedObjectCount']=e.get('changedObjectCount',len(changes));item['changedObjects']=changes[:16]
        history.append(item)
    return {'runId':run.name,'kind':report['kind'],'bestCheckpoint':str(run/report['best']/'scene.blend'),'bestGLB':str(run/report['best']/'scene.glb'),
        'bestValues':report['bestValues'],'initialMeasurements':report['stages'][0]['measurements'],'bestMeasurements':best['measurements'],
        'accepted':sum(1 for e in report['history'] if e.get('accepted')),'rejected':sum(1 for e in report['history'] if not e.get('accepted')),
        'history':history,'historyCount':len(report['history']),'report':str(run/'report.json'),'unknowns':report['unknowns']}

def prepare(root,payload,config,helpers):
    scope,new_run,image_record=helpers;permission(config);validate_spec(payload)
    source=scope(root,payload['blend']);require(source.suffix.lower()=='.blend' and source.is_file() and source.stat().st_size<=256*1024*1024,'RECONSTRUCTION_BLEND_FORMAT')
    run=new_run(root);before=sha(source);shutil.copyfile(source,run/'source.blend')
    require(sha(source)==before and sha(run/'source.blend')==before,'RECONSTRUCTION_SCENE_CHANGED')
    spec=json.loads(json.dumps(payload));images=[]
    for i,view in enumerate(spec['views']):
        record,_=image_record(root,view['reference'],run,i);images.append(record)
        require(record['metadata']['exifOrientation']==1,'RECONSTRUCTION_ORIENTATION_UNSUPPORTED')
        require(record['width']*record['height']<=4_000_000,'RECONSTRUCTION_CORRECTION_IMAGE_LIMIT')
        view['width']=record['width'];view['height']=record['height'];view['reference']=record['preserved']
        for annotation in view['annotations']:
            require(all(0<=x<view['width'] and 0<=y<view['height'] for x,y in annotation['polygon']),'RECONSTRUCTION_POLYGON_OUTSIDE_IMAGE')
    save(run/'correction-spec.json',spec)
    runtime=scope(root,run/'runtime',False);runtime.mkdir()
    for name in ['part_correction.py','part_adapter.py','geometry.py']:shutil.copyfile(Path(__file__).with_name(name),runtime/name)
    values={p['id']:0. for p in spec['parameters']}
    folder=render(root,run,spec,values,config,'initial',scope,beauty=True,export=True)
    measurements=measure(folder,spec)
    report={'runId':run.name,'kind':'part-correction','images':images,'sceneSource':str(source),'sceneSha256':before,
        'runtimeSnapshot':True,'runtimeDigests':{n:sha(runtime/n) for n in ['part_correction.py','part_adapter.py','geometry.py']},
        'stages':[{'folder':'initial','values':values,'measurements':measurements}],
        'best':'initial','bestValues':values,'steps':{p['id']:p['step'] for p in spec['parameters']},'history':[],
        'unknowns':['Part polygons and editable controls are attributed inputs, not automatically detected semantic/physical parts.',
          'Observed mask/boundary fit does not establish exact hidden geometry or metric scale.',
          'Flat part-ID masks treat glass as opaque and do not evaluate intrinsic materials, reflections, normals or internal unannotated details.',
          'Existing supported Blender scene required; this corrector does not infer an initial mesh from arbitrary images.',
          'Bounded coordinate search may stop at a local optimum; undeclared topology or new parts are not invented.',
          'Fresh disabled-autoexec Blender process is not an OS sandbox; only trusted project scenes are supported.']}
    artifacts(run,report);save(run/'report.json',report);return summary(run,report)

def correct(root,run,report,payload,config,scope):
    permission(config);require(report['kind']=='part-correction','RECONSTRUCTION_RUN_KIND');check_sources(root,run,report,scope)
    require(sha(Path(__file__))==report['runtimeDigests']['part_correction.py'],'RECONSTRUCTION_CORRECTION_VERSION_MIGRATION_REQUIRED')
    lock=run/'correction.lock'
    try:handle=lock.open('x')
    except FileExistsError:raise ValueError('RECONSTRUCTION_RUN_BUSY')
    try:
        handle.close();require(read(run/'report.json')==report,'RECONSTRUCTION_RUN_STALE')
        spec=read(run/'correction-spec.json');validate_spec(spec)
        require(len(report['history'])+payload['maxCandidates']<=48,'RECONSTRUCTION_CORRECTION_BUDGET')
        start=time.monotonic();attempts=0;tested=set()
        while attempts<payload['maxCandidates'] and time.monotonic()-start<240:
            best_stage=next(s for s in report['stages'] if s['folder']==report['best'])
            params=sorted(spec['parameters'],key=lambda p:part_loss(best_stage['measurements'],p['partId']),reverse=True)
            experiment=None
            for p in params:
                current=report['bestValues'][p['id']];step=report['steps'][p['id']]
                for direction in [-1,1]:
                    value=float(round(current+direction*step,12))
                    values={**report['bestValues'],p['id']:value};key=json.dumps(values,sort_keys=True)
                    if p['minimum']<=value<=p['maximum'] and key not in tested and not any(s['values']==values for s in report['stages']):
                        experiment=(p,values,key);break
                if experiment:break
                report['steps'][p['id']]=step/2
            if not experiment:break
            p,values,key=experiment;tested.add(key);attempts+=1
            label='trial-'+str(len(report['history'])+1)+'-'+uuid.uuid4().hex[:8]
            prediction={'parameter':p['id'],'targetPart':p['partId'],'checkpoint':report['best'],
                'beforeValue':report['bestValues'][p['id']],'proposedValue':values[p['id']],
                'mismatch':best_stage['measurements'],'prediction':'A bounded change may reduce the target polygon boundary/coverage mismatch; only actual renders can support acceptance.',
                'allowedObjects':next(x['objects'] for x in spec['parts'] if x['id']==p['partId']) if p['kind']=='translate' else [p['object']]}
            # Record the prediction before executing, including the accepted checkpoint.
            save(run/(label+'-prediction.json'),prediction)
            try:
                folder=render(root,run,spec,values,config,label,scope,beauty=True,export=True)
                after=measure(folder,spec);before_folder=run/report['best']
                pairs=[]
                for view in spec['views']:
                    bm,ba=masks(before_folder,view,spec['parts']);am,aa=masks(folder,view,spec['parts']);pairs.append((view,bm,ba,am,aa))
                decision=gate(best_stage['measurements'],after,read(before_folder/'fingerprints.json'),read(folder/'fingerprints.json'),
                    prediction['allowedObjects'],spec,p['partId'],pairs)
                report['stages'].append({'folder':label,'values':values,'measurements':after})
                if decision['accepted']:report['best']=label;report['bestValues']=values
                entry={**prediction,**decision,'folder':label,'measurements':after}
            except (ValueError,subprocess.TimeoutExpired) as error:
                entry={**prediction,'accepted':False,'folder':label,'reasons':['render_or_measurement_failed'],'details':str(error) if isinstance(error,ValueError) else 'render_timeout'}
            # Dense/per-view details and full allowed-object lists remain in
            # immutable trial files, not repeated in an unbounded MCP response.
            save(run/(label+'-decision.json'),entry)
            changes=entry.get('changedObjects',[])
            compact={k:entry[k] for k in ['parameter','targetPart','checkpoint','beforeValue','proposedValue','accepted','reasons','folder','protectedPixelChanges'] if k in entry}
            compact.update({'changedObjectCount':len(changes),'changedObjects':changes[:16],'predictionFile':str(run/(label+'-prediction.json')),'decisionFile':str(run/(label+'-decision.json'))})
            report['history'].append(compact)
            report['artifactDigests'][label+'-prediction.json']=sha(run/(label+'-prediction.json'))
            report['artifactDigests'][label+'-decision.json']=sha(run/(label+'-decision.json'))
            predictions={n:d for n,d in report['artifactDigests'].items() if n.endswith(('-prediction.json','-decision.json'))}
            artifacts(run,report);report['artifactDigests'].update(predictions);save(run/'report.json',report)
        return summary(run,report)
    finally:lock.unlink(missing_ok=True)

def inspect(root,run,report,scope):
    require(report['kind']=='part-correction','RECONSTRUCTION_RUN_KIND');check_sources(root,run,report,scope)
    return summary(run,report)
