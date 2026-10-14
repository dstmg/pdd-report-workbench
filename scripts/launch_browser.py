"""Launch ordinary installed Chrome before automation attaches; local endpoint only."""
import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def owned(record):
    port, pid = int(record['port']), int(record['pid'])
    expected_profile = Path(os.environ['LOCALAPPDATA']) / 'PddReportDownloader/browser-profile-chrome'
    if Path(record['profile']) != expected_profile or not 1 <= port <= 65535:
        raise RuntimeError('启动记录的登录目录或端口无效')
    environment = dict(os.environ, PDD_CHECK_PROFILE=str(expected_profile), PDD_CHECK_CHROME=record['chrome'])
    script = (f'$p=Get-CimInstance Win32_Process -Filter "ProcessId = {pid}"; '
        'if (!$p) {exit 2}; '
        'if ($p.ExecutablePath -ne $env:PDD_CHECK_CHROME -or !$p.CommandLine.Contains($env:PDD_CHECK_PROFILE)) {exit 1}; '
        f'$l=@(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue); '
        f'if ($l.Count -ne 1 -or $l[0].LocalAddress -ne "127.0.0.1" -or $l[0].OwningProcess -ne {pid}) {{exit 1}}')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], env=environment, capture_output=True)
    if result.returncode == 2:
        return False
    if result.returncode:
        raise RuntimeError('启动记录的进程、程序、登录目录或端口归属异常，停止而不连接或结束进程')
    return True


def launch():
    # Serialize Chrome startup across project copies sharing the dedicated profile.
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateMutexW(None,False,'Local\\PddReportDownloaderChromeLauncher')
    if not handle:raise RuntimeError('无法创建浏览器启动互斥锁')
    acquired=kernel.WaitForSingleObject(handle,0) in (0,128)
    if not acquired:
        kernel.CloseHandle(handle)
        raise RuntimeError('另一个启动操作正在进行，请稍后重试')
    try:_launch()
    finally:kernel.ReleaseMutex(handle);kernel.CloseHandle(handle)


def _launch():
    record_path = ROOT / 'data/browser-launch.json'
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if owned(record):
            print('已核验并复用现有专用Chrome，无需重新扫码。')
            print(json.dumps({'pid': record['pid'], 'port': record['port'], 'reused': True}, ensure_ascii=False))
            return
    candidates = [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
                  Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/Application/chrome.exe']
    chrome = next((path for path in candidates if path.is_file()), None)
    if chrome is None:
        raise RuntimeError('未找到Google Chrome；请配置已安装的浏览器路径')
    profile = Path(os.environ['LOCALAPPDATA']) / 'PddReportDownloader/browser-profile-chrome'
    # Reuse the same dedicated profile to vary the launch method alone.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    args = [str(chrome), f'--user-data-dir={profile}', f'--remote-debugging-port={port}',
            '--remote-debugging-address=127.0.0.1', '--no-first-run', '--no-default-browser-check',
            'https://yingxiao.pinduoduo.com/']
    process = subprocess.Popen(args)
    record = {'pid': process.pid, 'port': port, 'chrome': str(chrome), 'profile': str(profile),
              'launch_method': 'ordinary_chrome_before_cdp', 'automation_attached': False}
    deadline=time.monotonic()+15
    while True:
        if process.poll() is not None:
            raise RuntimeError('Chrome进程未独立启动；可能另一工程已打开相同专用环境。保留原启动记录，不接管未知窗口')
        try:
            if owned(record):break
        except RuntimeError:
            if time.monotonic()>=deadline:raise
        if time.monotonic()>=deadline:raise RuntimeError('独立Chrome端点未就绪，保留原记录供核验')
        time.sleep(0.25)
    directory = ROOT / 'data'
    directory.mkdir(exist_ok=True)
    path = directory / 'browser-launch.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    print(json.dumps(record, ensure_ascii=False))
    print('普通Chrome已启动，当前没有连接自动化。请先人工核对登录；不要反复扫码。')


def check():
    record = json.loads((ROOT / 'data/browser-launch.json').read_text(encoding='utf-8'))
    if not owned(record):
        raise RuntimeError('记录中的专用Chrome已经退出')
    endpoint = f"http://127.0.0.1:{int(record['port'])}/json/version"
    with urlopen(endpoint, timeout=3) as response:
        version = json.load(response)
    # Do not read profile storage, cookies, page requests, or WebSocket IDs.
    print(json.dumps({'port': record['port'], 'browser': version.get('Browser'),
                      'protocol': version.get('Protocol-Version'), 'endpoint_reachable': True}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check() if args.check else launch()
