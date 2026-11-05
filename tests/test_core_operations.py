"""Operational decisions preserve grain and reject invalid duration records."""
import copy
import csv
import hashlib
import json
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import duckdb

from scripts import core_operations as operations


class CoreOperations(unittest.TestCase):
    def connection(self, records):
        con = duckdb.connect()
        self.addCleanup(con.close)
        con.execute('''create table "ecommerce.order_items" (
            id varchar, order_id varchar, user_id varchar, status varchar,
            created_at varchar, delivered_at varchar)''')
        con.executemany('insert into "ecommerce.order_items" values (?,?,?,?,?,?)', records)
        return con

    def sample(self, records):
        return operations.analyze(self.connection(records), 1000)

    def test_materialized_partition_is_private_complete_and_idempotent(self):
        con = self.connection([
            ('good', 'a', 'u', 'Complete', '100', '200'),
            ('reverse', 'b', 'v', 'Returned', '200', '100'),
            ('future', 'c', 'w', 'Complete', '100', '2000'),
            ('missing', 'd', 'x', 'Complete', None, '200'),
            ('pending', 'e', 'y', 'Processing', '100', None),
        ])
        operations.analyze(con, 1000)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = operations.export_delivery_inputs(con, root, 1000, 'source', 'code')
            self.assertEqual(first['eligible_item_rows'], 1)
            self.assertEqual(first['quarantined_item_rows'], 3)
            self.assertEqual(first['invalid_eligible_rows'], 0)
            self.assertEqual(first, operations.export_delivery_inputs(con, root, 1000, 'source', 'code'))
            folder, = root.iterdir()
            with (folder / 'eligible_delivery_items.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
                self.assertEqual([r['id'] for r in rows], ['good'])
                self.assertEqual(rows[0]['source_created_at'], '100')
                self.assertEqual(rows[0]['source_delivered_at'], '200')
            with (folder / 'quarantined_delivery_items.csv').open(newline='') as stream:
                self.assertEqual({r['id'] for r in csv.DictReader(stream)}, {'reverse', 'future', 'missing'})
            later = operations.export_delivery_inputs(con, root, 3000, 'source', 'code')
            self.assertEqual(later['eligible_item_rows'], 2)
            self.assertEqual(len(list(root.iterdir())), 2)
            path = folder / 'eligible_delivery_items.csv'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                operations.export_delivery_inputs(con, root, 1000, 'source', 'code')

    def test_failed_export_leaves_no_partial_artifact(self):
        con = self.connection([('good', 'a', 'u', 'Complete', '100', '200')])
        operations.analyze(con, 1000)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(operations, 'file_hash', side_effect=OSError('Injected export failure')):
                with self.assertRaises(OSError):
                    operations.export_delivery_inputs(con, root, 1000, 'source', 'code')
            self.assertEqual(list(root.iterdir()), [])

    def test_item_and_order_grains_and_timestamp_exclusions(self):
        result = self.sample([
            ('1', 'a', 'u', 'Complete', '100', '200'),
            ('2', 'a', 'u', 'Complete', '100', '50'),
            ('3', 'b', 'v', 'Returned', 'nan', '200'),
            ('4', 'c', 'w', 'Complete', '100', '2000'),
            ('5', 'd', 'x', 'Processing', '100', '200'),
        ])
        self.assertEqual(result['item_rows'], 5)
        self.assertEqual(result['distinct_order_keys'], 4)
        self.assertEqual(result['terminal_item_rows'], 4)
        self.assertEqual(result['duration_eligible_rows'], 1)
        self.assertEqual(result['reversed_delivery_rows'], 1)

    def test_ambiguous_orders_are_reported(self):
        result = self.sample([
            ('1', 'a', 'u', 'Complete', '100', '200'),
            ('2', 'a', 'v', 'Cancelled', '100', None),
            ('3', None, None, 'Unknown', '100', None),
        ])
        self.assertEqual(result['mixed_status_orders'], 1)
        self.assertEqual(result['ambiguous_customer_orders'], 1)
        self.assertEqual(result['missing_order_key_item_rows'], 1)

    def test_duplicate_item_keys_reject_analysis(self):
        with self.assertRaisesRegex(ValueError, 'Unique'):
            self.sample([
                ('1', 'a', 'u', 'Complete', '100', '200'),
                ('1', 'a', 'u', 'Complete', '100', '200'),
            ])

    def test_current_receipt_code_population_and_decision_conservation(self):
        folder = operations.ROOT / 'docs/core-source'
        result = json.loads((folder / 'operations.json').read_text())
        source = json.loads((folder / 'status.json').read_text())
        operations.validate(result, source)
        code_hash = hashlib.sha256(operations.IMPLEMENTATION.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        self.assertEqual(result['implementation_sha256'], code_hash)
        self.assertFalse(result['financial_amounts_published'])
        for field in ('id', 'order_id', 'user_id', 'sale_price', 'cost'):
            self.assertNotIn('"' + field + '"', json.dumps(result))
        forged = copy.deepcopy(result)
        forged['summary']['duration_eligible_rows'] += 1
        with self.assertRaises(ValueError):
            operations.validate(forged, source)
        forged = copy.deepcopy(result)
        forged['decision']['repair_chronology'] = False
        with self.assertRaises(ValueError):
            operations.validate(forged, source)


if __name__ == '__main__':
    unittest.main()
