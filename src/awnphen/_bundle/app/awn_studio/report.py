"""Offline integration evidence, explicitly not an accuracy evaluation."""
import base64
import html
import json
from pathlib import Path
from PIL import Image


def write_report(folder):
    folder=Path(folder)
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    source=folder/'input.png'
    with Image.open(source) as im:width,height=im.size
    encoded=base64.b64encode(source.read_bytes()).decode()
    overlays=[]
    for i,g in enumerate(result['groups'],1):
        points=lambda values:' '.join(f'{x},{y}' for x,y in values)
        overlays.append(f'<polygon points="{points(g["polygon"])}" fill="#00aa4420" stroke="#167342" stroke-width="3"/>')
        if g['line']:
            overlays.append(f'<polyline points="{points(g["line"])}" fill="none" stroke="#dc9200" stroke-width="5"/>')
    facts={k:v for k,v in result.items() if k not in {'groups','layers'}}
    document=f'''<!doctype html><meta charset="utf-8"><title>Real-model integration validation</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:30px auto;padding:20px;color:#243b34}}svg{{width:100%;border:1px solid #ccc}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f4ee;padding:20px}}</style>
<h1>Real-model integration validation</h1><p>{len(result['groups'])} spikelets; {result['path_count']} representative awns; {result['seconds']} seconds.</p>
<p>Configuration: 640 px tiles / 320 px stride. One low-threshold model observation supplies both primary Evidence and low-confidence completion. Post-processing follows the current canonical Evidence → Reconciliation → Physical reconstruction/completion → Representative selection → Root normalization pipeline and does not read historical predictions or manual ground truth. Spikelets are shown in green and representative awns in yellow. Missing paths remain blank rather than being treated as zero.</p>
<p>This report validates product integration only; it is not a model-accuracy evaluation. No training was performed, no training curves are reported, awn/spikelet mask metrics were not calculated, and no manual length reference was used. Existing errors and missing measurements still require manual correction. The scale is entered in the Workbench and participates in canonical physical reconstruction and path measurement; this report does not claim millimetre-level accuracy.</p>
<svg viewBox="0 0 {width} {height}"><image width="{width}" height="{height}" href="data:image/png;base64,{encoded}"/>{''.join(overlays)}</svg>
<h2>Weights, device, and result provenance</h2><pre>{html.escape(json.dumps(facts,ensure_ascii=False,indent=2))}</pre>'''
    (folder/'integration_report.html').write_text(document,encoding='utf-8')

if __name__=='__main__':
    import sys
    write_report(sys.argv[1])
