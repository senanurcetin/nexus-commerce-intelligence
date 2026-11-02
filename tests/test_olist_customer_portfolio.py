"""Adversarial survival/risk-set and product-grain fixtures; no raw downloads."""
from pathlib import Path
import json
import tempfile
import unittest
import warnings

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import CensoredData, ecdf

from scripts.advanced_olist import ROOT, SQL, sha256
from scripts.olist_customer_portfolio import kaplan_meier, product_analysis


class SurvivalContracts(unittest.TestCase):
    def test_real_aggregate_estimates_and_intervals_match_scipy(self):
        ledger=pd.read_csv(ROOT/'docs/advanced-analysis/repeat_ledger.csv')
        expanded=np.repeat(ledger.duration.to_numpy(),ledger.customers.to_numpy())
        event=np.repeat(ledger.event.to_numpy(),ledger.customers.to_numpy())
        reference=ecdf(CensoredData(uncensored=expanded[event],right=expanded[~event])).sf
        actual=kaplan_meier(ledger)
        np.testing.assert_allclose(actual.repeat_probability,1-reference.evaluate(actual.day),atol=1e-12)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)  # S=1 interval undefined at day zero.
            interval=reference.confidence_interval(method='log-log')
        np.testing.assert_allclose(actual.ci_low,1-interval.high.evaluate(actual.day),atol=1e-12,equal_nan=True)
        np.testing.assert_allclose(actual.ci_high,1-interval.low.evaluate(actual.day),atol=1e-12,equal_nan=True)

    def test_known_product_limit_and_exhausted_risk_set(self):
        ledger=pd.DataFrame({'duration':[1,2,3],'event':[True,False,True],'customers':[1,1,1]})
        c=kaplan_meier(ledger,4)
        np.testing.assert_allclose(c.at_risk,[3,3,2,1,0])
        np.testing.assert_allclose(c.repeat_probability.iloc[:4],[0,1/3,1/3,1])
        self.assertTrue(pd.isna(c.repeat_probability.iloc[4]))
        self.assertTrue(pd.isna(c.ci_low.iloc[0]));self.assertTrue(pd.isna(c.ci_low.iloc[3]))
        self.assertLess(c.ci_low.iloc[1],1/3);self.assertGreater(c.ci_high.iloc[1],1/3)

    def test_tied_events_precede_censor_removal_and_day_zero_censoring(self):
        ledger=pd.DataFrame({'duration':[0,1,1,2],'event':[False,True,False,True],'customers':[2,1,1,1]})
        c=kaplan_meier(ledger,2)
        self.assertEqual(c.at_risk.iloc[1],3)
        self.assertAlmostEqual(c.repeat_probability.iloc[1],1/3)
        self.assertEqual(c.at_risk.iloc[2],1)

    def test_aggregated_and_expanded_counts_agree(self):
        grouped=pd.DataFrame({'duration':[1,2,3],'event':[True,False,False],'customers':[3,5,2]})
        expanded=grouped.loc[grouped.index.repeat(grouped.customers)].assign(customers=1)
        pd.testing.assert_frame_equal(kaplan_meier(grouped,3),kaplan_meier(expanded,3))

    def test_invalid_time_count_and_indicator_are_rejected(self):
        for duration,event,n in [(-1,True,1),(.5,True,1),(1,True,0),(1,True,1.5),(1,'yes',1),(float('nan'),False,1)]:
            with self.subTest(duration=duration,event=event,n=n),self.assertRaises(ValueError):
                kaplan_meier(pd.DataFrame({'duration':[duration],'event':[event],'customers':[n]}))

    def test_distinct_days_prior_history_and_exclusive_cutoff(self):
        con=duckdb.connect()
        try:
            con.execute('create table order_fact(customer_unique_id varchar,purchased_at timestamp,order_status varchar,gmv double)')
            con.executemany('insert into order_fact values (?,?,?,?)',[
                ('a','2017-01-01 10:00','delivered',10),('a','2017-01-01 11:00','delivered',20),
                ('a','2017-01-02','delivered',10),('old','2016-12-30','delivered',10),
                ('old','2017-01-03','delivered',10),('late','2018-07-31','delivered',10),
                ('late','2018-08-01','delivered',10),('not','2017-01-01','canceled',20)])
            r=con.execute((SQL/'customer_lifetimes.sql').read_text(),{'cutoff':pd.Timestamp('2018-08-01').to_pydatetime()}).df()
            self.assertEqual(r.customers.sum(),2)
            event=r[r.event].iloc[0];censor=r[~r.event].iloc[0]
            self.assertEqual(event.duration,1)
            self.assertEqual(censor.duration,0);self.assertEqual(censor.available_days,0)
        finally: con.close()

    def test_committed_outputs_match_grouped_lifetable_and_hashes(self):
        folder=ROOT/'docs/advanced-analysis'
        evidence=json.loads((folder/'extension_evidence.json').read_text())
        for name,digest in evidence['aggregate_sha256'].items():
            self.assertEqual(sha256(folder/name),digest)
            table=pd.read_csv(folder/name)
            self.assertTrue({'order_id','product_id','customer_unique_id'}.isdisjoint(table.columns))
        curve=kaplan_meier(pd.read_csv(folder/'repeat_ledger.csv'))
        published=pd.read_csv(folder/'repeat_curve.csv')
        np.testing.assert_allclose(curve.repeat_probability,published.repeat_probability,atol=1e-12,equal_nan=True)
        p=pd.read_csv(folder/'product_concentration.csv').iloc[0]
        self.assertAlmostEqual(p.hhi*p.effective_product_count,1)
        self.assertAlmostEqual(pd.read_csv(folder/'category_portfolio.csv').gmv.sum(),p.gmv,places=2)


class PortfolioGrain(unittest.TestCase):
    def fixture(self,raw):
        (raw/'olist_order_items_dataset.csv').write_text('order_id,order_item_id,product_id,price\no1,1,p1,10\no2,1,p2,20\no2,2,p3,10\n')
        (raw/'olist_products_dataset.csv').write_text('product_id,product_category_name\np1,a\np2,b\n')
        (raw/'product_category_name_translation.csv').write_text('product_category_name,product_category_name_english\na,Category A\nb,Category B\n')
        con=duckdb.connect()
        con.execute("create table raw_items as select order_id,order_item_id,price from read_csv_auto(?)",[str(raw/'olist_order_items_dataset.csv')])
        con.execute('''create table order_fact(order_id varchar,purchased_at timestamp,order_status varchar,gmv double);
            insert into order_fact values ('o1','2017-01-01','delivered',10),('o2','2017-02-01','delivered',30)''')
        return con

    def test_unknown_products_preserved_and_category_orders_are_incidences(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory);con=self.fixture(raw)
            try:
                tables,summary=product_analysis(con,raw)
                self.assertEqual(summary['coverage']['missing_product_lines'],1)
                self.assertEqual(summary['gmv'],40)
                self.assertAlmostEqual(summary['hhi'],.375)
                self.assertEqual(tables['category_portfolio'].category_order_incidences.sum(),3)
                self.assertIn('Unknown category',tables['category_portfolio'].category.tolist())
            finally: con.close()

    def test_duplicate_translation_cannot_expand_sales(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory);con=self.fixture(raw)
            with (raw/'product_category_name_translation.csv').open('a') as stream: stream.write('a,Duplicate\n')
            try:
                with self.assertRaisesRegex(ValueError,'dimension key'): product_analysis(con,raw)
            finally: con.close()


if __name__=='__main__': unittest.main()
