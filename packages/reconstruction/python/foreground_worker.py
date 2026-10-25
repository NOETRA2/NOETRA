"""Private fixed foreground stage. Exits before expensive shape inference starts."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import numpy as np
from PIL import Image
from photo_provider import foreground,digest
from geometry import require
from part_correction import save
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());out=Path(job['output'])
with Image.open(job['image']) as picture:
    manifest={}
    if job['mask'] is None and not (picture.mode=='RGBA' and picture.getextrema()[3][0]<255):
        path=Path(job['modelManifest']);require(path.is_file() and path.stat().st_size<1_000_000,'RECONSTRUCTION_MODEL_MANIFEST')
        manifest=json.loads(path.read_text(encoding='utf8'));background=manifest['files']['background'];asset=Path(background['path'])
        require(asset.is_absolute() and asset.is_file() and asset.stat().st_size==background['bytes'] and digest(asset)==background['sha256'],'RECONSTRUCTION_BACKGROUND_MODEL_CHANGED')
    _,transform=foreground(picture,manifest,out,job['mask'])
    rgb=np.asarray(picture.convert('RGB'));alpha=np.asarray(Image.open(out/'foreground.png').convert('L'))
    Image.fromarray(np.dstack([rgb,alpha]).astype(np.uint8)).save(out/'foreground-rgba.png')
save(out/'foreground-provenance.json',transform)
print('NOETRA_FOREGROUND_PREPARED')
