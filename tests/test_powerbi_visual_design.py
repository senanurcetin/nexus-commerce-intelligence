"""Native authoring contracts: filter scope, units, comparison grain and rebuilds.

These checks inspect PBIR/TMDL; they do not execute DAX or render Power BI.
"""
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.build_olist_powerbi import ROOT,NAME,TABLES,MEASURES,create
from scripts.powerbi_design import METHOD_LABELS


class NativeVisualDesign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory();cls.out=Path(cls.directory.name)
        cls.project=create(ROOT/'docs/advanced-analysis',cls.out)
        cls.pages=cls.project.parent/(NAME+'.Report/definition/pages')
        cls.model=cls.project.parent/(NAME+'.SemanticModel/definition/tables')

    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()

    def visuals(self,page):return {p.parent.name:json.loads(p.read_text()) for p in (self.pages/page/'visuals').glob('*/visual.json')}

    def interactions(self,page):return {(r['source'],r['target']):r['type'] for r in json.loads((self.pages/page/'page.json').read_text())['visualInteractions']}

    def test_forecast_date_and_method_have_different_declared_filter_targets(self):
        page='olist_forecasting';v=self.visuals(page);rules=self.interactions(page)
        plot='00000000000000000004';bars='00000000000000000005';card='00000000000000000001'
        self.assertEqual(rules['nexus_filter_1',plot],'DataFilter')
        self.assertEqual(rules['nexus_filter_1',card],'NoFilter')
        self.assertEqual(rules['nexus_filter_2',plot],'DataFilter')
        self.assertEqual(rules['nexus_filter_2',card],'DataFilter')
        self.assertEqual(rules['nexus_filter_2',bars],'NoFilter')
        self.assertEqual(rules[bars,'nexus_filter_2'],'NoFilter')
        self.assertIn("'Past-MAE selector'",json.dumps(v['nexus_filter_2']))
        self.assertTrue(v['nexus_filter_2']['visual']['objects']['selection'][0]['properties']['singleSelect']['expr']['Literal']['Value']=='true')
        self.assertEqual(v['nexus_filter_1']['position']['height'],80)

    def test_all_four_method_curves_are_available_without_summing_duplicated_actuals(self):
        source=pd.read_csv(ROOT/'docs/advanced-analysis/forecast_daily.csv');source=source[source.phase=='evaluation']
        self.assertEqual(len(source),840);self.assertEqual(source.groupby('day').actual_orders.nunique().max(),1)
        model=(self.model/'ForecastDaily.tmdl').read_text()
        for method in METHOD_LABELS:self.assertIn(method,model)
        self.assertIn('TREATAS({m}, ForecastDaily[method])',model)
        self.assertIn('MAX(ForecastDaily[actual_orders])',model)
        self.assertNotIn('SUM(ForecastDaily[actual_orders])',model)
        metrics=(self.model/'ForecastMetrics.tmdl').read_text()
        self.assertIn('REMOVEFILTERS(ForecastMetrics)',metrics)
        for label in METHOD_LABELS.values():self.assertIn(label,metrics)

    def test_fixed_association_and_operations_estimates_are_not_subgroup_recalculations(self):
        rules=self.interactions('olist_delivery')
        for name in ('nexus_filter_1','nexus_filter_2'):
            self.assertEqual(rules[name,'00000000000000000001'],'NoFilter')
        for formula,_ in MEASURES['Association'].values():
            self.assertIn('100 *',formula);self.assertIn('REMOVEFILTERS(Association)',formula)
        rules=self.interactions('olist_operations')
        self.assertEqual(rules['nexus_filter_1','00000000000000000004'],'DataFilter')
        self.assertEqual(rules['nexus_filter_2','00000000000000000004'],'NoFilter')
        self.assertEqual(rules['nexus_filter_2','00000000000000000005'],'DataFilter')

    def test_retention_totals_number_formats_and_uncertainty_are_preserved(self):
        cohort=(self.model/'Cohorts.tmdl').read_text()
        self.assertIn('HASONEVALUE(Cohorts[period])',cohort)
        self.assertIn('formatString: 0.00%',cohort)
        horizons=(self.model/'RepeatHorizons.tmdl').read_text()
        self.assertIn('column mature_customers\n\t\tformatString: #,0',horizons)
        self.assertIn('column mature_repeat_rate\n\t\tformatString: 0.00%',horizons)
        visual=self.visuals('olist_repeat_timing')['00000000000000000001']
        styles=visual['visual']['objects']['lineStyles']
        self.assertEqual(len(styles),3)
        self.assertTrue(all(s['properties']['lineChartType']['expr']['Literal']['Value']=="'step'" for s in styles))
        self.assertEqual(self.visuals('olist_repeat_timing')['00000000000000000002']['visual']['visualType'],'tableEx')

    def test_decomposition_has_a_native_driver_chart_and_exact_lookup(self):
        v=self.visuals('olist_decomposition')
        self.assertEqual(v['00000000000000000001']['visual']['visualType'],'stackedColumnChart')
        self.assertEqual(len(v['00000000000000000001']['visual']['query']['queryState']['Y']['projections']),3)
        self.assertEqual(v['00000000000000000002']['visual']['visualType'],'tableEx')
        self.assertIn('adjacent-month',json.dumps(v['nexus_metric_note']).lower())

    def test_build_is_idempotent_and_never_adds_cross_source_relationships(self):
        before={p.relative_to(self.project.parent).as_posix():p.read_bytes() for p in self.project.parent.rglob('*') if p.is_file()}
        create(ROOT/'docs/advanced-analysis',self.out)
        after={p.relative_to(self.project.parent).as_posix():p.read_bytes() for p in self.project.parent.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertFalse(list(self.model.parent.glob('*relationships*')))
        receipt=json.loads((self.project.parent/'visual_design.json').read_text())
        self.assertEqual(sum(r['slicers'] for r in receipt['pages']),14)
        self.assertFalse(receipt['native_render_verified']);self.assertFalse(receipt['dax_engine_executed'])
        self.assertEqual(len(list(self.model.glob('*.tmdl'))),len(TABLES))


if __name__=='__main__':unittest.main()
