import unittest,sys
from pathlib import Path
import numpy as np
import cv2 as cv
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from visual_hull import fuse_silhouettes

def fixture_views():
    result=[]
    for center in [[0,0,-3],[3,0,0],[0,3,0]]:
        center=np.asarray(center,float);z=-center/np.linalg.norm(center);reference=np.array([0.,1,0])
        if abs(reference@z)>.99:reference=np.array([0.,0,1])
        x=np.cross(reference,z);x/=np.linalg.norm(x);y=np.cross(z,x);R=np.stack([x,y,z]);t=-R@center
        mask=np.zeros((128,128),np.uint8);cv.circle(mask,(64,64),20,255,-1)
        result.append({'mask':mask,'K':[[100,0,64],[0,100,64],[0,0,1]],'R':R.tolist(),'t':t.tolist()})
    return result

def analytic_sphere_views():
    """Ray/sphere silhouettes from oblique cameras; no triangle mesh renderer."""
    views=[];sphere=np.array([.073,-.041,.029]);radius=.57;size=240;focal=210.
    directions=[[1,.3,.2],[-1,.4,-.1],[.2,1,.3],[-.2,-1,.4],[.3,.2,1],[-.4,.1,-1],
        [1,1,1],[-1,1,1],[1,-1,1],[1,1,-1],[-1,-1,1],[-1,1,-1],[1,-1,-1],[-1,-1,-1]]
    yy,xx=np.indices((size,size));rays=np.stack([(xx-size/2)/focal,(yy-size/2)/focal,np.ones_like(xx)],axis=-1)
    for direction in directions:
        camera=sphere+np.asarray(direction)/np.linalg.norm(direction)*3.2;z=(sphere-camera)/3.2
        x=np.cross([0,1,0],z);x/=np.linalg.norm(x);R=np.stack([x,np.cross(z,x),z]);t=-R@camera;c=R@sphere+t
        discriminant=np.einsum('...i,i->...',rays,c)**2-np.einsum('...i,...i->...',rays,rays)*(c@c-radius**2)
        views.append({'mask':discriminant>=0,'K':[[focal,0,size/2],[0,focal,size/2],[0,0,1]],'R':R,'t':t})
    return views,sphere,radius

def legacy_binary_hull(views,bounds,grid):
    """Regression baseline: former nearest-pixel occupancy extraction."""
    from skimage.measure import marching_cubes
    import trimesh
    lo=np.array(bounds['minimum']);hi=np.array(bounds['maximum']);spacing=(hi-lo)/(grid-1)
    indices=np.indices((grid,grid,grid)).reshape(3,-1).T;points=lo+indices*spacing;inside=np.ones(len(points),bool)
    for view in views:
        camera=points@np.asarray(view['R']).T+view['t'];uv=(camera@np.asarray(view['K']).T)[:,:2]/camera[:,2,None];h,w=view['mask'].shape
        valid=(camera[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<=w-1)&(uv[:,1]>=0)&(uv[:,1]<=h-1)
        pixel=np.rint(uv[valid]).astype(int);support=np.zeros(len(points),bool);support[valid]=view['mask'][pixel[:,1],pixel[:,0]];inside&=support
    vertices,faces,_,_=marching_cubes(inside.reshape((grid,grid,grid)).astype(np.float32),.5,spacing=spacing)
    mesh=trimesh.Trimesh(vertices=vertices+lo,faces=faces,process=True);mesh.fix_normals();return mesh

class VisualHullTests(unittest.TestCase):
    def test_three_silhouette_cones_produce_real_closed_mesh(self):
        mesh,report=fuse_silhouettes(fixture_views(),{'minimum':[-1,-1,-1],'maximum':[1,1,1]},32)
        self.assertTrue(mesh.is_watertight);self.assertTrue(mesh.is_winding_consistent);self.assertGreater(mesh.volume,0);self.assertGreater(len(mesh.faces),100)
        self.assertFalse(report['sourceMeshRead']);self.assertFalse(report['boundaryOccupied']);self.assertLess(np.max(np.abs(mesh.bounds)),.8)

    def test_truncated_volume_rejected_instead_of_capped_fake_surface(self):
        with self.assertRaisesRegex(ValueError,'OPEN_BOUNDS'):fuse_silhouettes(fixture_views(),{'minimum':[-.3,-.3,-.3],'maximum':[.3,.3,.3]},24)

    def test_insufficient_views_duplicate_cameras_and_unbounded_grid_rejected(self):
        views=fixture_views();bounds={'minimum':[-1,-1,-1],'maximum':[1,1,1]}
        with self.assertRaisesRegex(ValueError,'VIEW_COUNT'):fuse_silhouettes(views[:2],bounds,32)
        with self.assertRaisesRegex(ValueError,'CAMERA_BASELINE'):fuse_silhouettes([views[0]]*3,bounds,32)
        with self.assertRaisesRegex(ValueError,'HULL_GRID'):fuse_silhouettes(views,bounds,193)

    def test_empty_intersection_is_not_a_successful_reconstruction(self):
        views=fixture_views()
        for view in views:view['mask'][:]=0;view['mask'][0:3,0:3]=255
        with self.assertRaisesRegex(ValueError,'HULL_EMPTY'):fuse_silhouettes(views,{'minimum':[-1,-1,-1],'maximum':[1,1,1]},24)

    def test_oblique_sphere_float_surface_improves_real_triangle_normals_and_contour(self):
        views,center,radius=analytic_sphere_views();bounds={'minimum':[-.9,-.9,-.9],'maximum':[.9,.9,.9]}
        current,report=fuse_silhouettes(views,bounds,36);legacy=legacy_binary_hull(views,bounds,36)
        def errors(mesh):
            radial=np.abs(np.linalg.norm(mesh.vertices-center,axis=1)-radius)
            outward=mesh.triangles_center-center;outward/=np.linalg.norm(outward,axis=1)[:,None]
            angular=np.rad2deg(np.arccos(np.clip(np.einsum('ij,ij->i',outward,mesh.face_normals),-1,1)))
            return float(np.mean(radial)),float(np.mean(angular))
        radial,normal=errors(current);old_radial,old_normal=errors(legacy)
        self.assertLess(radial,old_radial*.8);self.assertLess(normal,old_normal*.65)
        self.assertTrue(current.is_watertight);self.assertIn('bilinearly',report['method']);self.assertIn('no post-smoothing',report['method'])

if __name__=='__main__':unittest.main()
