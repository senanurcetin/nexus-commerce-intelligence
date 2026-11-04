"""Published agreement is insufficient: replay formulas and reject forged outputs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import analysis_audit as a


class AnalysisAcceptance(unittest.TestCase):
    def fixture(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        root=Path(directory.name);folder=root/'docs/advanced-analysis';folder.mkdir(parents=True)
        for original in (a.ROOT/'docs/advanced-analysis').iterdir():
            if original.suffix in {'.csv','.json'}:shutil.copyfile(original,folder/original.name)
        return root,folder

    def test_actual_published_calculations_replay_but_business_and_native_gates_stay_open(self):
        with patch('scripts.olist_forecast.predictions',side_effect=AssertionError('Do not reuse estimator')),patch('scripts.olist_forecast.block_interval',side_effect=AssertionError('Do not reuse bootstrap')),patch('scripts.olist_review_selection.contrast',side_effect=AssertionError('Do not reuse bounds')):
            result=a.audit()
        self.assertEqual(result['published_calculation_acceptance'],'PASS',result['checks'])
        checks={r['name']:r['details'] for r in result['checks']}
        self.assertEqual(checks['independent_forecast_replay']['evaluation_weeks'],30)
        self.assertEqual(checks['independent_forecast_replay']['methods_replayed'],4)
        self.assertFalse(checks['independent_forecast_replay']['primary_superiority_demonstrated'])
        self.assertTrue(checks['independent_missing_rating_replay']['primary_bounds_include_zero'])
        self.assertFalse(checks['independent_missing_rating_replay']['customer_cluster_sampling_intervals_replayed'])
        for key in ('financial_semantics_acceptance','native_bi_acceptance','operational_forecast_acceptance'):
            self.assertEqual(result[key],'HOLD')
        stored=json.loads((a.ROOT/'docs/analysis-validation.json').read_text())
        self.assertEqual(stored['implementation_sha256'],result['implementation_sha256'])
        self.assertEqual(stored['published_calculation_acceptance'],'PASS')
        stored_checks={r['name']:r['details'] for r in stored['checks']}
        self.assertEqual(stored_checks['input_snapshot'],checks['input_snapshot'])
        for key,value in checks['independent_forecast_replay']['primary_interval'].items():
            a.near(stored_checks['independent_forecast_replay']['primary_interval'][key],value,'Stale committed replay result')

    def test_future_training_endpoint_is_rejected(self):
        _,folder=self.fixture();p=folder/'forecast_daily.csv';data=pd.read_csv(p)
        data.loc[0,'training_end']=data.loc[0,'origin'];data.to_csv(p,index=False)
        with self.assertRaisesRegex(ValueError,'future training endpoint'):a.forecast(folder)

    def test_wrong_past_selector_choice_is_rejected(self):
        _,folder=self.fixture();p=folder/'forecast_daily.csv';data=pd.read_csv(p)
        index=data.index[data.method=='past_mae_selector'][0];data.loc[index,'chosen_model']='weekday_mean_28';data.to_csv(p,index=False)
        with self.assertRaisesRegex(ValueError,'Selector differs'):a.forecast(folder)

    def test_matching_forged_positive_uncertainty_csv_and_receipt_still_fail_replay(self):
        _,folder=self.fixture();p=folder/'forecast_uncertainty.csv';data=pd.read_csv(p)
        data.loc[data.block_weeks==4,['ci_low','ci_high']]=[1.,3.];data.to_csv(p,index=False)
        p=folder/'forecast_evidence.json';receipt=json.loads(p.read_text())
        for row in receipt['paired_uncertainty']:
            if row['block_weeks']==4:row.update(ci_low=1.,ci_high=3.)
        p.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'uncertainty CSV does not replay'):a.forecast(folder)

    def test_matching_forged_review_csv_and_receipt_still_fail_count_identity(self):
        _,folder=self.fixture();p=folder/'review_summary.csv';data=pd.read_csv(p)
        data.loc[data.window_days==30,'bound_low']=.05;data.to_csv(p,index=False)
        p=folder/'review_selection_evidence.json';receipt=json.loads(p.read_text())
        for row in receipt['summary']:
            if row['window_days']==30:row['bound_low']=.05
        p.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'differs from outcome counts'):a.reviews(folder)

    def test_missing_assumption_scenario_is_rejected(self):
        _,folder=self.fixture();p=folder/'review_sensitivity.csv';pd.read_csv(p).iloc[:-1].to_csv(p,index=False)
        with self.assertRaisesRegex(ValueError,'Incomplete or duplicate'):a.reviews(folder)

    def test_stale_executive_summary_is_rejected_by_combined_evidence_control(self):
        root,_=self.fixture();reproduction=json.loads((a.ROOT/'docs/research_reproduction.json').read_text())
        from scripts.executive_readout import INPUTS
        names=set(reproduction['pipeline_inputs_sha256'])|set(INPUTS)|{'docs/research_reproduction.json','docs/EXECUTIVE_READOUT.md','docs/executive_readout.json'}
        for name in names:
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.ROOT/name,dest)
        legacy=root/'scripts/build_powerbi.py';lf=legacy.read_bytes().replace(b'\r\n',b'\n')
        for raw in (lf,lf.replace(b'\n',b'\r\n')):
            legacy.write_bytes(raw);self.assertTrue(a.evidence(root)['reproduction_fingerprints_current'])
        legacy.write_bytes(lf+b'\n# Additional text must not bypass the historical fingerprint\n')
        with self.assertRaisesRegex(ValueError,'pipeline fingerprint is stale'):a.evidence(root)
        legacy.write_bytes(lf)
        (root/'docs/EXECUTIVE_READOUT.md').write_text('An obsolete positive forecast recommendation')
        with self.assertRaisesRegex(ValueError,'Executive readout is stale'):a.evidence(root)

    def test_failed_cli_overwrites_stale_pass_receipt_and_returns_nonzero(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup);root=Path(directory.name)
        output=root/'result.json';output.write_text('{"published_calculation_acceptance":"PASS"}')
        result=subprocess.run([sys.executable,'-m','scripts.analysis_audit','--root',str(root),'--out',str(output)],cwd=a.ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(output.read_text())['published_calculation_acceptance'],'FAIL')

    def test_unknown_metrics_cannot_be_replaced_with_zero_and_nonfinite_values_fail(self):
        a.near(np.array([np.nan,np.nan]),None,'unknown')
        a.near(np.array([1.,np.nan]),np.array([1.,np.nan]),'mixed unknown')
        for actual,expected in ((0,None),(float('inf'),1),(0,float('nan'))):
            with self.subTest(actual=actual),self.assertRaises(ValueError):a.near(actual,expected,'invalid')

    def test_changed_inputs_during_validation_cannot_produce_pass(self):
        with patch.object(a,'fingerprints',side_effect=[{'source':'before'},{'source':'after'}]):result=a.audit()
        self.assertEqual(result['published_calculation_acceptance'],'FAIL')
        self.assertFalse(next(c for c in result['checks'] if c['name']=='input_stability')['passed'])


if __name__=='__main__':unittest.main()
