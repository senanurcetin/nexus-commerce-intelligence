"""Real five-study build on bounded SYNTHETIC data, never portfolio evidence.

No mocked analysis/export stages, network, Kaggle credentials or cloud source.
The fixture is temporary and its outputs must never replace public Olist files.
"""
import csv
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import pandas as pd

from scripts.build_research import build
from scripts.research_environment import LOCK,inspect


def write_fixture(raw):
    raw.mkdir()
    tables={
        'olist_orders_dataset.csv':(['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'],[]),
        'olist_customers_dataset.csv':(['customer_id','customer_unique_id','customer_state'],[]),
        'olist_order_items_dataset.csv':(['order_id','order_item_id','product_id','price','freight_value'],[]),
        'olist_order_reviews_dataset.csv':(['review_id','order_id','review_score','review_creation_date','review_answer_timestamp'],[]),
        'olist_products_dataset.csv':(['product_id','product_category_name'],[(f'fixture-product-{i}','category-'+str(i%2)) for i in range(8)]),
        'product_category_name_translation.csv':(['product_category_name','product_category_name_english'],[('category-0','Category A'),('category-1','Category B')])}
    counts={'orders':0,'items':0,'reviews':0,'cancelled':0,'placed_in_window':0,'delivered_in_window':0}
    start=date(2016,12,15)
    for day in range((date(2018,8,11)-start).days):
        purchased=start+timedelta(days=day)
        for group in range(2+(day%17==0)):
            key=f'fixture-order-{day}-{group}';customer=f'fixture-customer-{day}-{group}'
            cancelled=group==2;delivered=purchased+timedelta(days=7 if group else 3)
            tables['olist_orders_dataset.csv'][1].append((key,customer,'canceled' if cancelled else 'delivered',purchased,'' if cancelled else delivered,purchased+timedelta(days=5)))
            # Both delivery groups share clusters; repeat days are 150/180 days apart.
            period=180 if day%2 else 150
            tables['olist_customers_dataset.csv'][1].append((customer,f'fixture-person-{day%2}-{day%period}','SP'))
            counts['orders']+=1;counts['cancelled']+=cancelled
            inside=date(2017,1,1)<=purchased<date(2018,8,1)
            counts['placed_in_window']+=inside;counts['delivered_in_window']+=inside and not cancelled
            for item in range(1,2+(day%10==0)):
                tables['olist_order_items_dataset.csv'][1].append((key,item,f'fixture-product-{day%8}',10+day%7+item,2))
                counts['items']+=1
            if cancelled or day%7==0:continue
            answered=delivered+timedelta(days=-1 if day%11==0 else 20 if day%13==0 else 2)
            score=1 if (day%3==0 if group else day%5==0) else 5
            tables['olist_order_reviews_dataset.csv'][1].append((f'fixture-review-{day}-{group}',key,score,answered,answered))
            counts['reviews']+=1
            if day%19==0:
                tables['olist_order_reviews_dataset.csv'][1].append((f'fixture-review-later-{day}-{group}',key,4,answered+timedelta(days=1),answered+timedelta(days=1)))
                counts['reviews']+=1
    for name,(header,rows) in tables.items():
        with (raw/name).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream,lineterminator='\n');writer.writerow(header);writer.writerows(rows)
    return counts


class ResearchReproduction(unittest.TestCase):
    def test_clean_five_study_success_path_reconciles_raw_to_native_package(self):
        with tempfile.TemporaryDirectory(prefix='nexus-synthetic-research-') as td:
            root=Path(td);raw=root/'raw';out=root/'out';counts=write_fixture(raw)
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()}
            result=build(raw,out)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(len(result['analytical_reports']),5)
            self.assertFalse(result['desktop_render_verified']);self.assertFalse(result['dax_engine_executed'])
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()})
            core=json.loads((out/'evidence.json').read_text())
            self.assertIsNone(core['summary']['month_standardized_risk_difference'])
            self.assertIn('**not estimable** across 0 months',(out/'REPORT.md').read_text(encoding='utf-8'))
            self.assertIn('not estimable at this boundary',(out/'CUSTOMER_PORTFOLIO.md').read_text(encoding='utf-8'))
            extension=json.loads((out/'extension_evidence.json').read_text())
            self.assertIsNone(extension['summary']['repeat']['repeat_day_90']['ci_low'])
            self.assertEqual(core['quality']['order_fact_rows'],counts['orders'])
            monthly=pd.read_csv(out/'monthly.csv')
            self.assertEqual(int(monthly.orders.sum()),counts['delivered_in_window'])
            forecast=json.loads((out/'forecast_evidence.json').read_text())
            self.assertEqual(forecast['placed_orders'],counts['placed_in_window'])
            self.assertEqual((forecast['evaluation_weeks'],forecast['evaluation_days']),(30,210))
            self.assertGreater(counts['placed_in_window'],counts['delivered_in_window'])
            for name in ('extension_evidence.json','operations_evidence.json','review_selection_evidence.json','forecast_evidence.json'):
                receipt=json.loads((out/name).read_text())
                self.assertEqual(receipt['quality']['files'],core['quality']['files'])
                for file,digest in receipt['aggregate_sha256'].items():
                    self.assertEqual(hashlib.sha256((out/file).read_bytes()).hexdigest(),digest)
            archive=out/result['archive']
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),result['archive_sha256'])
            with ZipFile(archive) as bundle:
                names=bundle.namelist()
                self.assertEqual(sum(n.endswith('/page.json') for n in names),9)
                self.assertEqual(sum('/tables/' in n and n.endswith('.tmdl') for n in names),16)
                self.assertEqual(sum(n.endswith('.png') and '/' not in n for n in names),12)
                for report in result['analytical_reports']:self.assertIn(report,names)
                for name in names:
                    self.assertNotIn('fixture-order-',bundle.read(name).decode('utf-8',errors='ignore'))
            self.assertEqual(result['environment']['lock_sha256'],hashlib.sha256(LOCK.read_bytes()).hexdigest())
            self.assertTrue(result['pipeline_inputs_stable_during_build'])
            self.assertIn('contracts/olist_forecast_protocol.json',result['pipeline_inputs_sha256'])

    def test_environment_receipt_reports_actual_versions_without_claiming_native_acceptance(self):
        result=inspect()
        self.assertIn('numpy',result['packages'])
        self.assertEqual(len(result['lock_sha256']),64)
        self.assertEqual(result['matches_research_lock'],result['python_311'] and not result['mismatched_or_missing_packages'])


if __name__=='__main__':unittest.main()
