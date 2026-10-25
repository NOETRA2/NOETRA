"""Reference radiance transfer with explicit approximate orthographic alignment."""
import numpy as np

def basis(direction,up):
    toward=np.asarray(direction,float);toward/=np.linalg.norm(toward)
    vertical=np.asarray(up,float);vertical-=toward*np.dot(vertical,toward);vertical/=np.linalg.norm(vertical)
    right=np.cross(vertical,toward)
    if not np.isfinite([toward,vertical,right]).all():raise ValueError('RECONSTRUCTION_COLOR_CAMERA')
    return toward,vertical,right

def foreground(rgb,alpha=None):
    if alpha is not None and alpha.min()<128:return alpha>192
    return np.max(255-rgb.astype(float),axis=2)>24

def coordinates(points,direction,up,mask):
    toward,vertical,right=basis(direction,up);p=np.asarray(points,float)
    xy=np.column_stack([p@right,-p@vertical]);low=xy.min(0);high=xy.max(0)
    yy,xx=np.where(mask)
    if len(xx)<100:raise ValueError('RECONSTRUCTION_COLOR_FOREGROUND')
    target_low=np.array([xx.min(),yy.min()]);target_high=np.array([xx.max(),yy.max()])
    scale=float(np.min((target_high-target_low)/np.maximum(high-low,1e-9)))
    shift=(target_low+target_high)/2-(low+high)/2*scale
    # Standing views align paw bottoms, overhead/underneath views stay centred.
    if abs(toward[2])<.5:shift[1]=target_high[1]-high[1]*scale
    return xy*scale+shift,{'scalePixelsPerUnit':scale,'translationPixels':shift.tolist(),'sourceMaskBBox':[target_low.tolist(),target_high.tolist()],
        'scope':'Approximate orthographic bounding-silhouette alignment, not recovered camera calibration.'}

def sample(rgb,mask,uv):
    h,w=mask.shape;xy=np.rint(uv).astype(int);valid=(xy[:,0]>=0)&(xy[:,0]<w)&(xy[:,1]>=0)&(xy[:,1]<h)
    selected=np.flatnonzero(valid);valid[selected]&=mask[xy[selected,1],xy[selected,0]]
    colors=np.zeros((len(uv),3),float);selected=np.flatnonzero(valid);colors[selected]=rgb[xy[selected,1],xy[selected,0]]/255.
    # Convert observed sRGB to linear vertex colors; Blender/glTF expect linear.
    colors=np.where(colors<=.04045,colors/12.92,((colors+.055)/1.055)**2.4)
    return colors,valid

def warp_coordinates(uv,controls,image_size):
    """Attributed 2D landmark correction of sampling coordinates, never geometry."""
    if not controls:return np.asarray(uv,float).copy(),{'status':'no-controls'}
    source=np.asarray([c['modelPixel'] for c in controls],float);target=np.asarray([c['referencePixel'] for c in controls],float)
    if source.shape!=target.shape or source.ndim!=2 or source.shape[1]!=2 or len(source)<3 or not np.isfinite([source,target]).all():raise ValueError('RECONSTRUCTION_COLOR_CONTROLS')
    if len(np.unique(source,axis=0))!=len(source) or np.linalg.matrix_rank(source-source.mean(0))<2:raise ValueError('RECONSTRUCTION_COLOR_CONTROLS')
    scale=float(max(image_size));s=source/scale;t=target/scale
    # Image corners pin the outer frame. Thin-plate RBF gives smooth local
    # residuals while explicit controls anchor facial/paw sampling positions.
    w,h=image_size;corners=np.array([[0,0],[w-1,0],[0,h-1],[w-1,h-1]],float)/scale
    anchors=np.concatenate([s,corners]);delta=np.concatenate([t-s,np.zeros((4,2))])
    def kernel(q):
        distance=np.linalg.norm(q[:,None,:]-anchors[None,:,:],axis=2)
        return distance**2*np.log(np.maximum(distance,1e-15))
    affine=np.column_stack([np.ones(len(anchors)),anchors]);count=len(anchors)
    system=np.block([[kernel(anchors),affine],[affine.T,np.zeros((3,3))]])
    try:coefficients=np.linalg.solve(system,np.vstack([delta,np.zeros((3,2))]))
    except np.linalg.LinAlgError:raise ValueError('RECONSTRUCTION_COLOR_CONTROLS')
    def transform(q):return kernel(q)@coefficients[:count]+np.column_stack([np.ones(len(q)),q])@coefficients[count:]
    values=np.asarray(uv,float);warped=values.copy()
    for start in range(0,len(values),32768):warped[start:start+32768]+=transform(values[start:start+32768]/scale)*scale
    error=np.linalg.norm((s+transform(s)-t)*scale,axis=1)
    if not np.isfinite(warped).all():raise ValueError('RECONSTRUCTION_COLOR_WARP')
    return warped,{'controlCount':len(source),'maximumControlResidualPx':float(error.max()),'maximumSamplingShiftPx':float(np.linalg.norm(warped-values,axis=1).max()),'geometryMoved':False,'scope':'Authored 2D sampling landmarks, not measured camera registration.'}

def region_weights(points,region):
    if region is None:return np.ones(len(points))
    center=np.asarray(region['center'],float);radii=np.asarray(region['radii'],float)
    if center.shape!=(3,) or radii.shape!=(3,) or not np.isfinite([center,radii]).all() or (radii<=0).any():raise ValueError('RECONSTRUCTION_COLOR_REGION')
    normalized=(np.asarray(points)-center)/radii
    shape=region.get('shape','ellipsoid')
    if shape not in ['ellipsoid','box']:raise ValueError('RECONSTRUCTION_COLOR_REGION_SHAPE')
    distance=np.max(np.abs(normalized),axis=1) if shape=='box' else np.linalg.norm(normalized,axis=1)
    feather=region.get('feather',.2)
    value=np.clip((1-distance)/feather,0,1)
    return value*value*(3-2*value)
