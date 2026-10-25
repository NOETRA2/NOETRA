import unittest,sys,tempfile,hashlib,copy
from pathlib import Path
import numpy as np
import cv2 as cv
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/reconstruction/python'))
from observations import validate_observation_set,fit_observed_ellipse

class ObservationTests(unittest.TestCase):
    def ellipse(self):
        mask=np.zeros((160,200),np.uint8);cv.ellipse(mask,(100,80),(44,32),23,0,360,255,-1);return mask

    def fixture(self,root):
        def record(name,image):
            path=root/name;Image.fromarray(image).save(path);return {'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        camera={'convention':'opencv-world-to-camera-x-right-y-down-z-forward','K':[[100,0,100],[0,100,80],[0,0,1]],'R':np.eye(3).tolist(),'t':[0,0,3],'uncertaintyPx':1,'provenance':'authored calibration fixture'}
        return {'schemaVersion':1,'provenance':'test authored observations','parts':[{'id':'wheel','label':'wheel','objects':['Wheel'],'locked':False,'provenance':'authored part identity'}],
            'scale':{'status':'relative','units':'model units','uncertainty':1,'provenance':'no measurement supplied'},
            'views':[{'id':'source','image':record('source.png',np.zeros((160,200,3),np.uint8)),'origin':{'kind':'actual_photo','captureId':'capture-1','provenance':'operator attributed test image'},'role':'fit','camera':camera,
                'observations':[{'partId':'wheel','provenance':'authored outer wheel mask','uncertaintyPx':1,'mask':record('mask.png',self.ellipse()),'requireCompleteEllipse':True}]}]}

    def test_complete_mask_recovers_image_ellipse_without_3d_claim(self):
        result=fit_observed_ellipse(mask=self.ellipse());self.assertTrue(result['completeBoundarySupported'])
        np.testing.assert_allclose(result['centerPx'],[100,80],atol=.4);np.testing.assert_allclose(sorted(result['semiAxesPx']),[32,44],atol=.5)

    def test_truncated_wheel_rejected_even_away_from_image_border(self):
        mask=self.ellipse();mask[94:]=0
        result=fit_observed_ellipse(mask=mask);self.assertFalse(result['completeBoundarySupported']);self.assertFalse(result['touchesImageBorder'])

    def test_image_border_cutoff_rejected(self):
        mask=np.zeros((100,100),np.uint8);cv.circle(mask,(50,80),35,255,-1)
        self.assertFalse(fit_observed_ellipse(mask=mask)['completeBoundarySupported'])

    def test_boundary_keypoints_fit_and_partial_arc_is_incomplete(self):
        angle=np.linspace(0,2*np.pi,24,endpoint=False);points=np.column_stack([100+44*np.cos(angle),80+32*np.sin(angle)])
        self.assertTrue(fit_observed_ellipse(keypoints=points,image_size=(200,160))['completeBoundarySupported'])
        self.assertFalse(fit_observed_ellipse(keypoints=points[:14],image_size=(200,160))['completeBoundarySupported'])

    def test_source_hash_and_observation_identity_rechecked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);loaded=validate_observation_set(root,spec)
            changed=copy.deepcopy(spec);changed['views'][0]['origin']['provenance']='different attribution'
            with self.assertRaisesRegex(ValueError,'SET_CHANGED'):validate_observation_set(root,changed,loaded['sha256'])
            (root/'source.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):validate_observation_set(root,spec)

    def test_rendered_and_generated_views_cannot_validate_hidden_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root)
            for kind in ['rendered','generated']:
                spec['views'][0]['origin']['kind']=kind;spec['views'][0]['origin']['parentViewIds']=['source'];spec['views'][0]['role']='heldout'
                with self.assertRaisesRegex(ValueError,'HYPOTHESIS_VALIDATION'):validate_observation_set(root,spec)

    def test_heldout_photos_need_distinct_capture_and_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);heldout=copy.deepcopy(spec['views'][0]);heldout.update(id='heldout',role='heldout');spec['views'].append(heldout)
            with self.assertRaisesRegex(ValueError,'DUPLICATE_VALIDATION_VIEW'):validate_observation_set(root,spec)
            image=np.full((160,200,3),200,np.uint8);path=root/'heldout.png';Image.fromarray(image).save(path)
            heldout['image']={'path':'heldout.png','sha256':hashlib.sha256(path.read_bytes()).hexdigest()};heldout['origin']['captureId']='capture-2'
            loaded=validate_observation_set(root,spec);self.assertTrue(loaded['views']['heldout']['independentValidation'])

    def test_visible_part_masks_cannot_overlap_and_objects_cannot_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);part=copy.deepcopy(spec['parts'][0]);part['id']='other';spec['parts'].append(part)
            with self.assertRaisesRegex(ValueError,'OBJECT_OVERLAP'):validate_observation_set(root,spec)
            part['objects']=['Other'];observation=copy.deepcopy(spec['views'][0]['observations'][0]);observation['partId']='other';spec['views'][0]['observations'].append(observation)
            with self.assertRaisesRegex(ValueError,'MASK_OVERLAP'):validate_observation_set(root,spec)

    def test_camera_convention_and_nonfinite_uncertainty_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);spec['views'][0]['camera']['convention']='blender'
            with self.assertRaisesRegex(ValueError,'CAMERA_CONVENTION'):validate_observation_set(root,spec)
            spec=self.fixture(root);spec['views'][0]['observations'][0]['uncertaintyPx']=float('nan')
            with self.assertRaisesRegex(ValueError,'OBSERVATION_FIELDS'):validate_observation_set(root,spec)

    def test_boundary_points_cannot_upgrade_a_truncated_mask(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);mask=self.ellipse();mask[94:]=0;path=root/'mask.png';Image.fromarray(mask).save(path)
            observation=spec['views'][0]['observations'][0];observation['mask']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            angle=np.linspace(0,2*np.pi,48,endpoint=False);observation['ellipseBoundary']=np.column_stack([100+44*np.cos(angle),80+32*np.sin(angle)]).tolist()
            with self.assertRaisesRegex(ValueError,'WHEEL_BOUNDARY_INCOMPLETE'):validate_observation_set(root,spec)

    def test_outside_project_and_cyclic_render_lineage_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);spec['views'][0]['image']['path']='../outside.png'
            with self.assertRaisesRegex(ValueError,'OBSERVATION_PATH'):validate_observation_set(root,spec)
            spec=self.fixture(root)
            for identifier,parent in [('render-a','render-b'),('render-b','render-a')]:
                view=copy.deepcopy(spec['views'][0]);view.update(id=identifier,role='inspection');view['origin'].update(kind='rendered',parentViewIds=[parent]);spec['views'].append(view)
            with self.assertRaisesRegex(ValueError,'OBSERVATION_LINEAGE'):validate_observation_set(root,spec)

    def test_reference_artwork_can_constrain_fit_but_is_not_an_independent_photo(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);view=spec['views'][0];view['origin']['kind']='reference_artwork';view['origin']['provenance']='AI-created desired design reference'
            loaded=validate_observation_set(root,spec);self.assertFalse(loaded['views']['source']['independentValidation'])
            self.assertEqual(loaded['views']['source']['role'],'fit')
            view['role']='heldout'
            with self.assertRaisesRegex(ValueError,'INDEPENDENT_PHOTO_REQUIRED'):validate_observation_set(root,spec)

    def test_generated_backview_cannot_fit_or_independently_validate_artwork(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.fixture(root);spec['views'][0]['origin']['kind']='reference_artwork'
            view=copy.deepcopy(spec['views'][0]);view['id']='backview';view['origin'].update(kind='generated',parentViewIds=['source']);spec['views'].append(view)
            for role in ['fit','heldout']:
                view['role']=role
                with self.assertRaisesRegex(ValueError,'HYPOTHESIS_VALIDATION'):validate_observation_set(root,spec)
            view['role']='inspection';loaded=validate_observation_set(root,spec);self.assertFalse(loaded['views']['backview']['independentValidation'])

if __name__=='__main__':unittest.main()
