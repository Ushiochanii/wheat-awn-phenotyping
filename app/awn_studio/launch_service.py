"""Detach the model service from an interactive terminal (same Python environment)."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--device',default='cpu');args=parser.parse_args()
    try:
        with urlopen('http://127.0.0.1:8780/api/model',timeout=2) as response:
            print('Model service already running:',response.read().decode())
        raise SystemExit(0)
    except OSError:pass
    folder=ROOT/'artifacts/runtime';folder.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    if args.device!='cpu':env.setdefault('HSA_ENABLE_DXG_DETECTION','1')
    with (folder/'workbench_model_service.log').open('ab') as log:
        options=dict(stdin=subprocess.DEVNULL,stdout=log,stderr=log,cwd=ROOT,env=env)
        if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
        else:options['start_new_session']=True
        process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('serve_model.py')),'--device',args.device],**options)
    (folder/'workbench_model_service.pid').write_text(str(process.pid))
    print('Started model service PID',process.pid)
