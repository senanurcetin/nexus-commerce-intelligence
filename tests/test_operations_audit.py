"""Exercise the independent delivery replay with synthetic inputs in CI."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from scripts import operations_audit as audit
from scripts.advanced_olist import load_fact
from scripts.olist_delivery_operations import analyze
from test_research_reproduction import write_fixture


class OperationsAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        base = Path(directory.name)
        cls.raw = base / 'raw'
        cls.published = base / 'published'
        write_fixture(cls.raw)
        cls.published.mkdir()
        with duckdb.connect() as con:
            quality = load_fact(con, cls.raw)
            tables, summary = analyze(con)
        for name in audit.EXPORTS:
            tables[Path(name).stem].to_csv(cls.published / name, index=False,
                                          float_format='%.12g', lineterminator='\n')
        evidence = {
            'source_kind': 'historical_public_olist_operations',
            'quality': quality,
            'summary': summary,
            'aggregate_sha256': {name: audit.digest(cls.published / name) for name in audit.EXPORTS},
        }
        (cls.published / 'operations_evidence.json').write_text(json.dumps(evidence), encoding='utf-8')

    def test_replay_succeeds_without_production_estimator(self):
        with patch('scripts.olist_delivery_operations.analyze', side_effect=AssertionError('Reused estimator')):
            result = audit.audit(self.raw, self.published)
        self.assertEqual(result['acceptance'], 'PASS', result)
        self.assertGreater(result['details']['common_strata'], 0)

    def test_rehashed_stratum_contribution_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            published = Path(directory) / 'published'
            shutil.copytree(self.published, published)
            strata = published / 'operations_strata.csv'
            header, row, *rest = strata.read_text(encoding='utf-8').splitlines()
            fields = row.split(',')
            fields[header.split(',').index('mix_contribution')] = '0.99'
            strata.write_bytes(('\n'.join([header, ','.join(fields), *rest]) + '\n').encode())
            evidence_path = published / 'operations_evidence.json'
            evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
            evidence['aggregate_sha256'][strata.name] = audit.digest(strata)
            evidence_path.write_text(json.dumps(evidence), encoding='utf-8')
            self.assertEqual(audit.audit(self.raw, published)['acceptance'], 'FAIL')


class HistoricalReceiptTests(unittest.TestCase):
    def test_receipt_binds_public_evidence_and_replay_code(self):
        root = audit.ROOT
        receipt = json.loads((root / 'docs/operations-validation.json').read_text(encoding='utf-8'))
        evidence = json.loads((root / 'docs/advanced-analysis/operations_evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['acceptance'], 'PASS')
        paths = {
            **{f'published/{name}': root / 'docs/advanced-analysis' / name
               for name in ('operations_evidence.json', *audit.EXPORTS)},
            **{f'code/{name}': root / 'scripts' / name for name in (
                'operations_audit.py', 'delivery_association_audit.py', 'review_cluster_audit.py')},
        }
        expected = {key: hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                    for key, path in paths.items()}
        expected.update({f'raw/{name}': evidence['quality']['files'][name]['sha256'] for name in audit.RAW_FILES})
        self.assertEqual(receipt['input_sha256'], expected)


if __name__ == '__main__':
    unittest.main()
