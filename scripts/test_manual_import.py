"""Portable synthetic XLSX and crash-lock regression tests."""
import base64,io,json,subprocess,sys,tempfile,unittest,warnings
from pathlib import Path
from unittest.mock import patch
import openpyxl
import dashboard_data
from manual_import import preview,import_files
from process_lock import ProcessLock
from collection_state import BrowserLock
from report_validation import METRICS
ROOT=Path(__file__).resolve().parents[1]

def request(mode='分天数据',amount=10):
    book=openpyxl.Workbook();book.remove(book.active)
    names=['汇总数据','商品'] if mode=='分天数据' else ['商品']
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for name in names:
            sheet=book.create_sheet(f'{name}_{mode}_20260101至20260101')
            header=(['日期'] if mode=='分天数据' else [])+(['商品ID','商品名称','推广场景'] if name=='商品' else [])+list(METRICS)
            values=(['2026-01-01'] if mode=='分天数据' else [])+(['100','合成商品','合成场景'] if name=='商品' else [])+[amount]*len(METRICS)
            sheet.append(header);sheet.append(values)
    stream=io.BytesIO();book.save(stream);book.close()
    return {'shop':'合成验收店铺','start':'2026-01-01','end':'2026-01-01','confirmed':True,'files':[{'name':f'商品推广_{mode}_20260101至20260101.xlsx','content':base64.b64encode(stream.getvalue()).decode()}]}

class ImportTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def read(self,id):
        with patch.object(dashboard_data,'ROOT',self.root):return dashboard_data.dataset(id)
    def test_daily_then_pair_and_duplicate(self):
        r=request();self.assertEqual(preview(r)['files'][0]['mode'],'分天数据')
        first=import_files(r,self.root);data=self.read(first['id']);self.assertTrue(data['partial']);self.assertTrue(data['hasDaily']);self.assertFalse(data['reconciled']);self.assertEqual(len(data['daily']),1)
        self.assertIn('新增0份',import_files(r,self.root)['message'])
        second=import_files(request('汇总数据'),self.root);data=self.read(second['id']);self.assertTrue(data['reconciled']);self.assertFalse(data['partial']);self.assertEqual(len(data['sources']),2)
    def test_summary_only_and_review_rejected(self):
        id=import_files(request('汇总数据'),self.root)['id'];data=self.read(id)
        self.assertFalse(data['hasDaily']);self.assertEqual(data['daily'],[])
        from review_store import snapshot
        with patch('review_store.dataset',return_value=data),self.assertRaises(ValueError):snapshot({'batch':id})
    def test_conflict_and_pair_mismatch_preserves_manifest(self):
        first=import_files(request(),self.root);path=self.root/'data/reports'/first['id']/'collection.json';before=path.read_bytes()
        with self.assertRaises(ValueError):import_files(request(amount=20),self.root)
        with self.assertRaises(ValueError):import_files(request('汇总数据',20),self.root)
        self.assertEqual(path.read_bytes(),before)
    def test_confirmation_date_type_and_filename(self):
        for change in ({'confirmed':False},{'start':'2025-12-31'}):
            with self.assertRaises(ValueError):import_files({**request(),**change},self.root)
        r=request();r['files'][0]['name']='../report.xlsx'
        with self.assertRaises(ValueError):preview(r)
        r=request();r['files'][0]['name']='直播推广_分天数据_20260101至20260101.xlsx'
        with self.assertRaises(ValueError):preview(r)
    def test_exclusive_and_legacy_lock(self):
        with BrowserLock(self.root):
            with self.assertRaises(RuntimeError):
                with BrowserLock(self.root):pass
        with BrowserLock(self.root):pass
        path=self.root/'legacy.lock';path.write_text('123')
        with self.assertRaises(RuntimeError):
            with ProcessLock(path):pass
        self.assertEqual(path.read_text(),'123')
    def test_process_crash_releases_lock(self):
        path=self.root/'crash.lock'
        code="import sys,time;sys.path.insert(0,sys.argv[1]);from process_lock import ProcessLock;g=ProcessLock(sys.argv[2]);g.__enter__();print('locked',flush=True);time.sleep(60)"
        process=subprocess.Popen([sys._base_executable,'-c',code,str(ROOT/'scripts'),str(path)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'locked')
            with self.assertRaises(RuntimeError):
                with ProcessLock(path):pass
        finally:process.kill();process.wait(timeout=10);process.stdout.close()
        with ProcessLock(path):pass

if __name__=='__main__':unittest.main()
