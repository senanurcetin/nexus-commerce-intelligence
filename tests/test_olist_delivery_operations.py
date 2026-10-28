"""Comparable windows, Simpson reversal, common support and output contracts."""
import json
import unittest

import duckdb
import numpy as np
import pandas as pd

from scripts.advanced_olist import ROOT, SQL, sha256
from scripts.olist_delivery_operations import decompose_rates


class RateMixContracts(unittest.TestCase):
    def sample(self):
        return pd.DataFrame({'year':[2017,2017,2018,2018],'month':[1]*4,'state':['A','B','A','B'],
                             'orders':[900,100,100,900],'late_orders':[90,90,0,720]})

    def test_simpson_reversal_is_reconciled_not_misread_as_within_deterioration(self):
        rows,s=decompose_rates(self.sample())
        self.assertAlmostEqual(s['common_rate_change'],.54)
        self.assertAlmostEqual(s['within_contribution'],-.10)
        self.assertAlmostEqual(s['mix_contribution'],.64)
        self.assertAlmostEqual(s['pooled_standardized_rate_2017'],.5)
        self.assertAlmostEqual(s['pooled_standardized_rate_2018'],.4)
        self.assertAlmostEqual(rows.pooled_weight.sum(),1)

    def test_pooled_weights_are_not_mean_year_weights_when_sizes_differ(self):
        g=self.sample();g.loc[g.year==2018,['orders','late_orders']]*=2
        rows,s=decompose_rates(g)
        a=rows[rows.state=='A'].iloc[0]
        self.assertAlmostEqual(a.pooled_weight,1100/3000)
        self.assertAlmostEqual((a.weight_2017+a.weight_2018)/2,.5)
        self.assertNotAlmostEqual(s['pooled_standardized_rate_2017'],.5)
        self.assertAlmostEqual(s['common_rate_change'],.54)

    def test_support_exclusions_preserve_full_denominator_in_coverage(self):
        g=self.sample();g.loc[(g.year==2018)&(g.state=='B'),['orders','late_orders']]=[10,8]
        _,s=decompose_rates(g)
        self.assertEqual(s['common_strata'],1)
        self.assertAlmostEqual(s['common_coverage_2017'],.9)
        self.assertAlmostEqual(s['common_coverage_2018'],100/110)
        self.assertAlmostEqual(s['mix_contribution'],0)
        with self.assertRaisesRegex(ValueError,'No shared'):decompose_rates(g,minimum=1000)

    def test_invalid_counts_duplicate_keys_and_unmatched_months_fail(self):
        for col,value in [('orders',0),('orders',1.1),('late_orders',10000),('late_orders',-1),('month',8),('year',2016)]:
            g=self.sample();g[col]=g[col].astype(float);g.loc[0,col]=value
            with self.subTest(col=col,value=value),self.assertRaises(ValueError):decompose_rates(g)
        with self.assertRaisesRegex(ValueError,'Duplicate'):decompose_rates(pd.concat([self.sample(),self.sample().iloc[:1]]))

    def test_identity_is_invariant_to_input_order(self):
        _,first=decompose_rates(self.sample())
        _,second=decompose_rates(self.sample().sample(frac=1,random_state=2))
        self.assertEqual(first,second)


class OperationsEligibility(unittest.TestCase):
    def test_matched_months_calendar_deadline_and_missing_date_exclusion(self):
        con=duckdb.connect()
        try:
            con.execute('''create table order_fact(order_id varchar,customer_unique_id varchar,customer_state varchar,
                order_status varchar,gmv double,purchased_at timestamp,delivered_at timestamp,estimated_at timestamp)''')
            rows=[
                ('a','u1','SP','delivered',10,'2017-01-01','2017-01-03','2017-01-03'),
                ('b','u2','SP','delivered',10,'2017-01-01','2017-01-05','2017-01-03'),
                ('c','u3',None,'delivered',10,'2018-01-01','2018-01-02','2018-01-03'),
                ('d','u4','SP','delivered',10,'2018-08-01','2018-08-03','2018-08-03'),
                ('e','u5','SP','delivered',10,'2017-11-01','2017-11-03','2017-11-03'),
                ('f','u6','SP','delivered',10,'2018-01-01',None,'2018-01-03'),
                ('g','u7','SP','delivered',10,'2018-01-02','2018-01-01','2018-01-03'),
                ('h','u8','SP','canceled',10,'2018-01-01','2018-01-03','2018-01-03'),
                ('i','u9','SP','delivered',10,'2018-01-01','2018-01-03 14:00','2018-01-03'),
                ('j',None,'SP','delivered',10,'2018-01-01','2018-01-03','2018-01-03'),
            ]
            con.executemany('insert into order_fact values (?,?,?,?,?,?,?,?)',rows)
            con.execute((SQL/'delivery_operations.sql').read_text())
            self.assertEqual(con.execute('select count(*),sum(late::int) from operations_orders').fetchone(),(4,1))
            self.assertFalse(con.execute("select late from operations_orders where order_id='i'").fetchone()[0])
            self.assertEqual(con.execute("select state from operations_orders where order_id='c'").fetchone()[0],'Unknown state')
            # No review columns exist: eligibility is independent of review response.
        finally:con.close()

    def test_published_population_and_decomposition_contracts(self):
        folder=ROOT/'docs/advanced-analysis'
        evidence=json.loads((folder/'operations_evidence.json').read_text());s=evidence['summary']
        for name,digest in evidence['aggregate_sha256'].items():
            self.assertEqual(sha256(folder/name),digest)
            self.assertTrue({'order_id','customer_unique_id','product_id'}.isdisjoint(pd.read_csv(folder/name).columns))
        monthly=pd.read_csv(folder/'operations_monthly.csv');strata=pd.read_csv(folder/'operations_strata.csv')
        for year in (2017,2018):
            d=monthly[monthly.year==year]
            self.assertEqual(set(d.month),set(range(1,8)))
            self.assertEqual(d.orders.sum(),s[f'orders_{year}'])
            self.assertEqual(d.late_orders.sum(),s[f'late_orders_{year}'])
        self.assertAlmostEqual(strata.within_contribution.sum()+strata.mix_contribution.sum(),s['common_rate_change'],places=10)
        contributions=pd.read_csv(folder/'operations_month_contributions.csv')
        self.assertAlmostEqual(contributions.within_contribution.sum(),s['within_contribution'],places=10)
        dominant=contributions.loc[contributions.within_contribution.abs().idxmax()]
        self.assertEqual(int(dominant.month),s['dominant_within_month'])
        self.assertAlmostEqual(s['full_rate_2018']-s['full_rate_2017'],s['full_rate_change'])
        self.assertLessEqual(s['full_change_ci_low'],s['full_rate_change']);self.assertGreaterEqual(s['full_change_ci_high'],s['full_rate_change'])
        states=pd.read_csv(folder/'operations_states.csv')
        self.assertEqual(states.orders.sum(),s['orders_2018'])
        self.assertAlmostEqual(states.late_order_share.sum(),1)


if __name__=='__main__':unittest.main()
