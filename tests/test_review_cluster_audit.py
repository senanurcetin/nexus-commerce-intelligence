"""Independent raw reconstruction, cluster replay and adversarial receipt checks.

All generated rows and outputs are temporary SYNTHETIC fixtures, not findings.
"""
from contextlib import ExitStack
import csv
from datetime import datetime,timedelta
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

from scripts import review_cluster_audit as a
from scripts.advanced_olist import load_fact
from scripts.olist_review_selection import analyze,cluster_intervals


def fixture(raw,published):
    raw.mkdir();published.mkdir();tables={
        'orders':(['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'],[]),
        'customers':(['customer_id','customer_unique_id','customer_state'],[]),
        'order_items':(['order_id','order_item_id','price','freight_value'],[]),
        'order_reviews':(['order_id','review_id','review_score','review_creation_date','review_answer_timestamp'],[])}
    for i in range(120):
        for late in (False,True):
            key=f'fixture-{i}-{late}';purchase=datetime(2017,1,1);delivery=purchase+timedelta(days=5 if late else 3,hours=12)
            tables['orders'][1].append((key,key,'delivered',purchase,delivery,purchase+timedelta(days=3)))
            tables['customers'][1].append((key,f'fixture-person-{i}','SP'))
            tables['order_items'][1].extend([(key,1,10,1),(key,2,20,1)])
            if i%11==0:continue  # absent dated answer
            delay=-1 if i%13==0 else (7 if i%4==0 else 20 if i%4==1 else 60 if i%4==2 else 2)
            answered=delivery+timedelta(days=delay);score=1 if i%3==0 or (late and i%5==0) else 5
            tables['order_reviews'][1].append((key,'b',5,answered,answered))
            # Equal answer/creation timestamps: review ID 'a' wins despite input order.
            tables['order_reviews'][1].append((key,'a',score,answered,answered))
            tables['order_reviews'][1].append((key,'later',5,answered+timedelta(days=1),answered+timedelta(days=1)))
    # Maturity equality at the cutoff is excluded, not admitted by <=.
    tables['orders'][1].append(('boundary','boundary','delivered','2018-05-01','2018-05-03','2018-05-03'))
    tables['customers'][1].append(('boundary','boundary-private-id','SP'))
    tables['order_items'][1].append(('boundary',1,10,1))
    for key,(header,data) in tables.items():
        with (raw/a.FILES[key]).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream,lineterminator='\n');writer.writerow(header);writer.writerows(data)
    plan=json.loads((a.ROOT/'contracts/olist_review_protocol.json').read_text())
    con=duckdb.connect()
    try:quality=load_fact(con,raw);aggregates,bootstrap=analyze(con,plan)
    finally:con.close()
    for name,table in aggregates.items():table.to_csv(published/(name+'.csv'),index=False,float_format='%.12g',lineterminator='\n')
    evidence={'source_kind':'historical_public_olist_review_selection','synthetic':False,
        'protocol':plan,'protocol_sha256':a.digest(a.ROOT/'contracts/olist_review_protocol.json'),
        'quality':quality,'bootstrap':bootstrap,'summary':aggregates['review_summary'].to_dict('records'),
        'aggregate_sha256':{name+'.csv':a.digest(published/(name+'.csv')) for name in aggregates}}
    (published/'review_selection_evidence.json').write_text(json.dumps(evidence),encoding='utf-8')


class ReviewClusterAudit(unittest.TestCase):
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

    def edit_evidence(self,published,change):
        path=published/'review_selection_evidence.json';e=json.loads(path.read_text());change(e);path.write_text(json.dumps(e),encoding='utf-8')

    def test_replay_is_independent_of_production_helpers_and_quantiles(self):
        with ExitStack() as stack:
            for name in ('analyze','raw_control','cluster_intervals','contrast'):
                stack.enter_context(patch('scripts.olist_review_selection.'+name,side_effect=AssertionError('Production helper reused')))
            stack.enter_context(patch('scripts.advanced_olist.load_fact',side_effect=AssertionError('Production loader reused')))
            stack.enter_context(patch('numpy.quantile',side_effect=AssertionError('Production quantile reused')))
            result=a.audit(self.base/'raw',self.base/'published')
        self.assertEqual(result['acceptance'],'PASS',result)
        self.assertEqual(result['details']['eligible_orders'],240)
        self.assertEqual(result['details']['customers'],120)
        self.assertEqual(result['details']['sampling_limits_replayed'],18)
        text=json.dumps(result)
        self.assertNotIn('fixture-person-',text);self.assertNotIn('boundary-private-id',text)
        self.assertFalse(result['raw_rows_exported']);self.assertEqual(result['native_bi_acceptance'],'HOLD')

    def test_scalar_percentiles_match_numpy_linear_order_statistics(self):
        values=[-9,.5,.5,1,3,7,50]
        for q in (0,.025,.1,.5,.975,1):self.assertAlmostEqual(a.percentile(values,q),np.quantile(values,q))
        for values,q in (([],.5),([1],-1),([1],float('nan'))):
            with self.assertRaises(ValueError):a.percentile(values,q)

    def test_loop_replay_agrees_with_batched_reference_with_shared_customer_windows(self):
        plan=json.loads((a.ROOT/'contracts/olist_review_protocol.json').read_text())
        ledgers,_,_,_=a.reconstruct(self.base/'raw',plan)
        observed,meta=a.replay(ledgers,1000,20261029)
        expected,reference=cluster_intervals(ledgers,iterations=1000,seed=20261029)
        np.testing.assert_allclose(observed,expected,atol=1e-15,rtol=0)
        self.assertEqual(meta['valid_replicates'],reference['valid_replicates'])

    def test_raw_hash_mismatch_fails_without_exporting_content(self):
        raw,published=self.copy();p=raw/a.FILES['order_reviews'];p.write_bytes(p.read_bytes()+b'\n')
        result=a.audit(raw,published);self.assertEqual(result['acceptance'],'FAIL');self.assertNotIn('details',result)

    def test_consistent_csv_json_and_checksum_interval_forgery_fails_arithmetic(self):
        raw,published=self.copy();p=published/'review_summary.csv';data=pd.read_csv(p)
        data.loc[data.window_days==30,'complete_case_ci_low']=-.9;data.to_csv(p,index=False)
        def forge(e):
            e['aggregate_sha256'][p.name]=a.digest(p)
            next(r for r in e['summary'] if r['window_days']==30)['complete_case_ci_low']=-.9
        self.edit_evidence(published,forge)
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_rehashed_duplicate_items_are_rejected(self):
        raw,published=self.copy();p=raw/a.FILES['order_items'];lines=p.read_text().splitlines();p.write_text('\n'.join(lines+[lines[1]])+'\n')
        self.edit_evidence(published,lambda e:e['quality']['files'][p.name].update(sha256=a.digest(p),bytes=p.stat().st_size,rows=len(lines)))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_changed_customer_clustering_with_matching_source_hash_is_detected(self):
        raw,published=self.copy();p=raw/a.FILES['customers'];data=pd.read_csv(p)
        # Same total customer identities; move one on-time order into another cluster.
        data.loc[1,'customer_unique_id']=data.loc[2,'customer_unique_id'];data.to_csv(p,index=False)
        self.edit_evidence(published,lambda e:e['quality']['files'][p.name].update(sha256=a.digest(p),bytes=p.stat().st_size))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_changed_availability_reason_and_checksum_is_detected(self):
        raw,published=self.copy();p=published/'review_availability.csv';data=pd.read_csv(p);data.loc[0,'orders']+=1;data.to_csv(p,index=False)
        self.edit_evidence(published,lambda e:e['aggregate_sha256'].update({p.name:a.digest(p)}))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_consistently_rehashed_protocol_redefinition_is_rejected(self):
        raw,published=self.copy();protocol=published.parent/'protocol.json'
        plan=json.loads((a.ROOT/'contracts/olist_review_protocol.json').read_text())
        plan['review_policy']='latest answer instead of first answer'
        protocol.write_text(json.dumps(plan),encoding='utf-8')
        self.edit_evidence(published,lambda e:e.update(protocol=plan,protocol_sha256=a.digest(protocol)))
        self.assertEqual(a.audit(raw,published,protocol)['acceptance'],'FAIL')

    def test_synthetic_or_wrong_study_provenance_cannot_become_historical_acceptance(self):
        raw,published=self.copy()
        self.edit_evidence(published,lambda e:e.update(synthetic=True))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')
        self.edit_evidence(published,lambda e:e.update(synthetic=False,source_kind='historical_public_olist'))
        self.assertEqual(a.audit(raw,published)['acceptance'],'FAIL')

    def test_input_change_during_replay_never_preserves_pass(self):
        raw,published=self.copy();original=a.validate
        def mutate(*args):
            result=original(*args);p=raw/a.FILES['customers'];p.write_bytes(p.read_bytes()+b'\n');return result
        with patch.object(a,'validate',side_effect=mutate):result=a.audit(raw,published)
        self.assertEqual(result['acceptance'],'FAIL');self.assertNotIn('details',result)

    def test_invalid_cluster_counts_and_unsupported_groups_fail(self):
        for values in (np.zeros((0,3,6)),np.ones((3,2,6)),np.full((3,3,6),-.5),np.full((3,3,6),float('nan'))):
            with self.assertRaises(ValueError):a.replay(values,1000,1)
        with self.assertRaisesRegex(ValueError,'support'):a.replay(np.zeros((3,3,6)),1000,1)

    def test_cli_failed_run_replaces_previous_pass_and_protects_raw_outputs(self):
        raw,published=self.copy();out=published.parent/'result.json';out.write_text('{"acceptance":"PASS"}')
        p=raw/a.FILES['orders'];p.write_bytes(p.read_bytes()+b'\n')
        command=[sys.executable,'-m','scripts.review_cluster_audit','--raw',str(raw),'--published',str(published),'--out',str(out)]
        result=subprocess.run(command,cwd=a.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(json.loads(out.read_text())['acceptance'],'FAIL')
        original=p.read_bytes();command[-1]=str(p)
        result=subprocess.run(command,cwd=a.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertEqual(p.read_bytes(),original)

    def test_committed_historical_receipt_binds_public_inputs_and_implementation(self):
        p=a.ROOT/'docs/review-cluster-validation.json';receipt=json.loads(p.read_text())
        self.assertEqual(receipt['acceptance'],'PASS')
        self.assertEqual(receipt['implementation_sha256'],hashlib.sha256(Path(a.__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest())
        for key,value in receipt['input_sha256'].items():
            if key.startswith('published/'):path=a.ROOT/'docs/advanced-analysis'/key.split('/',1)[1]
            elif key=='protocol':path=a.ROOT/'contracts/olist_review_protocol.json'
            else:continue  # Historical raw files are separately acquired, never CI inputs.
            self.assertEqual(hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),value)
        self.assertEqual(receipt['details']['eligible_orders'],68448)
        self.assertEqual(receipt['details']['customers'],66295)


if __name__=='__main__':unittest.main()
