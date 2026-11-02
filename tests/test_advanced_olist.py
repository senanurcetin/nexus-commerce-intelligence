"""Boundary fixtures for Olist methods; no Kaggle/network access in tests."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
import json
import hashlib

import duckdb
import numpy as np
import pandas as pd

from scripts.advanced_olist import SQL, analyze, benjamini_hochberg, cluster_risk_difference, load_fact, shapley_change


class StatisticalMethods(unittest.TestCase):
    def test_published_aggregates_reconcile_without_raw_data(self):
        folder=SQL.parents[1]/'docs/advanced-analysis'
        evidence=json.loads((folder/'evidence.json').read_text())
        for name,digest in evidence['export_sha256'].items():
            self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),digest)
        monthly=pd.read_csv(folder/'monthly.csv')
        change=pd.read_csv(folder/'decomposition.csv')
        cohorts=pd.read_csv(folder/'cohorts.csv')
        self.assertAlmostEqual(monthly.gmv.sum(),evidence['summary']['gmv_source_units'],places=2)
        np.testing.assert_allclose(change[['order_volume','basket_size','unit_value']].sum(axis=1),change.gmv_change,rtol=0,atol=.005)
        np.testing.assert_allclose(monthly.gmv.diff().iloc[1:],change.gmv_change,rtol=0,atol=.005)
        self.assertTrue(cohorts[~cohorts.observable].retention.isna().all())
        m1=cohorts[(cohorts.period==1)&cohorts.observable]
        self.assertEqual(int(m1.active.sum()),evidence['summary']['m1_active'])
        self.assertAlmostEqual(m1.active.sum()/m1.customers.sum(),evidence['summary']['weighted_m1_retention'])
        states=pd.read_csv(folder/'delivery_states.csv')
        np.testing.assert_allclose(benjamini_hochberg(states.p_value),states.bh_q_value,atol=1e-9)

    def test_shapley_reconciles_and_is_symmetric(self):
        # Factors contribute differently; swapping inputs reverses every effect.
        a,b=[100,1.2,50],[135,1.1,65]
        effects=shapley_change(a,b)
        self.assertAlmostEqual(sum(effects),np.prod(b)-np.prod(a))
        np.testing.assert_allclose(shapley_change(b,a),-effects)
        np.testing.assert_allclose(shapley_change(a,a),[0,0,0])

    def test_one_factor_and_zero_start(self):
        np.testing.assert_allclose(shapley_change([0,2,3],[5,2,3]),[30,0,0])
        with self.assertRaises(ValueError): shapley_change([1,2,np.nan],[1,2,3])

    def test_bh_preserves_original_order_and_ties(self):
        np.testing.assert_allclose(benjamini_hochberg([.04,.001,.04,.8]),[.053333333,.004,.053333333,.8])
        self.assertEqual(len(benjamini_hochberg([])),0)
        with self.assertRaises(ValueError): benjamini_hochberg([1.01])

    def test_bootstrap_keeps_customer_vectors_and_is_reproducible(self):
        counts=np.array([[1,2,0,1],[1,2,1,3],[0,2,1,2],[2,3,0,2]])
        first=cluster_risk_difference(counts,iterations=150,seed=3)
        self.assertEqual(first,cluster_risk_difference(counts,iterations=150,seed=3))
        self.assertEqual(first['customers'],4)
        self.assertAlmostEqual(first['risk_difference'],4/9-2/8)
        self.assertLessEqual(first['ci_low'],first['ci_high'])
        with self.assertRaises(ValueError): cluster_risk_difference([[0,0,1,2]])
        with self.assertRaises(ValueError): cluster_risk_difference([[3,1,0,1]])


class SQLBoundaries(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect()
        self.con.execute('''create table order_fact(order_id varchar, customer_unique_id varchar,
            order_status varchar, purchased_at timestamp, delivered_at timestamp, gmv double)''')
        self.con.executemany('insert into order_fact values (?,?,?,?,?,?)',[
            ('old','old','delivered','2016-12-20','2016-12-25',20),
            ('old-repeat','old','delivered','2017-01-15','2017-01-20',20),
            ('a1','a','delivered','2017-01-20','2017-01-25',10),
            ('a2','a','delivered','2017-02-20','2017-02-25',10),
            ('a3','a','delivered','2017-02-21','2017-02-25',10),
            ('b1','b','delivered','2017-02-20','2017-02-25',10),
            ('c1','c','delivered','2017-02-20','2017-02-25',10),
            ('future-delivery','d','delivered','2017-02-20','2017-03-05',50),
            ('cancelled','e','canceled','2017-02-20',None,20),
            ('at-cutoff','f','delivered','2017-03-01','2017-03-05',20),
        ])

    def tearDown(self): self.con.close()

    def test_observed_zero_differs_from_future_and_counts_unique_customers(self):
        rows=self.con.execute((SQL/'cohorts.sql').read_text(),{
            'cutoff':datetime(2017,3,1),'cohort_start':datetime(2017,1,1),'periods':3}).df()
        jan=rows[rows.cohort==datetime(2017,1,1)].sort_values('period')
        feb=rows[rows.cohort==datetime(2017,2,1)].sort_values('period')
        self.assertEqual(jan.customers.tolist(),[1,1,1])  # old customer not reacquired
        self.assertEqual(jan.active.iloc[1],1)  # two February orders count once
        self.assertTrue(np.isnan(jan.retention.iloc[2]))
        self.assertFalse(bool(feb.observable.iloc[1]))
        # A later cutoff turns a future cell into a genuine zero.
        later=self.con.execute((SQL/'cohorts.sql').read_text(),{
            'cutoff':datetime(2017,4,1),'cohort_start':datetime(2017,1,1),'periods':3}).df()
        self.assertEqual(later[(later.cohort==datetime(2017,1,1)) & (later.period==2)].active.iloc[0],0)

    def test_rfm_ties_stay_together_and_future_delivery_is_excluded(self):
        rows=self.con.execute((SQL/'rfm.sql').read_text(),{'cutoff':datetime(2017,3,1)}).df()
        self.assertEqual(rows.customers.sum(),4)  # a,b,c,old; d not delivered as of cutoff
        singles=rows[rows.segment=='Single / recent'].iloc[0]
        self.assertEqual(singles.customers,2)
        self.assertEqual(singles.gmv,20)
        self.assertEqual(rows.orders.sum(),7)

    def test_review_and_item_many_sides_do_not_multiply_value(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory)
            (raw/'olist_orders_dataset.csv').write_text('order_id,customer_id,order_status,order_purchase_timestamp,order_delivered_customer_date,order_estimated_delivery_date\no,c,delivered,2017-01-01,2017-01-05,2017-01-04\n')
            (raw/'olist_customers_dataset.csv').write_text('customer_id,customer_unique_id,customer_state\nc,u,SP\n')
            (raw/'olist_order_items_dataset.csv').write_text('order_id,order_item_id,price,freight_value\no,1,10,2\no,2,20,3\n')
            (raw/'olist_order_reviews_dataset.csv').write_text('review_id,order_id,review_score,review_creation_date,review_answer_timestamp\nr1,o,1,2017-01-06,2017-01-07\nr2,o,5,2017-01-06,2017-01-08\n')
            con=duckdb.connect()
            try:
                receipt=load_fact(con,raw)
                self.assertEqual(con.execute('select gmv,items,review_score from order_fact').fetchone(),(30,2,5))
                self.assertEqual(receipt['extra_review_rows_collapsed'],1)
                # Same customer with both exposures keeps cluster resamples supported.
                con.execute("""insert into order_fact select * replace
                    ('o2' as order_id, timestamp '2017-01-03' as delivered_at)
                    from order_fact where order_id='o'""")
                con.execute("insert into raw_orders select * replace ('o2' as order_id) from raw_orders")
                con.execute("insert into raw_items select * replace ('o2' as order_id) from raw_items")
                tables,summary=analyze(con,datetime(2017,3,1),iterations=100)
                self.assertEqual(summary['delivery_association']['customers'],1)
                self.assertEqual(summary['delivery_association']['late_orders'],1)
                self.assertEqual(summary['delivery_association']['on_time_orders'],1)
                self.assertEqual(summary['m1_active'],0)
            finally: con.close()
            with (raw/'olist_customers_dataset.csv').open('a') as stream: stream.write('c,u,SP\n')
            con=duckdb.connect()
            try:
                with self.assertRaisesRegex(ValueError,'primary key'): load_fact(con,raw)
            finally: con.close()


if __name__=='__main__': unittest.main()
