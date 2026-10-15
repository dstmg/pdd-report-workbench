"""Loopback-only workbench; explicit collection and local review operations."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from dashboard_data import batches, dataset
from review_store import ReviewStore
from collection_controller import Controller
from manual_import import preview,import_files
import subprocess
import os
import sys

WEB = Path(__file__).resolve().parents[1] / 'web'
ROOT=WEB.parent
REVIEW_DIRECTORY=Path(os.environ.get('PDD_REVIEW_DIR',str(ROOT/'data/reviews')))
if not REVIEW_DIRECTORY.is_absolute():raise ValueError('PDD_REVIEW_DIR必须为绝对目录')
REVIEWS=ReviewStore(REVIEW_DIRECTORY)
COLLECTION=Controller(ROOT)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path)
        host = self.headers.get('Host', '')
        if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send_error(403)
            return
        try:
            if route.path == '/api/batches':
                self.reply(json.dumps(batches(), ensure_ascii=False).encode(), 'application/json; charset=utf-8')
            elif route.path=='/api/collection':
                self.reply(json.dumps(COLLECTION.status(),ensure_ascii=False).encode(),'application/json; charset=utf-8')
            elif route.path=='/api/reviews':
                self.reply(json.dumps(REVIEWS.read(),ensure_ascii=False).encode(),'application/json; charset=utf-8')
            elif route.path == '/api/dataset':
                batch = parse_qs(route.query).get('batch', [''])[0]
                self.reply(json.dumps(dataset(batch), ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')
            elif route.path in ('/', '/app.js', '/style.css','/enhancements.js','/calculator.js','/manual-import.js'):
                filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css','/enhancements.js':'enhancements.js','/calculator.js':'calculator.js','/manual-import.js':'manual-import.js'}[route.path]
                mime = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/style.css': 'text/css; charset=utf-8','/enhancements.js':'text/javascript; charset=utf-8','/calculator.js':'text/javascript; charset=utf-8','/manual-import.js':'text/javascript; charset=utf-8'}[route.path]
                self.reply((WEB / filename).read_bytes(), mime)
            else:
                self.send_error(404)
        except (ValueError, KeyError, OSError) as exc:
            self.reply(json.dumps({'error': str(exc)}, ensure_ascii=False).encode(), 'application/json; charset=utf-8', 422)

    def do_POST(self):
        host=self.headers.get('Host','')
        if host not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}') or self.headers.get('Origin')!='http://'+host:
            self.send_error(403);return
        try:
            route=urlparse(self.path).path
            length=int(self.headers.get('Content-Length','0'))
            limit=32*1024*1024 if route.startswith('/api/import/') else 100000
            if not 0<length<=limit or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('请求类型或大小无效')
            body=json.loads(self.rfile.read(length));route=urlparse(self.path).path
            if route in ('/api/import/preview','/api/import/confirm'):
                with COLLECTION.lock:
                    if COLLECTION.process and COLLECTION.process.poll() is None:raise ValueError('采集中不能导入')
                    result=preview(body) if route.endswith('preview') else import_files(body)
            elif route=='/api/reviews':result=REVIEWS.save(body)
            elif route=='/api/collection/start':result=COLLECTION.start(body['shop'],body['start'],body['end'])
            elif route=='/api/collection/command':result=COLLECTION.command(body['action'])
            elif route=='/api/collection/pause':result=COLLECTION.request_pause()
            elif route=='/api/browser/open':
                completed=subprocess.run([sys.executable,str(ROOT/'scripts/launch_browser.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8'),timeout=20)
                if completed.returncode:raise ValueError('浏览器未启动，请检查登录环境及进程归属')
                result={'message':'专用Chrome已打开或复用，请人工核对登录'}
            elif route=='/api/desktop-shortcut':
                completed=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'create-desktop-shortcut.ps1')],cwd=ROOT,capture_output=True,timeout=20)
                if completed.returncode:raise ValueError('桌面快捷方式未创建；请检查桌面权限或是否存在指向其他目录的同名快捷方式')
                result={'message':'已添加到桌面：PDD Workbench，双击即可启动。移动项目后请重新创建快捷方式。'}
            elif route=='/api/report-folder':
                directory=(ROOT/'data/reports').resolve()
                subprocess.Popen(['explorer.exe',str(directory)])
                result={'message':'已请求打开本地报表目录'}
            else:self.send_error(404);return
            self.reply(json.dumps(result,ensure_ascii=False,allow_nan=False).encode(),'application/json; charset=utf-8')
        except (ValueError,KeyError,OSError,subprocess.TimeoutExpired) as exc:
            self.reply(json.dumps({'error':str(exc)},ensure_ascii=False).encode(),'application/json; charset=utf-8',422)

    def reply(self, content, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5191)
    args = parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'拼多多工作台：http://127.0.0.1:{server.server_port}', flush=True)
    server.serve_forever()
