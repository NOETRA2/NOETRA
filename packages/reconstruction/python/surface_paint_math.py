"""Reusable, geometry-independent surface masks and scene-linear paint fields."""
import numpy as np
from reference_colors import region_weights

def linear(rgb):
    a=np.asarray(rgb,float)
    return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)

def paint_fields(points,design,weight_overrides=None):
    points=np.asarray(points,float)
    colors=np.tile(linear(design['baseSRGB']),(len(points),1))
    rough=np.full(len(points),design['baseRoughness']);flow=np.zeros(len(points));layers=[]
    for layer in design['layers']:
        weights=(weight_overrides[layer['id']] if weight_overrides and layer['id'] in weight_overrides else region_weights(points,layer['region']))*layer.get('opacity',1)
        target=np.tile(linear(layer['colorSRGB']),(len(points),1))
        if layer.get('gradient'):
            g=layer['gradient'];span=g['maximum']-g['minimum']
            if span<=0:raise ValueError('SURFACE_PAINT_GRADIENT_RANGE')
            t=np.clip((points[:,'XYZ'.index(g['axis'])]-g['minimum'])/span,0,1)
            target=target*(1-t[:,None])+linear(g['colorSRGB'])*t[:,None]
        colors=colors*(1-weights[:,None])+target*weights[:,None]
        rough=rough*(1-weights)+layer['roughness']*weights
        flow=flow*(1-weights)+layer.get('verticalFiber',0)*weights
        layers.append({'id':layer['id'],'affectedVertices':int((weights>0).sum()),'region':layer['region'],'provenance':layer['provenance']})
    return colors,rough,flow,layers

