"""Test the actual ZIP in a fresh directory and environment; no merchant access."""
import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(command,cwd,env,expected=0):
    result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    if result.returncode!=expected:
        raise RuntimeError(f'{command[0]} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}')
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--zip',required=True);args=parser.parse_args()
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
    for key in ('PYTHONPATH','PYTHONHOME','PDD_REVIEW_DIR'):env.pop(key,None)
    with tempfile.TemporaryDirectory(prefix='PDD 发布验收 ') as directory:
        target=Path(directory)
        with zipfile.ZipFile(args.zip) as bundle:
            for name in bundle.namelist():
                relative=Path(name)
                if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe ZIP path')
                if any(part in relative.parts for part in ('.venv','data','__pycache__')):raise ValueError('Runtime data in ZIP')
            bundle.extractall(target)
        roots=[path for path in target.iterdir() if path.is_dir()]
        assert len(roots)==1;project=roots[0]
        entries=json.loads((project/'RELEASE-MANIFEST.json').read_text(encoding='utf-8'))
        allowed={entry['path'] for entry in entries}|{'RELEASE-MANIFEST.json'}
        actual={path.relative_to(project).as_posix() for path in project.rglob('*') if path.is_file()}
        assert actual==allowed,'ZIP must contain exactly the manifest files'
        for entry in entries:assert hashlib.sha256((project/entry['path']).read_bytes()).hexdigest()==entry['sha256']
        print(f'Actual ZIP file list and hashes passed: {len(actual)} files.',flush=True)
        modules={path.stem for path in (project/'scripts').glob('*.py')}
        imports=set()
        for path in (project/'scripts').glob('*.py'):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module.split('.')[0])
        external=imports-modules
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(project/'install.ps1')],project,env)
        python=str(project/'.venv/Scripts/python.exe')
        # Dependency resolution must use the newly installed environment.
        run([python,'-c','import importlib.util; names='+repr(sorted(external))+'; missing=[n for n in names if importlib.util.find_spec(n) is None]; assert not missing,missing'],project,env)
        run([python,'-m','pip','check'],project,env)
        for script in ('verify_release.py','test_audit_regressions.py','test_clean_start.py','test_desktop_calculator.py','test_pagination.py'):
            run([python,str(project/'scripts'/script)],project,env);print(script+' passed from extracted ZIP.',flush=True)
        for script in ('collect_reports.py','launch_browser.py','serve_workbench.py'):
            run([python,str(project/'scripts'/script),'--help'],project,env)
        desktop=target/'测试桌面';desktop.mkdir()
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(project/'create-desktop-shortcut.ps1'),'-DesktopDirectory',str(desktop)],project,env)
        assert (desktop/'PDD Workbench.lnk').is_file()
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(project/'start-workbench.ps1'),'-ValidateOnly'],project,env)
        service=subprocess.Popen([python,str(project/'scripts/serve_workbench.py'),'--port','0'],cwd=project,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            port=re.search(r'127\.0\.0\.1:(\d+)',service.stdout.readline()).group(1);base='http://127.0.0.1:'+port
            with urllib.request.urlopen(base) as response:html=response.read().decode('utf-8')
            for asset in re.findall(r'(?:src|href)="(/[^"\s]+)"',html):
                with urllib.request.urlopen(base+asset) as response:assert response.status==200 and response.read()
            for route in ('/api/batches','/api/collection','/api/reviews'):
                with urllib.request.urlopen(base+route) as response:json.loads(response.read())
        finally:service.terminate();service.wait(timeout=10)
        # Ensure the integrity check rejects a genuinely missing runtime script.
        removed=project/'scripts/launch_browser.py';backup=removed.read_bytes();removed.unlink()
        try:
            failed=subprocess.run([python,str(project/'scripts/verify_release.py')],cwd=project,env=env,capture_output=True)
            assert failed.returncode!=0,'Missing runtime script must be detected'
        finally:removed.write_bytes(backup)
        print('Fresh ZIP installation, dependencies, assets, APIs, launchers, tests and missing-file rejection passed. No login or merchant collection performed.',flush=True)

if __name__=='__main__':main()
