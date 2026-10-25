import sys,unittest,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages'/'reconstruction'/'python'))
import numpy as np
from part_correction import gate,validate_spec,check_sources,permission,part_loss,summary
from worker import scope
from outline_model import geometry_from_outline

def spec():
    return {'parts':[{'id':'lamp','objects':['lamp']},{'id':'hood','objects':['hood']}],
        'parameters':[{'id':'lamp-x','partId':'lamp','kind':'translate','axis':'X','minimum':-.2,'maximum':.2,'step':.1}],
        'views':[{'id':'front','annotations':[{'partId':'lamp','polygon':[[1,1],[5,1],[5,5]],'provenance':'test'}]}],
        'minimumLossImprovement':.0001,'influencePaddingPixels':1}

def metrics(loss=.3,iou=.8,distance=3):
    return {'front':{'lamp':{'loss':loss,'iou':iou,'boundary':{'mean_px':distance}}}}

def fingerprint():return {'objects':{'lamp':'a','hood':'b','wheel':'c','camera':'d'},'world':'w','frame':1,'active_camera':'camera'}

class PartCorrectionTests(unittest.TestCase):
    def test_new_dispatch_does_not_shadow_existing_image_inspector(self):
        import worker
        from PIL import Image
        try:
            with tempfile.TemporaryDirectory() as name:
                root=Path(name).resolve();image=root/'image.png';Image.new('RGB',(8,8)).save(image)
                result=worker.main({'projectRoot':str(root),'operation':'inspect_image_structure','payload':{'images':[str(image)]},'config':{}})
                self.assertEqual(result['images'][0]['width'],8)
        finally:worker.ACTIVE_ROOT=None

    def test_compact_reports_do_not_serialize_dense_history(self):
        entry={'parameter':'p','targetPart':'lamp','accepted':False,'changedObjects':['x'*160]*512,'mismatch':{'dense':'x'*200000}}
        report={'kind':'part-correction','best':'initial','bestValues':{},'stages':[{'folder':'initial','measurements':metrics()}],
            'history':[entry]*48,'unknowns':[]}
        result=summary(Path('/project/run'),report)
        self.assertEqual(result['historyCount'],48);self.assertEqual(len(result['history']),12)
        self.assertLess(len(json.dumps(result)),65536)

    def test_outline_front_stays_fixed_while_hidden_depth_changes(self):
        points=[[20,20],[80,20],[80,60],[20,60]]
        sections=[{'t':0,'scaleX':1,'scaleZ':1},{'t':1,'scaleX':.8,'scaleZ':.8}]
        a=geometry_from_outline(points,100,80,2,.5,sections);b=geometry_from_outline(points,100,80,2,2,sections)
        np.testing.assert_allclose(a['rings'][0],b['rings'][0]);self.assertNotEqual(a['depth'],b['depth'])
        self.assertAlmostEqual(a['orthoScale'],2/60*100)

    def test_outline_observed_front_cannot_be_shrunk_by_hidden_profile(self):
        with self.assertRaisesRegex(ValueError,'OUTLINE_SECTIONS'):
            geometry_from_outline([[20,20],[80,20],[80,60],[20,60]],100,80,2,1,[{'t':0,'scaleX':.8,'scaleZ':1},{'t':1,'scaleX':.8,'scaleZ':.8}])

    def test_outline_outside_image_rejected(self):
        with self.assertRaisesRegex(ValueError,'OUTSIDE_IMAGE'):
            geometry_from_outline([[-1,20],[80,20],[80,60]],100,80,2,1,[{'t':0,'scaleX':1,'scaleZ':1},{'t':1,'scaleX':.8,'scaleZ':.8}])
    def test_only_measured_improvement_is_accepted(self):
        old=fingerprint();new=fingerprint();new['objects']['lamp']='edited'
        self.assertTrue(gate(metrics(),metrics(.1,.95,1),old,new,['lamp'],spec(),'lamp')['accepted'])
        self.assertFalse(gate(metrics(),metrics(),old,new,['lamp'],spec(),'lamp')['accepted'])

    def test_better_target_cannot_change_hood_wheels_or_camera(self):
        for name in ['hood','wheel','camera']:
            after=fingerprint();after['objects'][name]='corrupted'
            result=gate(metrics(),metrics(.1,.95,1),fingerprint(),after,['lamp'],spec(),'lamp')
            self.assertFalse(result['accepted']);self.assertIn('protected_object_changed',result['reasons'])

    def test_other_view_regression_rejected_even_with_better_average(self):
        before=metrics();before['side']=before['front']
        after=metrics(.01,.99,.1);after['side']=metrics(.31,.79,3.1)['front']
        result=gate(before,after,fingerprint(),fingerprint(),['lamp'],spec(),'lamp')
        self.assertFalse(result['accepted']);self.assertIn('part_view_regressed',result['reasons'])

    def test_better_overlap_with_worse_edge_is_rejected(self):
        result=gate(metrics(),metrics(.1,.95,4),fingerprint(),fingerprint(),['lamp'],spec(),'lamp')
        self.assertFalse(result['accepted']);self.assertIn('part_boundary_regressed',result['reasons'])

    def test_protected_part_regression_rejected(self):
        before=metrics();before['front']['hood']={'loss':.1,'iou':.95,'boundary':{'mean_px':1}}
        after=metrics(.1,.95,1);after['front']['hood']={'loss':.2,'iou':.9,'boundary':{'mean_px':2}}
        self.assertFalse(gate(before,after,fingerprint(),fingerprint(),['lamp'],spec(),'lamp')['accepted'])

    def test_missing_view_never_counts_as_improvement(self):
        self.assertFalse(gate(metrics(),{},fingerprint(),fingerprint(),['lamp'],spec(),'lamp')['accepted'])

    def test_visibility_outside_fixed_influence_region_rejected(self):
        a=np.zeros((16,16),bool);a[2:4,2:4]=True
        b=np.zeros_like(a);b[10:12,10:12]=True
        am={'lamp':a,'hood':b};bm={'lamp':a,'hood':b.copy()};bm['hood'][15,15]=True
        view=spec()['views'][0]
        result=gate(metrics(),metrics(.1,.95,1),fingerprint(),fingerprint(),['lamp'],spec(),'lamp',[(view,am,a|b,bm,a|b)])
        self.assertFalse(result['accepted']);self.assertEqual(result['protectedPixelChanges']['front'],1)

    def test_duplicate_part_ownership_rejected(self):
        value=spec();value['parts'][1]['objects']=['lamp']
        with self.assertRaisesRegex(ValueError,'PART_OVERLAP'):validate_spec(value)

    def test_undeclared_control_and_duplicate_control_rejected(self):
        value=spec();value['parameters'][0].update(kind='mesh_offset',object='wheel',indices=[0])
        with self.assertRaisesRegex(ValueError,'PART_OWNERSHIP'):validate_spec(value)
        value['parameters'][0].update(object='lamp',indices=[0,0])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_CONTROL'):validate_spec(value)

    def test_no_measured_target_and_degenerate_polygon_rejected(self):
        value=spec();value['views'][0]['annotations'][0]['partId']='hood'
        with self.assertRaisesRegex(ValueError,'PARAMETER_PART'):validate_spec(value)
        value=spec();value['views'][0]['annotations'][0]['polygon']=[[0,0],[0,0],[0,0]]
        with self.assertRaisesRegex(ValueError,'POLYGON_AREA'):validate_spec(value)

    def test_disabled_execution_fails_before_opening_scene(self):
        with self.assertRaisesRegex(ValueError,'EXECUTION_NOT_APPROVED'):permission({'allowBlenderExecution':False})

    def test_original_scene_mutation_invalidates_correction(self):
        import hashlib
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();run=root/'run';run.mkdir();source=root/'source.blend';source.write_bytes(b'original')
            (run/'source.blend').write_bytes(b'original')
            report={'sceneSource':str(source),'sceneSha256':hashlib.sha256(b'original').hexdigest(),'runtimeDigests':{}}
            check_sources(root,run,report,scope);source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SCENE_CHANGED'):check_sources(root,run,report,scope)

if __name__=='__main__':unittest.main(verbosity=2)
