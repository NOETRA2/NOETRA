"""Fixed Blender export for a computed hull; never opens its source/template scene."""
from pathlib import Path
import os,json,subprocess
import cv2 as cv
from part_correction import permission,save
from geometry import require,compare_masks

def render_calibrated_hull(run,manifest,config):
    executable=permission(config)
    job={'output':str(run),'views':manifest['views']}
    save(run/'export-job.json',job)
    resources=run/'blender-runtime';resources.mkdir(exist_ok=True)
    result=subprocess.run([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).with_name('calibrated_blender.py')),'--',str(run/'export-job.json')],cwd=str(run),env={**os.environ,'BLENDER_USER_RESOURCES':str(resources)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (run/'export-log.txt').write_bytes(result.stdout[-262144:])
    require(result.returncode==0,'RECONSTRUCTION_CALIBRATED_EXPORT_FAILED')
    measurements={}
    for view in manifest['views']:
        observed=cv.imread(view['mask']['path'],cv.IMREAD_GRAYSCALE)
        rendered=cv.imread(str(run/(view['id']+'-render.png')),cv.IMREAD_UNCHANGED)
        require(rendered is not None and rendered.shape==(*observed.shape,4),'RECONSTRUCTION_CALIBRATED_RENDER_MISSING')
        measurements[view['id']]=compare_masks(observed>127,rendered[:,:,3]>127)
    evidence=json.loads((run/'render-evidence.json').read_text())
    return {'outputs':{'blend':str(run/'model.blend'),'glb':str(run/'model.glb'),'preview':str(run/(manifest['views'][0]['id']+'-render.png'))},'measurements':measurements,'evidence':evidence,'scope':'Actual new mesh renders compared to supplied silhouettes; not independent hidden-surface validation.'}
