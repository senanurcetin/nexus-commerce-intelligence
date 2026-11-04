"""Independent original-cohort replay and explicit event-boundary sensitivity."""
from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pandas as pd

from scripts import delivery_association_audit as a
from scripts.advanced_olist import analyze,load_fact,cluster_risk_difference
from test_research_reproduction import write_fixture


def fixture(raw,published,*,double=False):
    write_fixture(raw);published.mkdir()
    if double:
        for name in a.FILES.values():
            p=raw/name;original=pd.read_csv(p,dtype=str,keep_default_na=False);copy=original.copy()
            for column in ('order_id','customer_id'):
                if column in copy:copy[column]=copy[column]+'-copy'
            pd.concat([original,copy],ignore_index=True).to_csv(p,index=False)
    con=duckdb.connect()
    try:quality=load_fact(con,raw);tables,summary=analyze(con,a.CUTOFF)
    finally:con.close()
    for key in ('delivery_months','delivery_common_support'):
        tables[key].to_csv(published/(key+'.csv'),index=False,float_format='%.10g',lineterminator='\n')
    e={'source_kind':'historical_public_olist','synthetic':False,'quality':quality,'summary':summary,
       'export_sha256':{k+'.csv':a.digest(published/(k+'.csv')) for k in ('delivery_months','delivery_common_support')}}
    (published/'evidence.json').write_text(json.dumps(e),encoding='utf-8')


class DeliveryAssociationAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name)
        fixture(cls.base/'raw',cls.base/'published')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def copy(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup);base=Path(directory.name)
        shutil.copytree(self.base/'raw',base/'raw');shutil.copytree(self.base/'published',base/'published')
        return base/'raw',base/'published'

    def edit(self,published,fn):
        p=published/'evidence.json';e=json.loads(p.read_text());fn(e);p.write_text(json.dumps(e),encoding='utf-8')

    def test_original_replay_uses_no_production_estimator_loader_or_quantile(self):
        with ExitStack() as stack:
            for name in ('load_fact','analyze','cluster_risk_difference'):
                stack.enter_context(patch('scripts.advanced_olist.'+name,side_effect=AssertionError('Production helper reused')))
            stack.enter_context(patch('numpy.quantile',side_effect=AssertionError('Production quantile reused')))
            result=a.audit(self.base/'raw',self.base/'published')
        self.assertEqual(result['acceptance'],'PASS',result)
        self.assertEqual(result['details']['association']['iterations'],1000)
        self.assertEqual(result['native_bi_acceptance'],'HOLD')
        self.assertNotIn('fixture-person-',json.dumps(result));self.assertFalse(result['raw_rows_exported'])
        self.assertFalse(result['details']['event_time_restricted_sensitivity']['genuine_point_in_time_backtest'])
        self.assertIsNone(result['details']['month_standardized_risk_difference'])

    def test_common_month_standardization_reconciles_and_rehashed_forgery_fails(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);raw=base/'raw';published=base/'published';fixture(raw,published,double=True)
            result=a.audit(raw,published);self.assertEqual(result['acceptance'],'PASS',result)
            self.assertGreater(result['details']['common_support_months'],0)
            p=published/'delivery_common_support.csv';data=pd.read_csv(p);data.loc[0,'risk_difference']=.99;data.to_csv(p,index=False)
            self.edit(published,lambda e:e['export_sha256'].update({p.name:a.digest(p)}))
            self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_weighted_bootstrap_matches_index_copy_reference(self):
        ledger=np.array([[1,2,0,1],[0,1,1,2],[1,1,0,2],[0,2,1,1]]*15)
        for seed in (7,20261027):
            independent=a.bootstrap(ledger,iterations=150,seed=seed)
            reference=cluster_risk_difference(ledger,iterations=150,seed=seed)
            self.assertEqual(independent,reference)

    def test_latest_review_order_and_event_boundary_reselect_earlier_answer(self):
        with tempfile.TemporaryDirectory() as td:
            raw=Path(td)
            tables={
                'customers':(['customer_id','customer_unique_id'],[(str(i),'fixture-sensitive-'+str(i)) for i in range(4)]),
                'orders':(['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'],[
                    ('0','0','delivered','2018-07-01','2018-07-03','2018-07-02'),
                    ('1','1','delivered','2018-07-01','2018-07-03','2018-07-03'),
                    ('2','2','delivered','2018-07-28','2018-08-01','2018-07-30'),
                    ('3','3','delivered','2018-07-25','2018-07-28','2018-07-28')]),
                'order_items':(['order_id','order_item_id','price','freight_value'],[(str(i),1,10,1) for i in range(4)]+[('0',2,20,1)]),
                'order_reviews':(['order_id','review_id','review_score','review_creation_date','review_answer_timestamp'],[
                    ('0','early',5,'2018-07-04','2018-07-04'),('0','latest',1,'2018-08-02','2018-08-02'),
                    ('1','z',1,'2018-07-04','2018-07-04'),('1','a',5,'2018-07-04','2018-07-04'),
                    ('1','null-time',5,'2018-09-01',''),
                    ('2','d',1,'2018-08-02','2018-08-02'),('3','cutoff',5,'2018-08-01','2018-08-01')])}
            for name,(header,records) in tables.items():
                with (raw/a.FILES[name]).open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.writer(stream,lineterminator='\n');writer.writerow(header);writer.writerows(records)
            ledger,_,all_timing,boundary,restricted,_=a.reconstruction(raw)
            np.testing.assert_array_equal(ledger.sum(axis=0),[2,2,1,2])
            np.testing.assert_array_equal(all_timing,[2,2,1,2])
            np.testing.assert_array_equal(restricted,[0,1,1,1])
            self.assertEqual(boundary['selected_answer_on_or_after_cutoff'],3)
            self.assertEqual(boundary['delivery_on_or_after_cutoff'],1)
            self.assertEqual(boundary['post_cutoff_latest_replaced_with_earlier_eligible_answer_orders'],1)

    def test_consistent_forged_interval_still_fails_replay(self):
        raw,published=self.copy();self.edit(published,lambda e:e['summary']['delivery_association'].update(ci_low=-.99,ci_high=.99))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_consistent_rehashed_monthly_forgery_fails_raw_counts(self):
        raw,published=self.copy();p=published/'delivery_months.csv';data=pd.read_csv(p);data.loc[0,'poor']+=1;data.to_csv(p,index=False)
        self.edit(published,lambda e:e['export_sha256'].update({p.name:a.digest(p)}))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_altered_standardization_or_all_timing_counts_are_rejected(self):
        raw,published=self.copy();self.edit(published,lambda e:e['summary'].update(month_standardized_risk_difference=.99))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')
        raw,published=self.copy();self.edit(published,lambda e:e['summary']['all_review_timing_sensitivity'].update(late_poor=9999))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_changed_input_during_validation_cannot_preserve_details_or_pass(self):
        raw,published=self.copy();original=a.validate
        def mutate(*args):
            result=original(*args);p=raw/a.FILES['customers'];p.write_bytes(p.read_bytes()+b'\n');return result
        with patch.object(a,'validate',side_effect=mutate):result=a.audit(raw,published)
        self.assertEqual(result['acceptance'],'FAIL');self.assertNotIn('details',result)

    def test_invalid_cluster_counts_or_group_support_raise(self):
        for values in (np.zeros((0,4)),np.zeros((3,3)),np.full((2,4),np.nan),np.array([[2,1,1,1]]),np.array([[1,1,0,0]])):
            with self.assertRaises(ValueError):a.bootstrap(values)

    def test_wrong_source_or_specification_and_missing_raw_files_fail(self):
        raw,published=self.copy();self.edit(published,lambda e:e.update(synthetic=True))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')
        raw,published=self.copy();self.edit(published,lambda e:e['summary']['delivery_association'].update(seed=7))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')
        self.assertEqual(a.audit(raw/'missing',published)['acceptance'],'FAIL')

    def test_cli_replaces_stale_pass_and_rejects_raw_input_output_overlap(self):
        raw,published=self.copy();out=published.parent/'result.json';out.write_text('{"acceptance":"PASS"}')
        p=raw/a.FILES['order_reviews'];p.write_bytes(p.read_bytes()+b'\n')
        command=[sys.executable,'-m','scripts.delivery_association_audit','--raw',str(raw),'--published',str(published),'--out',str(out)]
        result=subprocess.run(command,cwd=a.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(json.loads(out.read_text())['acceptance'],'FAIL')
        original=p.read_bytes();command[-1]=str(p)
        result=subprocess.run(command,cwd=a.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertEqual(p.read_bytes(),original)

    def test_committed_historical_receipt_binds_public_inputs_and_both_independent_implementations(self):
        receipt=json.loads((a.ROOT/'docs/delivery-association-validation.json').read_text())
        self.assertEqual(receipt['acceptance'],'PASS')
        self.assertEqual(receipt['implementation_sha256'],hashlib.sha256(Path(a.__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest())
        for key,value in receipt['input_sha256'].items():
            if key.startswith('published/'):path=a.ROOT/'docs/advanced-analysis'/key.split('/',1)[1]
            elif key=='independent_csv_helper':path=Path(a.helper.__file__)
            else:continue
            self.assertEqual(hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),value)
        details=receipt['details'];self.assertEqual(details['association']['customers'],82228)
        self.assertEqual(details['retrospective_event_boundary']['sample_orders'],84763)
        self.assertEqual(details['retrospective_event_boundary']['selected_answer_on_or_after_cutoff'],2761)
        self.assertEqual(details['retrospective_event_boundary']['post_cutoff_latest_replaced_with_earlier_eligible_answer_orders'],3)


if __name__=='__main__':unittest.main()
