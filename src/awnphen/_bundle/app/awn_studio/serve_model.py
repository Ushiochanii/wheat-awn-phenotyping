"""Local model service with one serialized worker and immutable per-job artifacts."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from functools import partial
from pathlib import Path
from io import BytesIO
import json
import os
import threading
import uuid
import webbrowser
from urllib.parse import unquote, urlparse

import cv2
import numpy as np

# ROCm on WSL2 requires DXG detection to be enabled before torch/Ultralytics import.
if Path("/dev/dxg").exists():
    os.environ.setdefault("HSA_ENABLE_DXG_DETECTION", "1")

from PIL import Image, ImageOps
from start import WorkbenchHandler
from inference_backend import (
    DEFAULT_MODEL_ID,
    Engine,
    MODEL_NAME,
    WEIGHTS,
    ROOT,
    SUPPORTED_ADAPTERS,
    install_official_model,
    model_catalog,
    model_spec,
    register_custom_model,
    remove_custom_model,
)
from job_payload import persistent_job_payload, public_job_payload
from calibration_plausibility import assess_calibration_plausibility
from resolution_gate import ResolutionGate
from spikelet_scale_probe import SpikeletScaleProbe
from awnphen.phenotyping.measurement.calibration import GRID_MM, calibrate_grid_v2
from awnphen.pipeline.workbench_postprocess import (
    WORKBENCH_POSTPROCESS_VERSION,
    reconcile_detection_evidence as reconcile_workbench_detection_evidence,
    run_physical_closeout as run_workbench_physical_closeout,
)

JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)
RUN_ROOT = Path(
    os.environ.get(
        "AWNPHEN_STUDIO_RUNS",
        Path.cwd() / "runs" / "awn_studio",
    )
).expanduser().resolve()


class Handler(WorkbenchHandler):
    def translate_path(self, path):
        parsed = urlparse(path).path
        prefix = "/runs/awn_studio/"
        if parsed.startswith(prefix):
            relative = unquote(parsed[len(prefix):]).lstrip("/")
            candidate = (RUN_ROOT / relative).resolve()
            try:
                candidate.relative_to(RUN_ROOT)
            except ValueError:
                return str(RUN_ROOT / "__invalid_path__")
            return str(candidate)
        return super().translate_path(path)

    def end_headers(self):
        origin = self.headers.get('Origin')
        if origin and self.allowed_origin(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        super().end_headers()

    def allowed_origin(self, origin):
        parsed = urlparse(origin)
        return (
            parsed.scheme == 'http'
            and parsed.hostname in {'localhost', '127.0.0.1'}
            and parsed.port in {8000, 8781, self.server.server_port}
        )

    def reply(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.reply({})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/model':
            return self.reply(dict(
                model=MODEL_NAME,
                model_id=DEFAULT_MODEL_ID,
                available=WEIGHTS.is_file(),
                device=self.server.engine.device,
                pipeline_version=WORKBENCH_POSTPROCESS_VERSION,
                crossing_guard_enabled=True,
            ))
        if path == '/api/models':
            return self.reply(dict(
                default=DEFAULT_MODEL_ID,
                device=self.server.engine.device,
                models=model_catalog(),
                adapters=[{'id': key, 'name': value} for key, value in SUPPORTED_ADAPTERS.items()],
                loaded_model_id=self.server.engine.model_id,
            ))
        if path.startswith('/api/jobs/') and path.endswith('/preview'):
            jid = path.split('/')[-2]
            with LOCK:
                job = JOBS.get(jid)
                preview = dict(job.get('preview', {})) if job else None
                if preview:
                    preview['revision'] = job.get('preview_revision', 0)
            return self.reply(preview or {'error':'Preview is not available yet.'}, 200 if preview else 404)
        if path.startswith('/api/jobs/'):
            with LOCK:
                stored = dict(JOBS.get(path.rsplit('/',1)[-1], {}))
            if not stored:
                return self.reply({'error':'Job not found.'},404)
            try:
                return self.reply(public_job_payload(stored))
            except Exception as error:
                return self.reply({'error':str(error)},500)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        preflight_paths = {
            '/api/resolution-gate',
            '/api/grid-calibration',
            '/api/calibration-plausibility',
        }
        model_paths = {
            '/api/models/install',
            '/api/models/register',
            '/api/models/remove',
            '/api/models/preload',
        }
        if path not in preflight_paths and path not in model_paths and path != '/api/jobs':
            return self.reply({'error':'Unknown endpoint.'},404)
        if not self.allowed_origin(self.headers.get('Origin','')):
            return self.reply({'error':'Request origin is not allowed.'},403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if path in model_paths:
                if not 0 < length <= 64*1024:
                    raise ValueError('Model settings request is too large.')
                payload = json.loads(self.rfile.read(length))
                if path == '/api/models/install':
                    model_id = str(payload.get('model_id') or '')
                    spec = install_official_model(model_id)
                    return self.reply({
                        'model': spec.public(default=spec.id == DEFAULT_MODEL_ID),
                        'models': model_catalog(),
                    })
                if path == '/api/models/register':
                    spec = register_custom_model(
                        name=payload.get('name',''),
                        weights=payload.get('weights',''),
                        adapter=payload.get('adapter','ultralytics_yolo_seg'),
                        description=payload.get('description',''),
                    )
                    return self.reply({'model': spec.public(default=False), 'models': model_catalog()})
                if path == '/api/models/remove':
                    model_id = str(payload.get('model_id') or '')
                    if not model_id.startswith('custom-'):
                        raise ValueError('Only user-added models can be removed.')
                    if not remove_custom_model(model_id):
                        return self.reply({'error':'Custom model not found.'},404)
                    return self.reply({'removed':model_id, 'models':model_catalog()})
                model_id = str(payload.get('model_id') or '')
                spec = model_spec(model_id)
                future = POOL.submit(self.server.engine.preload, spec.id)
                loaded = future.result()
                return self.reply({'model_id':loaded.id, 'name':loaded.name, 'ready':True})
            if not 0 < length <= 40*1024*1024:
                raise ValueError('Image request limit is 40 MB.')
            payload = json.loads(self.rfile.read(length))
            header, encoded = payload['src'].split(',',1)
            if header not in {'data:image/jpeg;base64','data:image/png;base64','data:image/webp;base64'}:
                raise ValueError('Only JPG, PNG, and WebP are supported.')
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(BytesIO(raw)) as source:
                if source.width*source.height > 25_000_000:
                    raise ValueError('Images larger than 25 megapixels are not supported.')
                source = ImageOps.exif_transpose(source).convert('RGB')

                if path in preflight_paths:
                    image = cv2.cvtColor(np.asarray(source), cv2.COLOR_RGB2BGR)
                    if path == '/api/grid-calibration':
                        x_cal, y_cal, qc, _ = calibrate_grid_v2(image)
                        x_period = float(x_cal['period_px'])
                        y_period = float(y_cal['period_px'])
                        mean_period = (x_period + y_period) / 2.0
                        if not np.isfinite(mean_period) or mean_period <= 0:
                            raise RuntimeError(
                                'Automatic grid calibration did not produce a valid scale.'
                            )
                        return self.reply({
                            'mm_per_px': float(GRID_MM / mean_period),
                            'grid_mm': float(GRID_MM),
                            'x_period_px': x_period,
                            'y_period_px': y_period,
                            'qc_adequate': bool(qc['affine_scale_adequate']),
                            'qc_reasons': list(qc['qc_reasons']),
                            'calibration_version': qc['calibration_version'],
                        })
                    if path == '/api/calibration-plausibility':
                        measured = self.server.scale_probe.measure(image)
                        diagnostic = assess_calibration_plausibility(
                            measured,
                            mm_per_px=float(payload['mm_per_px']),
                        )
                        return self.reply({
                            'probe': measured.public(),
                            'plausibility': diagnostic.public(),
                        })

                    prepared, result = self.server.resolution_gate.prepare(
                        image,
                        force_below_reject=bool(payload.get('force', False)),
                    )
                    response = {'resolution': result.public()}
                    if result.applied:
                        ok, buffer = cv2.imencode('.png', prepared)
                        if not ok:
                            raise RuntimeError('Could not encode the prepared image.')
                        response['src'] = (
                            'data:image/png;base64,'
                            + base64.b64encode(buffer.tobytes()).decode('ascii')
                        )
                        response['width'] = result.output_width
                        response['height'] = result.output_height
                    return self.reply(response)

                im = source
                if [im.width,im.height] != [payload['width'],payload['height']]:
                    raise ValueError('Image dimensions do not match the canvas.')
                with LOCK:
                    if any(j['status'] in ('queued','running') for j in JOBS.values()):
                        return self.reply({'error':'Another measurement job is already running.'},409)
                    jid = uuid.uuid4().hex
                    folder = RUN_ROOT / jid
                    folder.mkdir(parents=True)
                    im.save(folder/'input.png')
                    mm_per_px=float(payload['mm_per_px'])
                    if not 0 < mm_per_px < 10:
                        raise ValueError('Invalid calibration ratio.')
                    selected_model=model_spec(payload.get('model_id'))
                    if not selected_model.available:
                        raise FileNotFoundError(f'Model weights not found: {selected_model.weights}')
                    JOBS[jid] = dict(
                        id=jid,
                        status='queued',
                        message='Waiting for the inference worker…',
                        width=im.width,
                        height=im.height,
                        mm_per_px=mm_per_px,
                        model_id=selected_model.id,
                        model=selected_model.name,
                    )
            POOL.submit(self.run_job,jid,folder,mm_per_px,selected_model.id)
            self.reply({'id':jid,'model_id':selected_model.id},202)
        except Exception as error:
            self.reply({'error':str(error)},400)

    def run_job(self,jid,folder,mm_per_px,model_id):
        def progress(message,tiles,*,preview=None,stage=None,total_tiles=None):
            with LOCK:
                update=dict(status='running',message=message,tiles=tiles)
                if stage is not None:
                    update['stage']=stage
                if total_tiles is not None:
                    update['total_tiles']=total_tiles
                if preview is not None:
                    update['preview_revision']=JOBS[jid].get('preview_revision',0)+1
                    update['preview']=preview
                JOBS[jid].update(update)
        try:
            self.server.engine.run(
                folder/'input.png',
                folder,
                progress,
                mm_per_px=mm_per_px,
                model_id=model_id,
            )
            from report import write_report
            write_report(folder)
            report=f'/runs/awn_studio/{jid}/integration_report.html'
            with LOCK:
                JOBS[jid].pop('preview',None)
                JOBS[jid].update(
                    status='done',
                    message='Automatic measurement complete.',
                    stage='done',
                    result_file=str(folder/'result.json'),
                    report=report,
                )
        except Exception as error:
            import traceback
            (folder/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            with LOCK:
                JOBS[jid].pop('preview',None)
                JOBS[jid].update(status='error',message=str(error))
        with LOCK:
            stored=dict(JOBS[jid])
        (folder/'job.json').write_text(
            json.dumps(persistent_job_payload(stored),ensure_ascii=False),
            encoding='utf-8',
        )


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8780)
    parser.add_argument('--device',default='auto')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),partial(Handler,directory=str(ROOT)))
    server.engine=Engine(
        args.device,
        physical_closeout_runner=run_workbench_physical_closeout,
        reconciliation_runner=reconcile_workbench_detection_evidence,
    )
    server.scale_probe=SpikeletScaleProbe(device=server.engine.device)
    server.resolution_gate=ResolutionGate(server.scale_probe)
    url=f'http://127.0.0.1:{args.port}/app/awn_studio/'
    print(f'Awn Studio: {url} (device {server.engine.device})',flush=True)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    server.serve_forever()

