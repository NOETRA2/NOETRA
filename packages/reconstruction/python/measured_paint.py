"""Measured palette to an existing authored layout; strictly an unverified preview.

This operation never asserts that colour clusters discovered anatomical parts.
It does not lift the automatic design gate, load a photograph into a shader,
execute supplied code or change existing model/source artifacts.
"""
from pathlib import Path
import copy,hashlib,json
import cv2 as cv
import numpy as np
from geometry import require

def vector(value,length,minimum,maximum):
    require(isinstance(value,list) and len(value)==length,'RECONSTRUCTION_LAYOUT_VECTOR')
    a=np.asarray(value,float);require(np.isfinite(a).all() and (a>=minimum).all() and (a<=maximum).all(),'RECONSTRUCTION_LAYOUT_RANGE');return a

def checked_layout(value):
    require(isinstance(value,dict) and set(value)<=set(['baseSRGB','baseRoughness','resolution','layers','provenance']),'RECONSTRUCTION_LAYOUT_FIELDS')
    vector(value.get('baseSRGB'),3,0,1)
    require(value.get('resolution',2048) in [1024,2048] and .05<=value.get('baseRoughness',0)<=1,'RECONSTRUCTION_LAYOUT_RANGE')
    require(isinstance(value.get('provenance'),str) and 0<len(value['provenance'])<=2000,'RECONSTRUCTION_LAYOUT_PROVENANCE')
    layers=value.get('layers');require(isinstance(layers,list) and 1<=len(layers)<=32,'RECONSTRUCTION_LAYOUT_LAYERS')
    for layer in layers:
        require(isinstance(layer,dict) and set(layer)<=set(['id','region','colorSRGB','roughness','opacity','verticalFiber','gradient','provenance']),'RECONSTRUCTION_LAYOUT_FIELDS')
        require(isinstance(layer.get('id'),str) and 1<=len(layer['id'])<=64 and isinstance(layer.get('provenance'),str),'RECONSTRUCTION_LAYOUT_PROVENANCE')
        vector(layer.get('colorSRGB'),3,0,1)
        require(.05<=layer.get('roughness',0)<=1 and 0<=layer.get('opacity',1)<=1 and 0<=layer.get('verticalFiber',0)<=1,'RECONSTRUCTION_LAYOUT_RANGE')
        region=layer.get('region');require(isinstance(region,dict) and set(region)<=set(['shape','center','radii','feather','provenance']),'RECONSTRUCTION_LAYOUT_REGION')
        vector(region.get('center'),3,-1000,1000);r=vector(region.get('radii'),3,0,100);require((r>0).all(),'RECONSTRUCTION_LAYOUT_RANGE')
        require(region.get('shape','ellipsoid') in ['ellipsoid','box'] and .01<=region.get('feather',.2)<=.5,'RECONSTRUCTION_LAYOUT_REGION')
        if layer.get('gradient'):
            g=layer['gradient'];require(set(g)<=set(['axis','minimum','maximum','colorSRGB']) and g.get('axis') in ['X','Y','Z'] and -1000<=g.get('minimum',1001)<g.get('maximum',-1001)<=1000,'RECONSTRUCTION_LAYOUT_GRADIENT');vector(g.get('colorSRGB'),3,0,1)
    return copy.deepcopy(value)

def derive_design(layout,palette):
    design=checked_layout(layout)
    require(isinstance(palette,list) and 3<=len(palette)<=12,'RECONSTRUCTION_MEASURED_PALETTE')
    colors=np.asarray([vector(p['observedSRGB8'],3,0,255) for p in palette],np.float32)/255
    lab=cv.cvtColor(colors.reshape(-1,1,3),cv.COLOR_RGB2LAB).reshape(-1,3);assignments=[]
    def measured(seed,part):
        sample=cv.cvtColor(np.asarray(seed,np.float32).reshape(1,1,3),cv.COLOR_RGB2LAB).reshape(3)
        distance=np.linalg.norm(lab-sample,axis=1);i=int(distance.argmin())
        assignments.append({'layoutField':part,'sourceFamily':palette[i]['family'],'sourceHex':palette[i]['hex'],'sourceSRGB8':palette[i]['observedSRGB8'],
          'selection':'Nearest measured Lab swatch to the existing authored layout colour; part placement not inferred','deltaE76FromPreviousChoice':float(distance[i])})
        return colors[i].astype(float).tolist()
    design['baseSRGB']=measured(design['baseSRGB'],'base')
    for layer in design['layers']:
        layer['colorSRGB']=measured(layer['colorSRGB'],layer['id'])
        if layer.get('gradient'):layer['gradient']['colorSRGB']=measured(layer['gradient']['colorSRGB'],layer['id']+'-gradient')
    design['provenance']='MEASURED COLOUR PREVIEW. Every palette endpoint comes from actual reference pixels. Existing authored spatial masks are provisional, not automatically verified anatomical segmentation. Roughness/fibre parameters remain authored hypotheses.'
    return design,assignments

def preview(root,payload,config,helpers):
    scope,new_run,image_record,load_run,read_json=helpers
    require(payload['mode']=='unverified-preview','RECONSTRUCTION_MEASURED_PREVIEW_ONLY')
    analysis,report=load_run(root,payload['analysisRunId']);source,mesh_report=load_run(root,payload['meshRunId'])
    require(report.get('kind')=='automatic-reference-appearance-analysis' and report['designGate']['automaticTexturingAllowed'] is False,'RECONSTRUCTION_APPEARANCE_ANALYSIS_REQUIRED')
    path=scope(root,payload['layout']);require(path.is_file() and path.suffix.lower()=='.json' and path.stat().st_size<65536,'RECONSTRUCTION_LAYOUT_FILE')
    digest=hashlib.sha256(path.read_bytes()).hexdigest();layout=read_json(path)
    design,assignments=derive_design(layout,report['views'][0]['palette'])
    evidence={'mode':'unverified-preview','analysisRun':analysis.name,'analysisReportSha256':hashlib.sha256((analysis/'report.json').read_bytes()).hexdigest(),
      'layout':{'source':str(path),'sha256':digest,'provenance':'Previously authored region layout; reused explicitly, not inferred by colour clustering.'},
      'sourcePaletteImage':report['images'][0]['id'],'assignments':assignments,'analysisReadinessUnchanged':report['designGate'],
      'photographProjected':False,'roughnessMeasured':False,'anatomicalPlacementVerified':False,'promotedToAcceptedModel':False}
    from material_paint import paint
    result=paint(root,source,mesh_report,{'references':[r['source'] for r in report['images']],'design':design,'_measuredPreview':evidence},config,(scope,new_run,image_record))
    require(hashlib.sha256(path.read_bytes()).hexdigest()==digest,'RECONSTRUCTION_LAYOUT_CHANGED')
    return result
