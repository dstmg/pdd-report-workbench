"""Persistent per-shop/per-date tasks, with exclusive execution and revalidation."""
import hashlib
import json
import os
from pathlib import Path

from report_validation import validate


class BrowserLock:
    """One active collector across dates, preventing shared page/account races."""
    def __init__(self, root):
        directory = Path(root) / 'data'
        directory.mkdir(exist_ok=True)
        self.path = directory / 'browser-collection.lock'
        self.fd = None

    def __enter__(self):
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError('专用浏览器已有采集锁；核对进程后处理，不并发操作或自动清锁') from exc
        os.write(self.fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)
            self.path.unlink()


class Journal:
    def __init__(self, root, shop, start, end):
        self.shop, self.start, self.end = shop, start, end
        shop_key = hashlib.sha256(shop.encode('utf-8')).hexdigest()[:16]
        self.directory = Path(root) / 'data' / 'reports' / shop_key / f'{start}_{end}'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'collection.json'
        self.lock = self.directory / 'collection.lock'
        self.fd = None
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if (self.data['shop'], self.data['start'], self.data['end']) != (shop, start, end):
                raise ValueError('任务身份不一致')
        else:
            self.data = {'shop': shop, 'start': start, 'end': end, 'state': 'pending', 'tasks': {}}

    def __enter__(self):
        try:
            self.fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError('任务锁存在；请核对是否仍在运行，不自动删除锁') from exc
        os.write(self.fd, str(os.getpid()).encode())
        # Re-read after acquiring the task lock to avoid stale constructor data.
        if self.path.exists():
            try:
                latest=json.loads(self.path.read_text(encoding='utf-8'))
                if (latest['shop'],latest['start'],latest['end'])!=(self.shop,self.start,self.end):
                    raise ValueError('任务身份不一致')
                self.data=latest
            except Exception:
                os.close(self.fd);self.fd=None;self.lock.unlink()
                raise
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)
            self.lock.unlink()

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def task(self, category, mode):
        key = f'{category}_{mode}'
        return self.data['tasks'].setdefault(key, {'category': category, 'mode': mode, 'state': 'pending'})

    def completed(self, task):
        if task.get('state') not in ('validated', 'needs_validation', 'saving'):
            return False
        path = self.directory / task['file']
        if path.parent != self.directory:
            raise ValueError('任务文件路径无效')
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('下载接收未完成；先对账实际文件，不自动重复点击')
        result = validate(path, self.start, self.end, task['category'], task['mode'])
        if task.get('sha256') and result['sha256'] != task['sha256']:
            raise ValueError('已完成文件发生变化，停止恢复')
        task.update(state='validated', sha256=result['sha256'])
        self.save()
        return True
