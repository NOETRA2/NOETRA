import unittest,sys,tempfile,json,hashlib,shutil,uuid
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from calibrated_views import reconstruct_from_views,load_calibrated_views
from test_visual_hull import fixture_views

class CalibratedViewTests(unittest.TestCase):
    def fixture(self,root):
        views=[]
        def image(name,array):
            path=root/name;Image.fromarray(array).save(path);return {'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        for i,view in enumerate(fixture_views()):
            camera={k:view[k] for k in ['K','R','t']};camera.update(convention='opencv-world-to-camera-x-right-y-down-z-forward',uncertaintyPx=0,provenance='analytic fixture camera')
            views.append({'id':'view-'+str(i),'image':image('image-'+str(i)+'.png',np.full((128,128,3),i*50,np.uint8)),
                'mask':image('mask-'+str(i)+'.png',view['mask']),'camera':camera,'origin':{'kind':'rendered','captureId':'synthetic-'+str(i),'provenance':'analytic sphere silhouette test; not a source photograph'}})
        manifest={'schemaVersion':1,'provenance':'analytical geometry fixture','bounds':{'minimum':[-1,-1,-1],'maximum':[1,1,1]},'grid':32,'views':views}
        path=root/'views.json';path.write_text(json.dumps(manifest,indent=1));return manifest,path

    def scope(self,root,path):
        root=Path(root).resolve();candidate=Path(path);candidate=(candidate if candidate.is_absolute() else root/candidate).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():raise ValueError('PROJECT_SCOPE')
        return candidate

    def helpers(self):
        def new_run(root):
            path=Path(root)/str(uuid.uuid4());path.mkdir();return path
        def record(root,path,run,index):
            source=self.scope(root,path);preserved=run/(str(index)+source.suffix);shutil.copyfile(source,preserved)
            with Image.open(source) as image:rgb=np.asarray(image.convert('RGB'))
            return {'source':str(source),'preserved':str(preserved),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},rgb
        return self.scope,new_run,record

    def test_manifest_only_reconstruction_exports_mesh_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,path=self.fixture(root)
            report=reconstruct_from_views(root,{'manifest':'views.json'},{},self.helpers())
            self.assertFalse(report['sourceMeshRead']);self.assertEqual(report['derivedViewCount'],3);self.assertIn('derived-render',report['validationScope'])
            self.assertEqual(Path(report['sourceManifest']['preserved']).read_bytes(),path.read_bytes());self.assertTrue(Path(report['outputs']['ply']).is_file());self.assertTrue(Path(report['outputs']['glb']).is_file())
            import trimesh
            reopened=trimesh.load(report['outputs']['ply'],force='mesh');self.assertTrue(reopened.is_watertight);self.assertEqual(len(reopened.faces),report['geometry']['triangles'])

    def test_tampered_mask_rejected_before_reconstruction(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,path=self.fixture(root);(root/'mask-0.png').write_bytes(b'changed')
            with self.assertRaises((ValueError,OSError)):load_calibrated_views(root,'views.json',self.scope)

    def test_mesh_input_and_unsupported_origin_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,path=self.fixture(root);manifest['sourceMesh']='forbidden.blend';path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'OBSERVATION_FIELDS'):load_calibrated_views(root,'views.json',self.scope)
            manifest.pop('sourceMesh');manifest['views'][0]['origin']['kind']='generated';path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'HULL_ORIGIN'):load_calibrated_views(root,'views.json',self.scope)

    def test_source_photo_and_artwork_scope_are_distinct_from_derived_renders(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,path=self.fixture(root)
            for view in manifest['views']:view['origin']['kind']='reference_artwork'
            path.write_text(json.dumps(manifest));report=reconstruct_from_views(root,{'manifest':'views.json'},{},self.helpers())
            self.assertEqual(report['derivedViewCount'],0);self.assertIn('reference-artwork',report['validationScope'])

if __name__=='__main__':unittest.main()
