"""Verify published source hashes and compile without emitting bytecode."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    entries = json.loads((ROOT / 'RELEASE-MANIFEST.json').read_text(encoding='utf-8'))
    required={'requirements.txt','install.ps1','start-workbench.cmd','start-workbench.ps1','create-desktop-shortcut.ps1',
              'web/index.html','web/app.js','web/enhancements.js','web/calculator.js','web/style.css',
              'scripts/browser_session.py','scripts/collect_reports.py','scripts/collection_state.py','scripts/collection_controller.py',
              'scripts/dashboard_data.py','scripts/launch_browser.py','scripts/metrics_catalog.py','scripts/report_validation.py',
              'scripts/review_store.py','scripts/serve_workbench.py','examples/demo/demo-live.json','examples/demo/demo-brand.json'}
    published={entry['path'] for entry in entries}
    if required-published:
        raise ValueError('Required runtime files missing from manifest: '+str(sorted(required-published)))
    seen = set()
    for entry in entries:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or entry['path'] in seen:
            raise ValueError('Invalid manifest path')
        seen.add(entry['path'])
        path = ROOT / relative
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256'] or len(raw) != entry['bytes']:
            raise ValueError('Source changed: ' + entry['path'])
        if path.suffix == '.py':
            compile(raw.decode('utf-8'), entry['path'], 'exec')
    for file in (ROOT / 'examples/demo').glob('*.json'):
        demo = json.loads(file.read_text(encoding='utf-8'))
        if demo.get('demo') is not True:
            raise ValueError('Example must be explicitly synthetic')
    html=(ROOT/'web/index.html').read_text(encoding='utf-8')
    for asset in re.findall(r'(?:src|href)="(/[^"\s]+)"',html):
        if not (ROOT/'web'/asset.lstrip('/')).is_file():raise ValueError('Missing page asset: '+asset)
    print(f'Verified {len(entries)} source files, Python syntax and synthetic example labels.')

if __name__ == '__main__':
    main()
