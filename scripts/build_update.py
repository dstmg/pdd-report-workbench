"""Build current public tree from the audited 1.0 allowlist, excluding local data."""
import hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'data/public-update/pdd-report-workbench-1.0'
CHANGED=['README.md','UPDATE-2026-10-15.md','scripts/collection_state.py','scripts/collection_controller.py','scripts/collect_reports.py','scripts/dashboard_data.py','scripts/review_store.py','scripts/serve_workbench.py','scripts/verify_release.py','scripts/process_lock.py','scripts/manual_import.py','scripts/test_manual_import.py','scripts/verify_manual_import.py','scripts/build_update.py','web/app.js','web/enhancements.js','web/index.html','web/manual-import.js','web/style.css']
def build():
    source=ROOT if (ROOT/'RELEASE-MANIFEST.json').exists() else ROOT/'交付/pdd-report-workbench-1.0'
    entries=json.loads((source/'RELEASE-MANIFEST.json').read_text(encoding='utf-8'))
    TARGET.mkdir(parents=True,exist_ok=True)
    for entry in entries:
        p=source/entry['path'];raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('原公开文件哈希变化：'+entry['path'])
        dest=TARGET/entry['path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    for name in CHANGED:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    manifest=[{'path':p.relative_to(TARGET).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(TARGET.rglob('*')) if p.is_file() and p.name!='RELEASE-MANIFEST.json']
    if any(e['path'].startswith(('data/','.venv/','.git/')) for e in manifest):raise ValueError('不允许运行数据进入发布包')
    (TARGET/'RELEASE-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Public update assembled: {len(manifest)} files')
if __name__=='__main__':build()
