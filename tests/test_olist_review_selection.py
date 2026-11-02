"""Binary bounds independently enumerated; timestamp policy and cluster inference."""
import itertools
import json
import unittest

import duckdb
import numpy as np

from scripts.advanced_olist import ROOT, SQL, sha256
from scripts.olist_review_selection import contrast, scenario, tipping_frontier, cluster_intervals, PROTOCOL


class MissingOutcomeArithmetic(unittest.TestCase):
    def test_sharp_endpoints_match_independent_exhaustive_binary_assignments(self):
        counts=[[1,2,4],[2,3,5]];values=[]
        for assignment in itertools.product((0,1),repeat=4):
            values.append((1+sum(assignment[:2]))/4-(2+sum(assignment[2:]))/5)
        s=contrast(counts)
        self.assertAlmostEqual(s['bound_low'],min(values));self.assertAlmostEqual(s['bound_high'],max(values))
        self.assertAlmostEqual(scenario(counts,0,1),min(values));self.assertAlmostEqual(scenario(counts,1,0),max(values))

    def test_no_missing_outcomes_collapse_bounds_to_available_case(self):
        s=contrast([[1,4,4],[2,5,5]])
        self.assertEqual(s['bound_low'],s['bound_high']);self.assertEqual(s['bound_low'],s['complete_case_difference'])
        self.assertIsNone(tipping_frontier([[1,4,4],[2,5,5]],.5))

    def test_all_missing_is_unknown_not_zero_poor(self):
        s=contrast([[0,0,4],[0,0,5]])
        self.assertIsNone(s['complete_case_difference']);self.assertEqual((s['bound_low'],s['bound_high']),(-1,1))

    def test_group_exchangeability_assumption_reproduces_available_case_only_algebraically(self):
        c=[[1,2,4],[2,3,5]]
        self.assertAlmostEqual(scenario(c,.5,2/3),contrast(c)['complete_case_difference'])
        self.assertAlmostEqual(scenario(c,.5,tipping_frontier(c,.5)),0)
        self.assertGreater(tipping_frontier([[8,10,11],[1,10,11]],1),1)  # Preserve infeasible threshold.

    def test_invalid_counts_and_assumptions_are_rejected(self):
        for c in ([[2,1,4],[0,1,4]],[[0,1,0],[0,1,4]],[[0,.5,4],[0,1,4]],[[0,1,float('nan')],[0,1,4]]):
            with self.subTest(c=c),self.assertRaises(ValueError):contrast(c)
        for q in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):scenario([[1,2,4],[1,2,4]],q,.5)

    def test_joint_customer_bootstrap_is_deterministic_and_preserves_degenerate_estimates(self):
        counts=np.tile(np.array([[[1,2,4,2,3,5],[1,2,4,2,3,5],[1,2,4,2,3,5]]]),(8,1,1))
        limits,receipt=cluster_intervals(counts,iterations=100,seed=7)
        again,_=cluster_intervals(counts,iterations=100,seed=7)
        np.testing.assert_array_equal(limits,again)
        expected=contrast([[1,2,4],[2,3,5]])
        np.testing.assert_allclose(limits[:,:,0],expected['complete_case_difference'])
        np.testing.assert_allclose(limits[:,:,1],expected['bound_low'])
        self.assertEqual(receipt['customers'],8)
        counts[0,0,0]=3
        with self.assertRaises(ValueError):cluster_intervals(counts,iterations=100)

    def test_two_opposite_customer_clusters_retain_their_whole_order_histories(self):
        values=np.array([[[0,2,2,2,2,2]],[[2,2,2,0,2,2]]])
        limits,_=cluster_intervals(values,iterations=1000,seed=1)
        # Enumerating two customer draws gives contrasts -1, 0, +1 with 1/4,1/2,1/4 probability.
        self.assertEqual(limits[0,0,0],-1);self.assertEqual(limits[1,0,0],1)


class ReviewWindowPolicy(unittest.TestCase):
    def test_shared_mature_cohort_first_answer_ties_and_endpoint_boundaries(self):
        con=duckdb.connect()
        try:
            con.execute('''create table order_fact(order_id varchar,customer_unique_id varchar,order_status varchar,gmv double,
                purchased_at timestamp,delivered_at timestamp,estimated_at timestamp);
                insert into order_fact values
                ('a','u','delivered',10,'2017-01-01','2017-01-03 12:00','2017-01-03'),
                ('b','v','delivered',10,'2017-01-01','2017-01-05','2017-01-03'),
                ('c','w','delivered',10,'2018-05-01','2018-05-03','2018-05-03'),
                ('d','x','delivered',10,'2018-05-01','2018-05-04','2018-05-03'),
                ('e','y','canceled',10,'2017-01-01','2017-01-05','2017-01-03');
                create table raw_reviews(order_id varchar,review_score int,review_answer_timestamp timestamp,review_creation_date timestamp,review_id varchar);
                insert into raw_reviews values
                ('a',1,'2017-01-03 11:59','2017-01-03','early'),
                ('a',2,'2017-01-10 12:00','2017-01-10','first'),
                ('a',5,'2017-01-11','2017-01-11','later'),
                ('b',5,'2017-01-15','2017-01-14','b'),
                ('b',1,'2017-01-15','2017-01-14','a')''')
            text=(SQL/'review_selection.sql').read_text();first,rest=text.split(';',1)
            con.execute(first,{'start':'2017-01-01','cutoff':'2018-08-01','maximum_window':90})
            con.execute(rest,{'windows':[7,30,90],'cutoff':'2018-08-01','poor_max':2})
            self.assertEqual(con.execute('select count(*) from review_cohort').fetchone()[0],2)  # May 3 + 90 = cutoff, excluded.
            self.assertEqual(con.execute('select count(*) from review_observations').fetchone()[0],6)
            self.assertEqual(con.execute("select late,responded,poor from review_observations where order_id='a' and window_days=7").fetchone(),(False,True,True))
            self.assertEqual(con.execute("select responded,poor from review_observations where order_id='b' and window_days=7").fetchone(),(False,False))
            self.assertTrue(con.execute("select poor from review_observations where order_id='b' and window_days=30").fetchone()[0])
        finally:con.close()

    def test_committed_receipt_and_corner_grid_agree(self):
        import pandas as pd
        folder=ROOT/'docs/advanced-analysis'
        receipt=json.loads((folder/'review_selection_evidence.json').read_text())
        self.assertEqual(receipt['protocol_sha256'],sha256(PROTOCOL))
        self.assertEqual(receipt['protocol_sha256'],sha256(folder/'olist_review_protocol.json'))
        self.assertEqual(receipt['protocol'],json.loads(PROTOCOL.read_text()))
        self.assertEqual(receipt['query_sha256'],sha256(SQL/'review_selection.sql'))
        self.assertEqual(receipt['query_sha256'],sha256(folder/'review_selection.sql'))
        self.assertEqual(receipt['implementation_sha256'],sha256(ROOT/'scripts/olist_review_selection.py'))
        self.assertTrue(receipt['independent_raw_counts_reconciled'])
        self.assertFalse(receipt['causal_effect_identified'])
        for file,digest in receipt['aggregate_sha256'].items():self.assertEqual(sha256(folder/file),digest)
        grid=pd.read_csv(folder/'review_sensitivity.csv');summary=pd.read_csv(folder/'review_summary.csv')
        primary=summary[summary.window_days==30].iloc[0]
        self.assertAlmostEqual(grid.risk_difference.min(),primary.bound_low,places=10)
        self.assertAlmostEqual(grid.risk_difference.max(),primary.bound_high,places=10)


if __name__=='__main__':unittest.main()
