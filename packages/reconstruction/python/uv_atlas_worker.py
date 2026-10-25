"""Fixed data-only xatlas child stage in an operator-selected Python runtime.

CLI: uv_atlas_worker.py INPUT.npz OUTPUT.npz EVIDENCE.json [OPTIONS.json]
The invoking process MUST enforce a 100-second subprocess deadline, including
native xatlas calls. All data paths must be regular files in one resolved local
directory. Inputs contain arrays only; no code, provider, or executable is read
from job data. Input arrays: vertices, faces; optional normals/resolution/padding.
Output NPZ has loop_uv, a per-original-triangle-corner (F,3,2) UV array.
"""
from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
from uv_atlas import generate_atlas


def _path(value):
    raw = Path(value)
    if not raw.is_absolute() or raw.is_symlink():
        raise ValueError('UV_ATLAS_WORKER_ABSOLUTE_REGULAR_PATH_REQUIRED')
    return raw.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('evidence')
    parser.add_argument('options',nargs='?')
    args = parser.parse_args(argv)
    source,output,evidence = [_path(value) for value in (args.source,args.output,args.evidence)]
    paths = [source,output,evidence]
    options_path = _path(args.options) if args.options else None
    if options_path:
        paths.append(options_path)
    if len(set(paths)) != len(paths) or len({path.parent for path in paths}) != 1:
        raise ValueError('UV_ATLAS_WORKER_PATH_SCOPE')
    if source.suffix.lower() != '.npz' or output.suffix.lower() != '.npz' or evidence.suffix.lower() != '.json':
        raise ValueError('UV_ATLAS_WORKER_FILE_TYPES')
    if not source.is_file() or source.stat().st_size > 128*1024*1024:
        raise ValueError('UV_ATLAS_WORKER_INPUT_BUDGET')
    options = {}
    if options_path:
        if not options_path.is_file() or options_path.suffix.lower() != '.json' or options_path.stat().st_size > 4096:
            raise ValueError('UV_ATLAS_WORKER_OPTIONS')
        options = json.loads(options_path.read_text(encoding='utf-8-sig'))
        if not isinstance(options,dict) or set(options)-{'resolution','padding'}:
            raise ValueError('UV_ATLAS_WORKER_OPTIONS')
    # Bound decompressed arrays too: a small compressed NPZ must not expand
    # into an unbounded allocation before the mesh checks can run.
    import zipfile
    with zipfile.ZipFile(source) as archive:
        if len(archive.infolist()) > 8 or sum(item.file_size for item in archive.infolist()) > 128*1024*1024:
            raise ValueError('UV_ATLAS_WORKER_EXPANDED_INPUT_BUDGET')
    with np.load(source,allow_pickle=False) as data:
        if not {'vertices','faces'} <= set(data.files):
            raise ValueError('UV_ATLAS_WORKER_ARRAYS')
        vertices,faces = data['vertices'],data['faces']
        normals = data['normals'] if 'normals' in data.files and data['normals'].size else None
        resolution = options.get('resolution',data['resolution'].item() if 'resolution' in data.files else 2048)
        padding = options.get('padding',data['padding'].item() if 'padding' in data.files else 8)
        loop_uv,report = generate_atlas(vertices,faces,resolution=resolution,padding=padding,normals=normals)
    report['workerContract'] = 'Fixed local array-only xatlas worker; caller enforces a 100s subprocess timeout.'
    # Publish only complete outputs. Existing destination files are never read.
    temporary_npz = output.with_name(output.name+'.tmp.npz')
    temporary_json = evidence.with_name(evidence.name+'.tmp.json')
    if temporary_npz.is_symlink() or temporary_json.is_symlink():
        raise ValueError('UV_ATLAS_WORKER_TEMP_PATH')
    try:
        np.savez_compressed(temporary_npz,loop_uv=loop_uv)
        temporary_json.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        os.replace(temporary_npz,output)
        os.replace(temporary_json,evidence)
    finally:
        temporary_npz.unlink(missing_ok=True)
        temporary_json.unlink(missing_ok=True)
    print('UV_ATLAS_COMPLETE',flush=True)


if __name__=='__main__':
    main()
