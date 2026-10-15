"""OS-owned lock; crash releases ownership, never unlink a live lock file."""
import os
from pathlib import Path

class ProcessLock:
    def __init__(self,path):self.path=Path(path);self.stream=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=self.path.open('a+b')
        try:
            self.stream.seek(0);legacy=self.stream.read()
            if legacy and not legacy.startswith(b'OSLOCK1'):
                raise RuntimeError('发现旧版锁，请先核对原采集进程；不自动删除旧锁')
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.stream.seek(0);self.stream.truncate();self.stream.write(b'OSLOCK1 '+str(os.getpid()).encode());self.stream.flush()
            return self
        except Exception:
            self.stream.close();self.stream=None
            raise RuntimeError('采集锁被占用，或存在未核验的旧版锁；请核对后重试')
    def __exit__(self,*args):
        if self.stream:
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_UN)
            self.stream.close();self.stream=None
