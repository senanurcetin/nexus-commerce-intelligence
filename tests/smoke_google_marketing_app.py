"""Streamlit AppTest verifies empty-state honesty and test-only fixture rendering.

No account authentication, Google API requests, mock business claims or data writes.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

from scripts.google_dashboard_data import SCHEMA
from scripts.greenweez_bridge import validate_snapshot as validate_greenweez
from scripts.ecommerce_marts_bridge import validate_snapshot as validate_historical
from datetime import datetime, timezone


APP = Path(__file__).resolve().parents[1] / "dashboard/google_marketing_app.py"


def export_fixture(root: Path) -> None:
    """The following numbers are synthetic CI-only fixtures, never product metrics."""
    extracted = "2026-10-15T10:00:00+00:00"
    examples = {
        "ga4": {
            "source_system": "ga4_data_api", "property_id": "CI-ONLY-123",
            "date": "2026-10-01", "ga4_session_channel_group": "Organic Search",
            "sessions": "20", "engaged_sessions": "12", "active_users": "14",
            "ecommerce_purchases": "2", "purchase_revenue_property_currency": "45.50",
            "extracted_at_utc": extracted,
        },
        "gsc": {
            "source_system": "gsc_search_analytics_api", "site_property": "sc-domain:ci-only.example",
            "date": "2026-10-01", "device": "MOBILE",
            "clicks": "4", "impressions": "20", "ctr_ratio": "0.2",
            "average_position": "3.0", "extracted_at_utc": extracted,
        },
        "pagespeed": {
            "source_system": "pagespeed_insights_api", "url": "https://ci-only.example/",
            "strategy": "mobile", "extracted_at_utc": extracted,
            "performance_score": "0", "accessibility_score": "80", "best_practices_score": "90",
            "seo_score": "100", "lab_fcp_ms": "800", "lab_lcp_ms": "1700",
            "lab_speed_index_ms": "1500", "lab_total_blocking_time_ms": "70",
            "lab_cls": "0.05",
        },
    }
    manifest = {
        "schema_version": 1,
        "data_status": "actual_api_snapshots_not_live_feed",
        "partial_snapshot_count": 0,
        "input_snapshot_count": 3,
        "source_summary": {},
    }
    for source, spec in SCHEMA.items():
        record = examples[source]
        with (root / spec["filename"]).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=spec["required"])
            writer.writeheader()
            writer.writerow(record)
        manifest["source_summary"][spec["source_system"]] = {"rows": 1}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def isolated_app():
    """Do not let a developer's persisted bridge files contaminate fixtures."""
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    # Only test widget state changes: never delete or rename the user's data.
    with tempfile.TemporaryDirectory() as folder:
        absent = Path(folder)
        defaults = {
            "Validated export folder": absent / "google",
            "Historical E-Commerce snapshot file": absent / "historical.json",
            "Greenweez original Sheets evidence": absent / "sheets.json",
            "Greenweez snapshot file": absent / "finance.json",
        }
        for field in app.text_input:
            if field.label in defaults:
                field.set_value(str(defaults[field.label]))
        return app.run()


class GoogleMeasurementAppSmokeTests(unittest.TestCase):
    def test_no_snapshot_never_claims_real_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(folder).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertEqual(len(app.metric), 0, "Unavailable sources must not display KPI figures")
            self.assertEqual(len(app.tabs), 9, "Unified model sources and observed Greenweez Sheets stay accessible")
            self.assertTrue(any("Website URL" == field.label for field in app.text_input))

    def test_historical_ecommerce_import_uses_distinct_business_domain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            historical = root / "historical_ci.json"
            payload = {
                "schema_version": 1, "source_system": "ecommerce_dbt_marts",
                "provenance": "synthetic_ci",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": "c" * 64,
                "tables": {
                    "orders": [{
                        "date": "2023-02-01", "completed_orders": 1,
                        "returned_orders": 0, "completed_revenue": 150.0,
                        "returned_line_revenue": 0.0,
                    }],
                    "sessions": [{
                        "date": "2023-02-01", "sessions": 2,
                        "converted_sessions": 1, "page_view_events": 4,
                    }],
                },
                "row_counts": {"orders": 1, "sessions": 1},
            }
            historical.write_text(json.dumps(validate_historical(payload)), encoding="utf-8")
            app = isolated_app()
            next(x for x in app.text_input if x.label == "Validated export folder").set_value(str(root)).run()
            next(x for x in app.text_input if x.label == "Historical E-Commerce snapshot file").set_value(str(historical)).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            labels = [m.label for m in app.metric]
            self.assertIn("Completed order-days · daily distinct IDs", labels)
            self.assertIn("Sessions · dbt historical", labels)
            self.assertNotIn("Greenweez revenue · stored units", labels)
            self.assertNotIn("Purchase revenue · property currency", labels)
            self.assertGreaterEqual(len(app.warning), 1)

    def test_greenweez_import_renders_separate_source_only(self):
        """Test-only fixture cannot be claimed as a real Greenweez business result."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "greenweez_ci_only.json"
            value = {
                "schema_version": 1,
                "source_system": "greenweez_dbt_marts",
                "provenance": "synthetic_demo",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": "e" * 64,
                "tables": {
                    "daily": [
                        {"date": "2023-01-02", "transactions": 1, "revenue": 100.0,
                         "operational_margin": 30.0, "ads_cost": 10.0,
                         "ads_margin": 20.0, "ads_impression": 200, "ads_clicks": 5},
                    ],
                    "monthly": [
                        {"datemonth": "2023-01-01", "transactions": 1, "revenue": 100.0,
                         "operational_margin": 30.0, "ads_cost": 10.0,
                         "ads_margin": 20.0, "ads_impression": 200, "ads_clicks": 5},
                    ],
                    "marketing_source": [],
                    "refunds": [],
                },
                "row_counts": {"daily": 1, "monthly": 1, "marketing_source": 0, "refunds": 0},
            }
            sample.write_text(json.dumps(validate_greenweez(value)), encoding="utf-8")
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(str(root)).run()
            next(field for field in app.text_input if field.label == "Greenweez snapshot file").set_value(str(sample)).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertTrue(any("Greenweez" in tab.label for tab in app.tabs))
            labels = [metric.label for metric in app.metric]
            self.assertIn("Greenweez revenue · stored units", labels)
            self.assertNotIn("Purchase revenue · property currency", labels)
            self.assertNotIn("Lab completed test checkouts", labels)
            self.assertGreaterEqual(len(app.warning), 1, "Synthetic Greenweez rows must retain warning banner")

    def test_rejected_greenweez_snapshot_does_not_show_finance_kpis(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            corrupted = root / "corrupt.json"
            corrupted.write_text(json.dumps({"rows": [{"revenue": 99999999}]}), encoding="utf-8")
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(str(root)).run()
            next(field for field in app.text_input if field.label == "Greenweez snapshot file").set_value(str(corrupted)).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertFalse(any("Greenweez revenue · stored units" == m.label for m in app.metric))
            self.assertGreaterEqual(len(app.error), 1, "Invalid Greenweez snapshot must fail closed")

    def test_commerce_lab_tab_never_fabricates_unconnected_revenue(self):
        with tempfile.TemporaryDirectory() as folder:
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(folder).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertTrue(any("Commerce Lab" in tab.label for tab in app.tabs))
            self.assertFalse(any("Lab completed test checkouts" == metric.label for metric in app.metric))
            self.assertFalse(any("Purchase revenue · property currency" == metric.label for metric in app.metric))

    def test_ecommerce_demo_picker_prefills_url_without_scanning(self):
        with tempfile.TemporaryDirectory() as folder:
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(folder).run()
            store = next(field for field in app.selectbox if field.label == "Measurement target")
            store.set_value("Tricentis Demo Web Shop (third-party)").run()
            url = next(field for field in app.text_input if field.label == "Website URL")
            self.assertEqual(url.value, "https://demowebshop.tricentis.com/")
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertEqual(len(app.metric), 0, "Changing preset must not start an API call")

    def test_own_store_is_initial_website_target_and_no_api_is_called(self):
        with tempfile.TemporaryDirectory() as folder:
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(folder).run()
            store = next(field for field in app.selectbox if field.label == "Measurement target")
            self.assertEqual(store.value, "NEXUS Commerce Lab (owned test storefront)")
            url = next(field for field in app.text_input if field.label == "Website URL")
            self.assertEqual(url.value, "https://nexus-commerce-lab.vercel.app/")
            self.assertEqual(len(app.metric), 0)
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])

    def test_pagespeed_only_source_does_not_require_ga4_or_gsc(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            export_fixture(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for source in ("ga4", "gsc"):
                spec = SCHEMA[source]
                with (root / spec["filename"]).open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=spec["required"])
                    writer.writeheader()
                manifest["source_summary"][spec["source_system"]]["rows"] = 0
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(folder).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            labels = [metric.label for metric in app.metric]
            self.assertNotIn("Sessions", labels)
            self.assertIn("Performance", labels)

    def test_verified_csv_contract_drives_all_three_views(self):
        with tempfile.TemporaryDirectory() as folder:
            export_fixture(Path(folder))
            app = isolated_app()
            next(field for field in app.text_input if field.label == "Validated export folder").set_value(folder).run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            labels = [metric.label for metric in app.metric]
            self.assertIn("Sessions", labels)
            self.assertIn("Organic CTR", labels)
            self.assertIn("Performance", labels)


    def test_switching_from_valid_export_to_absent_source_clears_old_kpis(self):
        """No stale metrics when an operator changes the selected source."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            valid = root / "valid"
            valid.mkdir()
            empty = root / "empty"
            empty.mkdir()
            export_fixture(valid)
            app = isolated_app()
            source = next(x for x in app.text_input
                          if x.label == "Validated export folder")
            source.set_value(str(valid)).run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn("Sessions", [metric.label for metric in app.metric])
            source = next(x for x in app.text_input
                          if x.label == "Validated export folder")
            source.set_value(str(empty)).run()
            self.assertEqual(len(app.exception), 0)
            self.assertNotIn("Sessions", [metric.label for metric in app.metric])
            self.assertNotIn("Organic CTR", [metric.label for metric in app.metric])
            self.assertEqual(len(app.tabs), 9)

    def test_gsc_device_filter_is_source_scoped(self):
        """Removing GSC device rows must not hide independent GA4 counters."""
        with tempfile.TemporaryDirectory() as folder:
            export_fixture(Path(folder))
            app = isolated_app()
            next(x for x in app.text_input
                 if x.label == "Validated export folder").set_value(folder).run()
            devices = next(x for x in app.multiselect if x.label == "Devices")
            devices.set_value([]).run()
            self.assertEqual(len(app.exception), 0)
            labels = [metric.label for metric in app.metric]
            self.assertNotIn("Search clicks", labels)
            self.assertNotIn("Organic CTR", labels)
            self.assertIn("Sessions", labels)


if __name__ == "__main__":
    unittest.main()
