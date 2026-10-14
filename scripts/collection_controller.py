"""Controlled local subprocess with explicit manual continuation and progress."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from browser_session import dates
from collection_state import Journal
from launch_browser import owned


class Controller:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.RLock();self.process=None;self.journal=None
        self.logs=[];self.result='idle';self.message='尚未发起页面采集'
        self.original_stamp=None

    def status(self):
        with self.lock:
            result={'state':self.result,'message':self.message,'logs':self.logs[-8:],'tasks':[]}
            if self.journal and self.journal.path.exists():
                if self.process and self.process.poll() not in (None,0):
                    return {**result,'state':'needs_attention','message':'采集进程未完成，请查看诊断；原进度保留'}
                if self.journal.path.stat().st_mtime_ns==self.original_stamp:
                    return result
                j=json.loads(self.journal.path.read_text(encoding='utf-8'))
                result.update(state=j['state'],message=j.get('message',''),tasks=list(j['tasks'].values()))
                if self.process and self.process.poll() is not None and result['state'] not in ('complete','needs_attention'):
                    result.update(state='needs_attention',message='采集已停止，进度保留')
            return result

    def start(self,shop,start,end):
        shop=str(shop).strip()
        if not shop or len(shop)>100 or '模拟' in shop or '示例' in shop:raise ValueError('请填写真实店铺名称')
        start,end=dates(start,end)
        with self.lock:
            if self.process and self.process.poll() is None:raise ValueError('已有页面采集正在运行')
            if (self.root/'data/browser-collection.lock').exists():raise ValueError('存在其他采集进程或未核验的采集锁')
            record=json.loads((self.root/'data/browser-launch.json').read_text(encoding='utf-8'))
            if not owned(record):raise ValueError('请先打开专用Chrome并人工登录')
            self.journal=Journal(self.root,shop,start,end)
            # Keep startup state in memory; only the collector owning BrowserLock
            # may mutate the journal. Do not overwrite another process's progress.
            self.original_stamp=self.journal.path.stat().st_mtime_ns if self.journal.path.exists() else None
            environment=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
            self.process=subprocess.Popen([sys.executable,str(self.root/'scripts/collect_reports.py'),
                '--attach','--generate','--shop',shop,'--start',start,'--end',end],cwd=self.root,
                env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.result='starting';self.message='正在连接专用Chrome';self.logs=[]
            threading.Thread(target=self._read,args=(self.process,),daemon=True).start()
            return self.status()

    def _read(self,process):
        for line in process.stdout:
            # Controlled script messages only; do not collect page requests/cookies.
            line=line.strip()
            if line and not line.startswith(('Traceback','  File','    ','warn(')):
                with self.lock:
                    if process is self.process:self.logs.append(line[:500])
        process.wait()
        with self.lock:
            if process is self.process:self.result='complete' if process.returncode==0 else 'needs_attention'

    def command(self,action):
        with self.lock:
            if not self.process or self.process.poll() is not None:raise ValueError('当前没有可继续的页面采集')
            if self.status()['state']!='paused':raise ValueError('采集未处于人工处理暂停状态')
            if action not in ('continue','quit'):raise ValueError('未知采集命令')
            self.process.stdin.write(action+'\n');self.process.stdin.flush()
            return {'message':'已提交继续核验' if action=='continue' else '已提交停止，保留进度'}

    def request_pause(self):
        with self.lock:
            if not self.process or self.process.poll() is not None:raise ValueError('当前没有运行中的页面采集')
            if self.status()['state']=='paused':raise ValueError('任务已经暂停')
            path=self.journal.directory/'control.json';temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps({'action':'pause'}),encoding='utf-8');temp.replace(path)
            return {'message':'暂停请求已提交，将在当前动作完成后的安全检查点暂停'}
