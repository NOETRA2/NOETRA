"""Geometry-only image matching and bounded local part-control proposals."""
import numpy as np
from scipy.optimize import lsq_linear
from geometry import require,boundary,symmetric_distance

def measure_shape(observed_mask,rendered_mask,observed_keypoints=None,rendered_keypoints=None):
    target=np.asarray(observed_mask);prediction=np.asarray(rendered_mask)
    require(target.ndim==2 and target.shape==prediction.shape and target.size<=8_000_000,'RECONSTRUCTION_MATCH_MASK')
    require(np.isfinite(target).all() and np.isfinite(prediction).all() and np.isin(target,[0,1,255]).all() and np.isin(prediction,[0,1,255]).all(),'RECONSTRUCTION_MATCH_MASK')
    target=target.astype(bool);prediction=prediction.astype(bool);require(target.any(),'RECONSTRUCTION_MATCH_EMPTY_TARGET')
    union=(target|prediction).sum();iou=float((target&prediction).sum()/max(1,union))
    # Explicit empty background outside the image preserves edges of masks that
    # touch the image border, including a full-frame foreground region.
    target_edge=boundary(np.pad(target,1))[1:-1,1:-1];prediction_edge=boundary(np.pad(prediction,1))[1:-1,1:-1]
    edge_error=symmetric_distance(target_edge,prediction_edge) if prediction.any() else {'mean_px':float(max(target.shape)),'p95_px':float(max(target.shape))}
    result={'silhouetteIoU':iou,'boundaryMeanPx':edge_error['mean_px'],'boundaryP95Px':edge_error['p95_px'],'keypointRmsePx':None,
        'scope':'Actual geometry masks and named projected landmarks only; texture and appearance do not contribute.'}
    if observed_keypoints is not None or rendered_keypoints is not None:
        require(isinstance(observed_keypoints,dict) and isinstance(rendered_keypoints,dict) and 0<len(observed_keypoints)<=256 and set(observed_keypoints)==set(rendered_keypoints),'RECONSTRUCTION_MATCH_KEYPOINT_IDS')
        a=np.asarray([observed_keypoints[k] for k in sorted(observed_keypoints)],float);b=np.asarray([rendered_keypoints[k] for k in sorted(observed_keypoints)],float)
        require(a.shape==b.shape==(len(observed_keypoints),2) and np.isfinite(a).all() and np.isfinite(b).all(),'RECONSTRUCTION_MATCH_KEYPOINTS')
        result['keypointRmsePx']=float(np.sqrt(np.mean(np.sum((a-b)**2,axis=1))))
    return result

def propose_part_parameters(parameters,residual,jacobian,locked_parts=(),uncertainty=None):
    """Solve a bounded local linearization from real render finite differences.

    residual is predicted minus observed; Jacobian columns follow parameter IDs.
    This returns a proposal only. The caller must render it and run the gate.
    """
    require(isinstance(parameters,list) and 1<=len(parameters)<=64,'RECONSTRUCTION_MATCH_PARAMETER_LIMIT')
    r=np.asarray(residual,float);J=np.asarray(jacobian,float)
    require(r.ndim==1 and 1<=len(r)<=8192 and J.shape==(len(r),len(parameters)) and np.isfinite(r).all() and np.isfinite(J).all(),'RECONSTRUCTION_MATCH_LINEARIZATION')
    ids=set();active=[];lower=[];upper=[];deltas=np.zeros(len(parameters))
    for i,p in enumerate(parameters):
        require(isinstance(p,dict) and set(p)=={'id','partId','value','minimum','maximum','maxStep'},'RECONSTRUCTION_MATCH_PARAMETER_FIELDS')
        require(isinstance(p['id'],str) and 0<len(p['id'])<=64 and p['id'] not in ids and isinstance(p['partId'],str),'RECONSTRUCTION_MATCH_PARAMETER_IDS');ids.add(p['id'])
        require(all(isinstance(p[k],(int,float)) and not isinstance(p[k],bool) for k in ['value','minimum','maximum','maxStep']),'RECONSTRUCTION_MATCH_PARAMETER_BOUNDS')
        values=np.asarray([p[k] for k in ['value','minimum','maximum','maxStep']],float)
        require(np.isfinite(values).all() and p['minimum']<=p['value']<=p['maximum'] and p['minimum']<p['maximum'] and 0<p['maxStep']<=p['maximum']-p['minimum'],'RECONSTRUCTION_MATCH_PARAMETER_BOUNDS')
        if p['partId'] in locked_parts:continue
        lo=max(p['minimum']-p['value'],-p['maxStep']);hi=min(p['maximum']-p['value'],p['maxStep'])
        if lo<hi:active.append(i);lower.append(lo);upper.append(hi)
    weights=np.ones(len(r))
    if uncertainty is not None:
        sigma=np.asarray(uncertainty,float);require(sigma.shape==r.shape and np.isfinite(sigma).all() and (sigma>0).all(),'RECONSTRUCTION_MATCH_UNCERTAINTY');weights=1/np.maximum(sigma,1e-6)
    require(active,'RECONSTRUCTION_MATCH_NO_EDITABLE_PARAMETERS')
    fit=lsq_linear(J[:,active]*weights[:,None],-r*weights,bounds=(lower,upper),max_iter=100,tol=1e-8)
    require(fit.success and np.isfinite(fit.x).all(),'RECONSTRUCTION_MATCH_PROPOSAL_FAILED');deltas[active]=fit.x
    return {'parameters':[{'id':p['id'],'partId':p['partId'],'before':p['value'],'delta':float(d),'proposed':float(p['value']+d)} for p,d in zip(parameters,deltas)],
        'weightedResidualBefore':float(np.linalg.norm(r*weights)),'predictedWeightedResidualAfter':float(np.linalg.norm((r+J@deltas)*weights)),
        'requiresActualRender':True,'scope':'Bounded linearized part-control proposal; no camera edit, topology change, inferred part discovery or claim of measured hidden shape.'}

def correction_gate(before,after,before_fingerprints,after_fingerprints,editable_parts,heldout_views=()):
    """Accept real rendered improvement while preserving cameras/locked geometry.

    before/after: view ID -> {origin, role, parts: part ID -> measure_shape result}.
    Fingerprints: {cameras: {id: hash}, parts: {partId: hash}}. Callers derive
    fingerprints from actual scene geometry/cameras, never texture images.
    """
    reasons=[]
    require(set(before_fingerprints)==set(after_fingerprints)=={'cameras','parts'},'RECONSTRUCTION_MATCH_FINGERPRINTS')
    require(before and before_fingerprints['cameras'] and before_fingerprints['parts'] and set(before)<=set(before_fingerprints['cameras']) and set(editable_parts)<=set(before_fingerprints['parts']),'RECONSTRUCTION_MATCH_FINGERPRINTS')
    if before_fingerprints['cameras']!=after_fingerprints['cameras']:reasons.append('camera_changed')
    if set(before_fingerprints['parts'])!=set(after_fingerprints['parts']):reasons.append('part_set_changed')
    for pid,digest in before_fingerprints['parts'].items():
        if pid not in editable_parts and after_fingerprints['parts'].get(pid)!=digest:reasons.append('locked_part_changed:'+pid)
    if set(before)!=set(after):reasons.append('view_set_changed')
    improved=False;validated=set();fit_origins=set()
    for vid,old in before.items():
        new=after.get(vid)
        if new is None:continue
        if old.get('origin')!=new.get('origin') or old.get('role')!=new.get('role'):reasons.append('view_provenance_changed:'+vid);continue
        if old.get('origin') not in ['actual_photo','reference_artwork']:
            if old.get('role')!='inspection' or vid in heldout_views:reasons.append('hypothesis_used_as_validation:'+vid)
            continue
        if old.get('origin')=='reference_artwork' and (old.get('role')=='heldout' or vid in heldout_views):
            reasons.append('artwork_used_as_independent_validation:'+vid);continue
        if old.get('role')=='fit':fit_origins.add(old.get('origin'))
        if set(old['parts'])!=set(new['parts']):reasons.append('observation_set_changed:'+vid);continue
        if vid in heldout_views:
            if old.get('role')!='heldout':reasons.append('heldout_role_required:'+vid)
            else:validated.add(vid)
        for pid,a in old['parts'].items():
            b=new['parts'][pid]
            keys=['silhouetteIoU','boundaryMeanPx','boundaryP95Px','keypointRmsePx']
            require(all(k in a and k in b for k in keys),'RECONSTRUCTION_MATCH_METRICS')
            require(all(a[k] is None and b[k] is None or a[k] is not None and b[k] is not None and np.isfinite([a[k],b[k]]).all() for k in keys),'RECONSTRUCTION_MATCH_METRICS')
            require(a['silhouetteIoU'] is not None and b['silhouetteIoU'] is not None and 0<=a['silhouetteIoU']<=1 and 0<=b['silhouetteIoU']<=1 and all(a[k] is not None and b[k] is not None and a[k]>=0 and b[k]>=0 for k in ['boundaryMeanPx','boundaryP95Px']),'RECONSTRUCTION_MATCH_METRICS')
            regression=b['silhouetteIoU']<a['silhouetteIoU']-.001 or b['boundaryMeanPx']>a['boundaryMeanPx']+.1 or b['boundaryP95Px']>a['boundaryP95Px']+.25
            if a['keypointRmsePx'] is not None:regression|=b['keypointRmsePx']>a['keypointRmsePx']+.1
            if regression:reasons.append('geometry_regression:'+vid+':'+pid)
            if old.get('role')=='fit' and pid in editable_parts:
                improved|=bool(b['silhouetteIoU']>a['silhouetteIoU']+.001 or b['boundaryMeanPx']<a['boundaryMeanPx']-.1 or (a['keypointRmsePx'] is not None and b['keypointRmsePx']<a['keypointRmsePx']-.1))
    if not improved:reasons.append('no_measured_fit_improvement')
    if set(heldout_views)!=validated:reasons.append('independent_heldout_validation_missing')
    validation_scope='heldout-actual-views' if validated else ('reference-artwork-only; hidden geometry unvalidated' if fit_origins=={'reference_artwork'} else 'source-view-only; hidden geometry unvalidated')
    return {'accepted':not reasons,'reasons':reasons,'independentHeldoutViews':sorted(validated),'validationScope':validation_scope}
