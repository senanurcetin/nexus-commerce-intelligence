"""Greenweez bridge tests: synthetic CI-only fixtures; no production finance claims."""
from __future__ import annotations

from datetime import date, datetime, timezone
import copy
import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from scripts import greenweez_bridge as bridge


def fixture_tables():
    return {
        "daily": [
            {"date": "2023-01-02", "transactions": 2, "revenue": 150.0,
             "operational_margin": 40.0, "ads_cost": 10.0,
             "ads_margin": 30.0, "ads_impression": 1000, "ads_clicks": 25},
            {"date": "2023-01-03", "transactions": 1, "revenue": 50.0,
             "operational_margin": 20.0, "ads_cost": 5.0,
             "ads_margin": 15.0, "ads_impression": 500, "ads_clicks": 25},
        ],
        "monthly": [
            {"datemonth": "2023-01-01", "transactions": 3, "revenue": 200.0,
             "operational_margin": 60.0, "ads_cost": 15.0,
             "ads_margin": 45.0, "ads_impression": 1500, "ads_clicks": 50},
        ],
        "marketing_source": [
            {"datemonth": "2023-01-01", "paid_source": "adwords",
             "ads_cost": 10.0, "impressions": 1000, "clicks": 25,
             "cpc": 0.4, "ctr": 0.025, "spend_share": .6667},
            {"datemonth": "2023-01-01", "paid_source": "facebook",
             "ads_cost": 5.0, "impressions": 500, "clicks": 25,
             "cpc": .2, "ctr": .05, "spend_share": .3333},
        ],
        "refunds": [],
    }


def manifest(tables=None, provenance="synthetic_demo"):
    source_tables = tables if tables is not None else fixture_tables()
    return {
        "schema_version": bridge.SCHEMA_VERSION,
        "source_system": bridge.SOURCE,
        "provenance": provenance,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": "f" * 64,
        "tables": source_tables,
        "row_counts": {name: len(rows) for name, rows in source_tables.items()},
    }


def create_db(path: Path, tables=None):
    rows = tables or fixture_tables()
    conn = duckdb.connect(str(path))
    try:
        conn.execute("create schema analytics_finance")
        conn.execute("create schema analytics_marketing")
        for key in ("daily", "monthly", "marketing_source"):
            name = bridge.TABLE_NAMES[key]
            cols = bridge.TABLE_COLUMNS[key]
            schema = []
            for col in cols:
                coltype = ("DATE" if col in ("date", "datemonth") else
                           "VARCHAR" if col == "paid_source" else
                           "INTEGER" if col in bridge.WHOLE else "DOUBLE")
                schema.append(col + " " + coltype)
            conn.execute(f"create table {name} ({', '.join(schema)})")
            for row in rows[key]:
                conn.execute(
                    f"insert into {name} values ({', '.join('?' for _ in cols)})",
                    [row[col] for col in cols],
                )
    finally:
        conn.close()


class GreenweezBridgeTests(unittest.TestCase):
    def test_export_real_mart_schema_read_only_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "demo.duckdb"
            out = root / "export" / "snapshot.json"
            create_db(db)
            result = bridge.export_from_duckdb(db, out)
            self.assertEqual(result["row_counts"]["daily"], 2)
            self.assertEqual(result["row_counts"]["monthly"], 1)
            self.assertEqual(result["provenance"], "synthetic_demo")
            self.assertEqual(result["tables"]["marketing_source"][0]["paid_source"], "adwords")
            self.assertEqual(bridge.load_snapshot(out), result)
            self.assertEqual(len(result["source_sha256"]), 64)
            self.assertNotIn("customer", out.read_text().lower())
            self.assertNotIn("email", out.read_text().lower())

    def test_explicit_external_is_always_marked_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "gsheet_real.duckdb"
            create_db(db)
            result = bridge.export_from_duckdb(
                db, root / "external.json", provenance="external_unverified",
            )
            self.assertEqual(result["provenance"], "external_unverified")
            self.assertNotIn("verified", set(bridge.PROVENANCE))
            with self.assertRaisesRegex(ValueError, "Source provenance"):
                bridge.export_from_duckdb(db, root / "bad.json", provenance="real_verified")

    def test_missing_external_never_invents_zero_finance(self):
        with tempfile.TemporaryDirectory() as temp:
            absent = Path(temp) / "not-there.json"
            self.assertIsNone(bridge.load_snapshot(absent))
            with self.assertRaises(FileNotFoundError):
                bridge.export_from_duckdb(absent, Path(temp) / "out.json")

    def test_reject_joined_domains_wrong_source_unknown_manifest(self):
        base = manifest()
        for update in (
            {"source_system": "nexus_lab_ga4"},
            {"provenance": "verified"},
            {"schema_version": 99},
            {"row_counts": {"daily": 2}},
            {"source_sha256": "bad"},
        ):
            bad = copy.deepcopy(base)
            bad.update(update)
            with self.assertRaises(ValueError):
                bridge.validate_snapshot(bad)

    def test_reject_tampered_aggregate_and_revenue_cross_grain(self):
        base = manifest()
        for path, value in (
            (("daily", 0, "ads_margin"), 800),
            (("monthly", 0, "revenue"), 9900),
            (("monthly", 0, "ads_cost"), 11),
            (("marketing_source", 0, "ads_cost"), 8),
        ):
            bad = copy.deepcopy(base)
            name, idx, col = path
            bad["tables"][name][idx][col] = value
            with self.assertRaises(ValueError):
                bridge.validate_snapshot(bad)

    def test_unknown_column_duplicate_grain_nan_and_negative_spend_fail(self):
        base = manifest()
        mutations = []
        a = copy.deepcopy(base)
        a["tables"]["daily"][0]["revenue_from_toy_store"] = 77
        mutations.append(a)
        a = copy.deepcopy(base)
        a["tables"]["daily"][1]["date"] = "2023-01-02"
        mutations.append(a)
        a = copy.deepcopy(base)
        a["tables"]["daily"][0]["revenue"] = float("nan")
        mutations.append(a)
        a = copy.deepcopy(base)
        a["tables"]["daily"][0]["ads_cost"] = -5.0
        mutations.append(a)
        for bad in mutations:
            with self.assertRaises(ValueError):
                bridge.validate_snapshot(bad)

    def test_ads_only_day_retained_and_no_per_source_attribution(self):
        data = fixture_tables()
        data["daily"][1]["transactions"] = 0
        data["daily"][1]["revenue"] = 0.0
        data["daily"][1]["operational_margin"] = 0.0
        data["daily"][1]["ads_margin"] = -5.0
        data["monthly"][0]["transactions"] = 2
        data["monthly"][0]["revenue"] = 150.0
        data["monthly"][0]["operational_margin"] = 40.0
        data["monthly"][0]["ads_margin"] = 25.0
        result = bridge.validate_snapshot(manifest(data))
        self.assertEqual(result["tables"]["daily"][1]["ads_margin"], -5.0)
        self.assertNotIn("roas", result["tables"]["marketing_source"][0])

    def test_refund_flag_blocks_false_net_revenue(self):
        base = manifest()
        base["tables"]["refunds"] = [{
            "datemonth": "2023-01-01", "orders": 3, "revenue": 200.0,
            "refund_amount": 250.0, "orders_with_refund": 3,
            "orders_refund_above_revenue": 1, "refund_unit_verified": False,
            "net_revenue_after_refunds": 0.0,
        }]
        base["row_counts"]["refunds"] = 1
        with self.assertRaisesRegex(ValueError, "Unverified refund"):
            bridge.validate_snapshot(base)
        base["tables"]["refunds"][0]["net_revenue_after_refunds"] = None
        bridge.validate_snapshot(base)
        base["tables"]["refunds"][0]["refund_unit_verified"] = True
        with self.assertRaisesRegex(ValueError, "Unverified refund"):
            bridge.validate_snapshot(base)


if __name__ == "__main__":
    unittest.main()
