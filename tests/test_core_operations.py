"""Operational decisions preserve grain and reject invalid duration records."""
import copy
import hashlib
import json
import unittest

import duckdb

from scripts import core_operations as operations


class CoreOperations(unittest.TestCase):
    def sample(self, records):
        con = duckdb.connect()
        self.addCleanup(con.close)
        con.execute('''create table "ecommerce.order_items" (
            id varchar, order_id varchar, user_id varchar, status varchar,
            created_at varchar, delivered_at varchar)''')
        con.executemany('insert into "ecommerce.order_items" values (?,?,?,?,?,?)', records)
        return operations.analyze(con, 1000)

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
