"""Fixed-horizon design, exact-test cross-checks and honest synthetic provenance."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from scipy.stats import binomtest

from scripts import experiment_design as e


class ExperimentDesign(unittest.TestCase):
    def test_planning_matches_independent_published_method_reference(self):
        # statsmodels samplesize_proportions_2indep_onetail(-.01,.08,.8,
        # alpha=.05) = 10889.141620288427; runtime dependency is not required.
        self.assertEqual(e.planned_per_arm(.08,.07),10890)
        self.assertEqual(e.planned_per_arm(.07,.08),10890)
        self.assertGreater(e.planned_per_arm(.08,.075),10890)
        self.assertGreater(e.planned_per_arm(.08,.07,power=.9),10890)

    def test_invalid_probabilities_effects_and_counts_are_rejected(self):
        for p in (0,1,float('nan'),float('inf'),True,-.1):
            with self.subTest(p=p),self.assertRaises(ValueError):e.planned_per_arm(p,.07)
        with self.assertRaises(ValueError):e.planned_per_arm(.08,.08)
        for count,total in ((1.5,10),(-1,10),(11,10),(True,10),(0,0)):
            with self.subTest(count=count),self.assertRaises(ValueError):e.wilson(count,total)

    def test_wilson_matches_independent_scipy_score_intervals_at_boundaries(self):
        for count,total in ((0,100),(100,100),(1,10),(4,23),(50,100)):
            expected=binomtest(count,total).proportion_ci(method='wilson')
            low,high=e.wilson(count,total)
            self.assertAlmostEqual(low,expected.low,places=12);self.assertAlmostEqual(high,expected.high,places=12)

    def test_newcombe_matches_statsmodels_reference_and_preserves_direction(self):
        refs=[((5,8,1,7),(-.7475646253526181,.006759791473318011)),
              ((0,100,0,100),(-.03699349820698569,.03699349820698569)),
              ((100,100,0,100),(-1.,-.947683293116056))]
        for args,(low,high) in refs:
            r=e.analyze(*args);self.assertAlmostEqual(r['newcombe_ci_low'],low,places=12)
            self.assertAlmostEqual(r['newcombe_ci_high'],high,places=12)
            swapped=e.analyze(args[2],args[3],args[0],args[1])
            self.assertAlmostEqual(swapped['newcombe_ci_low'],-high,places=12)
            self.assertAlmostEqual(swapped['newcombe_ci_high'],-low,places=12)

    def test_fisher_matches_independent_fixed_margin_enumeration(self):
        # Seven treatment units out of fifteen; six total failures; observed one.
        probabilities=[math.comb(6,k)*math.comb(9,7-k)/math.comb(15,7) for k in range(7)]
        expected=sum(p for p in probabilities if p<=probabilities[1]+1e-14)
        self.assertAlmostEqual(e.analyze(5,8,1,7)['fisher_two_sided_p'],expected,places=12)

    def test_zero_and_all_event_arms_do_not_invent_zero_uncertainty(self):
        for count in (0,100):
            r=e.analyze(count,100,count,100)
            self.assertEqual(r['fisher_two_sided_p'],1.)
            self.assertLess(r['newcombe_ci_low'],0);self.assertGreater(r['newcombe_ci_high'],0)
            json.dumps(r,allow_nan=False)

    def test_early_extreme_result_withholds_inference_until_fixed_total(self):
        r=e.evaluate(50,50,0,50,1000,outcomes_complete=True,assignment_verified=True)
        self.assertEqual(r['gate'],'WAIT_FIXED_HORIZON');self.assertIsNone(r['inference'])

    def test_missing_outcomes_assignment_or_overrun_hold_inference(self):
        cases=[({'outcomes_complete':False,'assignment_verified':True},100,'HOLD_INCOMPLETE_OUTCOMES'),
               ({'outcomes_complete':True,'assignment_verified':False},100,'HOLD_ASSIGNMENT_UNVERIFIED'),
               ({'outcomes_complete':True,'assignment_verified':True},90,'HOLD_ENROLLMENT_OVERRUN')]
        for flags,target,status in cases:
            r=e.evaluate(4,50,3,50,target,**flags);self.assertEqual(r['gate'],status);self.assertIsNone(r['inference'])

    def test_sample_ratio_mismatch_holds_even_if_outcomes_look_favorable(self):
        r=e.evaluate(70,900,0,100,1000,outcomes_complete=True,assignment_verified=True)
        self.assertEqual(r['gate'],'HOLD_SAMPLE_RATIO_MISMATCH');self.assertIsNone(r['inference'])

    def test_complete_balanced_synthetic_result_never_automatically_recommends_adoption(self):
        r=e.evaluate(80,1000,40,1000,2000,outcomes_complete=True,assignment_verified=True)
        self.assertEqual(r['gate'],'READY_SYNTHETIC_FIXED_HORIZON')
        self.assertTrue(r['inference']['reject_equal_risk']);self.assertFalse(r['adoption_recommended'])
        self.assertFalse(r['inference']['causal_effect_execution_verified'])

    def test_simulation_is_reproducible_and_keeps_all_replicates(self):
        r=e.simulate(.08,.07,200,200,19)
        self.assertEqual(r,e.simulate(.08,.07,200,200,19))
        self.assertEqual(r['rejections'],r['benefit_rejections']+r['harm_rejections'])
        self.assertEqual(r['rejection_probability'],r['rejections']/200)
        self.assertLessEqual(r['decision_eligible_rejections'],r['rejections'])

    def test_empty_arm_simulations_are_counted_not_dropped(self):
        r=e.simulate(.08,.07,2,200,19)
        self.assertGreater(r['empty_arm_trials'],0);self.assertEqual(r['replicates'],200)
        self.assertEqual(r['rejection_probability'],r['rejections']/200)

    def test_published_simulation_is_explicitly_separate_and_content_addressed(self):
        folder=e.ROOT/'docs/experiment-design';r=json.loads((folder/'evidence.json').read_text())
        self.assertEqual(r['source_kind'],'synthetic_experiment_design');self.assertTrue(r['synthetic'])
        self.assertEqual(r['real_customers_enrolled'],0);self.assertFalse(r['adoption_recommended'])
        self.assertFalse(r['financial_roi_estimated']);self.assertFalse(r['causal_effect_execution_verified'])
        self.assertEqual(r['contract_sha256'],e.artifact_hash(e.CONTRACT))
        self.assertEqual(r['implementation_sha256'],hashlib.sha256(Path(e.__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest())
        for file,sha in r['artifacts_sha256'].items():self.assertEqual(e.artifact_hash(folder/file),sha)

    def test_invalid_changed_plan_invalidates_previous_success_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);out=root/'out';out.mkdir();receipt=out/'evidence.json';receipt.write_text('{"synthetic":true}')
            plan=json.loads(e.CONTRACT.read_text());plan['adoption_allowed']=True
            contract=root/'plan.json';contract.write_text(json.dumps(plan))
            with patch.object(e,'CONTRACT',contract):
                with self.assertRaisesRegex(ValueError,'Only a proposed'):e.build(out)
            self.assertFalse(receipt.exists())

    def test_full_temporary_design_build_reproduces_published_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);result=e.build(out)
            self.assertEqual(result['grid_scenarios'],9);self.assertEqual(result['simulation_scenarios'],3)
            self.assertEqual(result['planned_total_customers'],21780)
            self.assertTrue(result['design_inputs_stable_during_generation'])
            for name in ('sample_size_grid.csv','simulation.csv'):
                pd.testing.assert_frame_equal(pd.read_csv(out/name),pd.read_csv(e.ROOT/'docs/experiment-design'/name),check_exact=False,atol=1e-12,rtol=1e-12)
            for file,sha in result['artifacts_sha256'].items():self.assertEqual(e.artifact_hash(out/file),sha)


if __name__=='__main__':unittest.main()
