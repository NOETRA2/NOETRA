"""Automatic object-agnostic observed-appearance analysis, never photo painting.

No lion names, anatomical landmarks, hand-authored palette or paint polygons.
No network, new models, Blender operations or claimed physical depth recovery.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import cv2 as cv
from PIL import Image,ImageDraw,ImageFont
cv.setNumThreads(2)

def save(path,data):
    Path(path).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf8')

def estimate_foreground(rgb,alpha=None):
    if alpha is not None and alpha.size and alpha.min()<128:
        mask=alpha>192
        return mask,{'method':'source-alpha','status':'observed-matte','edgeUncertainty':'Translucent edge pixels excluded; alpha does not label anatomical parts.'}
    # White studio removal is restricted to connected border background. Dark
    # nostrils and enclosed pale muzzle pixels cannot become background by hue.
    pale=np.min(rgb,axis=2)>238
    border=np.concatenate([pale[0],pale[-1],pale[:,0],pale[:,-1]])
    if border.mean()<.75:
        return np.ones(rgb.shape[:2],bool),{'method':'unavailable','status':'ambiguous-background','edgeUncertainty':'No usable alpha or uniform white background; colour clusters can include scenery. Automatic application is blocked.'}
    count,labels=cv.connectedComponents(pale.astype(np.uint8),8)
    connected=np.unique(np.concatenate([labels[0],labels[-1],labels[:,0],labels[:,-1]]));connected=connected[connected!=0]
    mask=~np.isin(labels,connected)
    # Large enclosed white islands can be studio background between limbs.
    # Exclude them conservatively and report ambiguity rather than silently
    # turning a white air gap into a pale material family.
    island_sizes=np.bincount(labels.ravel());large=np.flatnonzero(island_sizes>=max(1024,int(mask.size*.0008)))
    large=large[(large!=0)&~np.isin(large,connected)]
    uncertain=int(np.isin(labels,large).sum());mask[np.isin(labels,large)]=False
    count,parts,stats,_=cv.connectedComponentsWithStats(mask.astype(np.uint8),8)
    if count>1:
        keep=np.flatnonzero(stats[:,cv.CC_STAT_AREA]>=max(20,mask.size*.00001));keep=keep[keep!=0]
        mask=np.isin(parts,keep)
    return mask,{'method':'connected-white-border','status':'estimated-matte','ambiguousEnclosedWhitePixelsExcluded':uncertain,'edgeUncertainty':'White-connected thin fur can be lost; large enclosed white islands are excluded as uncertain. This is a foreground estimate, not a verified silhouette.'}

def assign(samples,centers):
    labels=np.empty(len(samples),np.int16)
    for start in range(0,len(samples),32768):
        distance=np.sum((samples[start:start+32768,None,:]-centers[None,:,:])**2,axis=2)
        labels[start:start+32768]=distance.argmin(axis=1)
    return labels

def colour_families(rgb,mask,maximum):
    pixels=rgb[mask];lab=cv.cvtColor(pixels.astype(np.float32).reshape(-1,1,3)/255,cv.COLOR_RGB2LAB).reshape(-1,3)
    sample=lab[np.linspace(0,len(lab)-1,min(20000,len(lab)),dtype=int)]
    centers=[sample[np.argmin(np.abs(sample[:,0]-np.median(sample[:,0])))]]
    for _ in range(maximum-1):
        distance=np.min(np.sum((sample[:,None,:]-np.asarray(centers)[None,:,:])**2,axis=2),axis=1)
        index=int(distance.argmax())
        if distance[index]<1e-6:break
        centers.append(sample[index])
    centers=np.asarray(centers)
    for _ in range(16):
        labels=assign(sample,centers)
        updated=np.asarray([np.median(sample[labels==i],axis=0) if (labels==i).any() else c for i,c in enumerate(centers)])
        if np.max(np.abs(updated-centers))<.01:centers=updated;break
        centers=updated
    centers=centers[np.argsort(centers[:,0],kind='stable')]
    labels=assign(lab,centers);palette=[]
    for i,center in enumerate(centers):
        selected=np.flatnonzero(labels==i)
        if not len(selected):continue
        values=lab[selected];medoid=selected[np.argmin(np.sum((values-center)**2,axis=1))]
        color=pixels[medoid].tolist();hexcolor='#'+''.join(f'{int(c):02X}' for c in color)
        palette.append({'family':i+1,'hex':hexcolor,'observedSRGB8':color,'medianLab':np.median(values,axis=0).tolist(),
            'lightnessP10P50P90':np.percentile(values[:,0],[10,50,90]).tolist(),'objectPixelShare':float(len(selected)/len(pixels)),
            'sampleIsActualSourcePixel':True,'materialIdentity':None,'intrinsicAlbedo':None})
    full=np.zeros(mask.shape,np.uint8);full[mask]=labels+1
    return full,palette

def analyze_pixels(rgb,alpha=None,families=8):
    if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8:raise ValueError('RECONSTRUCTION_APPEARANCE_RGB')
    mask,matte=estimate_foreground(rgb,alpha)
    if mask.sum()<64:raise ValueError('RECONSTRUCTION_APPEARANCE_FOREGROUND_EMPTY')
    labels,palette=colour_families(rgb,mask,families)
    lab=cv.cvtColor(rgb.astype(np.float32)/255,cv.COLOR_RGB2LAB)
    smooth=cv.GaussianBlur(lab,(0,0),1.5)
    gx=cv.Sobel(smooth,cv.CV_32F,1,0,ksize=3)/8;gy=cv.Sobel(smooth,cv.CV_32F,0,1,ksize=3)/8
    chroma=np.sqrt(np.sum(gx[:,:,1:]**2+gy[:,:,1:]**2,axis=2))
    luminance=np.sqrt(gx[:,:,0]**2+gy[:,:,0]**2)
    gray=cv.cvtColor(rgb,cv.COLOR_RGB2GRAY).astype(np.float32)/255
    tx=cv.Sobel(gray,cv.CV_32F,1,0,ksize=3);ty=cv.Sobel(gray,cv.CV_32F,0,1,ksize=3)
    jxx=cv.GaussianBlur(tx*tx,(0,0),2);jyy=cv.GaussianBlur(ty*ty,(0,0),2);jxy=cv.GaussianBlur(tx*ty,(0,0),2)
    direction=.5*np.arctan2(2*jxy,jxx-jyy)+np.pi/2
    coherence=np.sqrt((jxx-jyy)**2+4*jxy*jxy)/np.maximum(jxx+jyy,1e-9)
    # Suppress isolated fur speckles before spatial components. This deliberately
    # reports coarse colour regions, never pixel-perfect anatomical boundaries.
    coarse=cv.medianBlur(labels,5);coarse[~mask]=0
    components=np.zeros(mask.shape,np.uint16);regions=[];minimum=max(30,int(mask.sum()*.0004));next_id=1
    for family in range(1,len(palette)+1):
        count,cc,stats,_=cv.connectedComponentsWithStats((coarse==family).astype(np.uint8),8)
        ranked=sorted(range(1,count),key=lambda i:-int(stats[i,cv.CC_STAT_AREA]))
        for index in ranked[:32]:
            x,y,w,h,area=map(int,stats[index])
            if area<minimum or next_id>256:continue
            inside=cc[y:y+h,x:x+w]==index;components[y:y+h,x:x+w][inside]=next_id
            contours,hierarchy=cv.findContours(inside.astype(np.uint8),cv.RETR_CCOMP,cv.CHAIN_APPROX_SIMPLE)
            boundaries=[]
            for j,contour in enumerate(contours):
                if abs(cv.contourArea(contour))<3:continue
                poly=cv.approxPolyDP(contour,1.5,True).reshape(-1,2)+[x,y]
                if len(poly)>128:poly=poly[np.linspace(0,len(poly)-1,128,dtype=int)]
                boundaries.append({'isHole':bool(hierarchy[0,j,3]>=0),'pointsPx':poly.tolist()})
            d=direction[y:y+h,x:x+w][inside];c=coherence[y:y+h,x:x+w][inside]
            iy,ix=np.where(inside);closest=np.argmin((ix-w/2)**2+(iy-h/2)**2)
            stable=c>.35
            angle=None
            if stable.sum()>10:angle=float(np.degrees(np.arctan2(np.sin(2*d[stable]).mean(),np.cos(2*d[stable]).mean()))/2%180)
            regions.append({'regionId':next_id,'colourFamily':family,'areaPixels':area,'bboxPx':[x,y,x+w,y+h],
                'bboxNormalized':[x/rgb.shape[1],y/rgb.shape[0],(x+w)/rgb.shape[1],(y+h)/rgb.shape[0]],
                'boundaries':boundaries,'labelAnchorPx':[int(x+ix[closest]),int(y+iy[closest])],'partName':None,'semanticConfidence':0,
                'dominantTextureLineAngleDegrees':angle,'textureCoherenceMedian':float(np.median(c)),
                'depthMetres':None,'reliefClass':'unknown','boundaryMeaning':'Connected region of quantized observed colour; can split one anatomical part or merge different parts.'})
            next_id+=1
    interior=cv.erode(mask.astype(np.uint8),np.ones((5,5),np.uint8))>0
    transitions=[]
    a=coarse[:,:-1];b=coarse[:,1:];good=(a!=b)&(a>0)&(b>0)&interior[:,:-1]&interior[:,1:]
    for first,second in np.unique(np.sort(np.column_stack([a[good],b[good]]),axis=1),axis=0):
        selected=good&(((a==first)&(b==second))|((a==second)&(b==first)))
        yy,xx=np.where(selected)
        if len(xx)<8:continue
        indexes=np.linspace(0,len(xx)-1,min(128,len(xx)),dtype=int)
        transitions.append({'families':[int(first),int(second)],'horizontalAdjacencySamples':int(len(xx)),
            'samplePointsPx':np.column_stack([xx[indexes],yy[indexes]]).tolist(),
            'medianLocalLightnessGradientPerPixel':float(np.median(luminance[yy,xx])),
            'medianLocalChromaGradientPerPixel':float(np.median(chroma[yy,xx])),
            'materialBoundaryVerified':False,'physicalDepth':None})
    return {'mask':mask,'labels':labels,'components':components,'chromaGradient':chroma,'lightnessGradient':luminance,
      'direction':direction,'coherence':coherence,'matte':matte,'palette':palette,'regions':regions,'transitions':transitions}

def diagram(rgb,analysis,path):
    h,w=rgb.shape[:2];scale=min(1,1000/w);height=int(h*scale)
    source=Image.fromarray(rgb).resize((int(w*scale),height));quant=np.full_like(rgb,245)
    for p in analysis['palette']:quant[analysis['labels']==p['family']]=p['observedSRGB8']
    colors=Image.fromarray(quant).resize(source.size)
    canvas=Image.new('RGB',(source.width*2,height+118),'#17191C');canvas.paste(source,(0,42));canvas.paste(colors,(source.width,42))
    draw=ImageDraw.Draw(canvas);draw.text((14,12),'SOURCE IMAGE - untouched reference',fill='white');draw.text((source.width+14,12),'AUTOMATIC COLOUR FAMILIES - not a texture or part segmentation',fill='white')
    for r in analysis['regions']:
        if r['areaPixels']<analysis['mask'].sum()*.008:continue
        for c in r['boundaries']:
            if c['isHole']:continue
            points=[(int(x*scale)+source.width,int(y*scale)+42) for x,y in c['pointsPx']]
            if len(points)>2:draw.line(points+[points[0]],fill='#191919',width=1)
        x,y=r['labelAnchorPx'];draw.text((source.width+int(x*scale),42+int(y*scale)),str(r['regionId']),fill='#FFFFFF',stroke_width=1,stroke_fill='#111111')
    left=12
    for p in analysis['palette']:
        draw.rectangle((left,height+54,left+54,height+78),fill=tuple(p['observedSRGB8']))
        draw.text((left,height+83),f"{p['family']} {p['hex']}",fill='white');left+=112
    draw.text((12,height+104),'Measured sRGB radiance includes lighting. Depth and anatomical mapping remain unknown.',fill='#BEC3C8')
    canvas.save(path)

def analyze(root,payload,helpers):
    new_run,image_record=helpers;run=new_run(root);views=[];images=[]
    for index,path in enumerate(payload['images']):
        record,_=image_record(root,path,run,index);images.append(record)
        with np.load(record['rgbArray'],allow_pickle=False) as stored:rgb=stored['rgb'].copy();alpha=stored['alpha'].copy()
        data=analyze_pixels(rgb,alpha,payload['colourFamilies']);prefix=f'view-{index}'
        Image.fromarray(data['mask'].astype(np.uint8)*255).save(run/(prefix+'-foreground.png'))
        Image.fromarray(data['labels']).save(run/(prefix+'-colour-labels.png'))
        Image.fromarray(data['components']).save(run/(prefix+'-regions.png'))
        diagram(rgb,data,run/(prefix+'-analysis.png'))
        np.savez_compressed(run/(prefix+'-measurements.npz'),chromaGradient=data['chromaGradient'],lightnessGradient=data['lightnessGradient'],textureDirectionRadians=data['direction'],textureCoherence=data['coherence'])
        detail={'imageId':record['id'],'sourceSha256':record['sha256'],'size':record['metadata']['size'],'matte':data['matte'],
          'palette':data['palette'],'regions':data['regions'],'transitions':data['transitions'],'summaryDiagram':str(run/(prefix+'-analysis.png')),
          'anatomicalPartSegmentation':{'status':'unavailable','namesInferred':False},
          'depth':{'metric':None,'relative':None,'reason':'Colour/shading gradients alone cannot establish geometry, scale, light or material.'}}
        save(run/(prefix+'-analysis.json'),detail)
        views.append({'imageId':record['id'],'source':record['source'],'matte':data['matte'],'palette':data['palette'],'regionCount':len(data['regions']),
          'analysis':str(run/(prefix+'-analysis.json')),'diagram':str(run/(prefix+'-analysis.png'))})
    blockers=['ANATOMICAL_REGIONS_UNVERIFIED','SEMANTIC_TO_MESH_CORRESPONDENCE_MISSING','INTRINSIC_ALBEDO_AND_LIGHTING_UNSEPARATED','DEPTH_UNOBSERVED']
    if any(v['matte']['status']=='ambiguous-background' for v in views):blockers.append('FOREGROUND_AMBIGUOUS')
    gate={'automaticTexturingAllowed':False,'automaticGeometryDesignAllowed':False,'blockers':blockers,
      'requiredNextEvidence':['Verified anatomical region masks, not merely colour clusters.','Visibility-aware region-to-mesh correspondence and UV validation.','Consistent multi-view geometry/depth evidence or explicitly attributed modelling priors.'],
      'onFailure':'Preserve current model. Do not project photographs, invent part colours, or report completion.'}
    outputs={'analysis':str(run/'appearance-report.json'),'gate':str(run/'design-gate.json'),'diagrams':[v['diagram'] for v in views]}
    report={'runId':run.name,'kind':'automatic-reference-appearance-analysis','images':images,'views':views,'designGate':gate,'outputs':outputs,
      'algorithm':'Deterministic farthest-first Lab median clusters, connected spatial components, Sobel chroma/lightness gradients and local structure tensors. No object-specific templates or supplied paint masks.',
      'scope':'Observed image analysis only. Quantized regions are not anatomical parts; swatches are actual image pixels, not proposed paint colours. No mesh is read or changed.'}
    save(run/'appearance-report.json',report);save(run/'design-gate.json',gate)
    report['artifactDigests']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file()}
    save(run/'report.json',report)
    for record in images:
        if hashlib.sha256(Path(record['source']).read_bytes()).hexdigest()!=record['sha256']:raise ValueError('RECONSTRUCTION_SOURCE_CHANGED')
    return {k:report[k] for k in ['runId','kind','views','designGate','outputs','algorithm','scope']}
