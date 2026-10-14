"""Portable audit regression tests: no merchant files, browser or account required."""
import copy
import tempfile
import unittest
from collection_state import Journal
from metrics_catalog import numeric
from report_validation import number,reconcile
from browser_session import dates

class AuditTests(unittest.TestCase):
    def test_journal_reload_under_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            stale=Journal(directory,'合成测试店铺','2026-01-01','2026-01-07')
            with Journal(directory,'合成测试店铺','2026-01-01','2026-01-07') as first:
                first.task('商品推广','分天数据')['state']='submitting';first.save()
            with stale:
                self.assertEqual(stale.task('商品推广','分天数据')['state'],'submitting')

    def test_non_finite_numbers_rejected(self):
        for fn in (numeric,number):
            for value in ('NaN','Infinity','-Infinity'):
                with self.assertRaises(ValueError):fn(value)

    def test_overview_and_product_disagreement_rejected(self):
        def sheet(name,value):return {'name':name,'sums':{'总花费(元)':value},'unavailable':[]}
        daily={'start':'2026-01-01','end':'2026-01-07','category':'商品推广','mode':'分天数据',
               'sheets':[sheet('汇总数据_分天数据_20260101至20260107','11'),sheet('商品_分天数据_20260101至20260107','10')]}
        summary={**daily,'mode':'汇总数据','sheets':[sheet('商品_汇总数据_20260101至20260107','10')]}
        with self.assertRaises(ValueError):reconcile(daily,summary)

    def test_history_parameters_not_limited_to_sample(self):
        self.assertEqual(dates('2026-07-15','2026-10-12'),('2026-07-15','2026-10-12'))
        self.assertEqual(dates('2026-07-01','2026-07-31'),('2026-07-01','2026-07-31'))

if __name__=='__main__':unittest.main()
