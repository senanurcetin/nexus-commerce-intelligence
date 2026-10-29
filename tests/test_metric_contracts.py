"""KPI definitions must name their population, denominator and implementation."""
import copy
import json
import re
import tempfile
from pathlib import Path
import unittest

from scripts.metric_contracts import ROOT,build,validate


class MetricContracts(unittest.TestCase):
    def setUp(self):self.registry=json.loads((ROOT/'contracts/metrics.json').read_text())

    def test_registry_is_complete_and_domain_scoped(self):
        metrics=validate(self.registry)
        self.assertEqual(len(metrics),20)
        self.assertEqual({m['domain'] for m in metrics},{'E-Commerce','Greenweez','Olist'})

    def test_duplicate_missing_denominator_and_foreign_source_are_rejected(self):
        duplicate=copy.deepcopy(self.registry);duplicate['metrics'].append(duplicate['metrics'][0])
        with self.assertRaisesRegex(ValueError,'Duplicate'):validate(duplicate)
        missing=copy.deepcopy(self.registry);del missing['metrics'][0]['denominator']
        with self.assertRaisesRegex(ValueError,'denominator'):validate(missing)
        mixed=copy.deepcopy(self.registry);mixed['metrics'][0]['sql']='analytics/olist/order_fact.sql'
        with self.assertRaisesRegex(ValueError,'crosses'):validate(mixed)

    def test_rendered_coverage_retains_synthetic_and_live_verification_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            result=build(evidence_dir=ROOT/'docs/analysis',out=Path(directory))
            text=(Path(directory)/'SOURCE_COVERAGE.md').read_text()
            self.assertFalse(result['live_queries_performed'])
            self.assertIn('synthetic item rows',text)
            self.assertIn('no cloud rows read',text)
            self.assertIn('selected order records',text)
            for filename in ('SOURCE_COVERAGE.md','KPI_CATALOG.md'):
                for link in re.findall(r'\]\(([^)]+)\)',(Path(directory)/filename).read_text()):
                    self.assertTrue((Path(directory)/link.strip('<>')).is_file(),link)


if __name__=='__main__':unittest.main()
