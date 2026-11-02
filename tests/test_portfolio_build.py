"""Public demo boundaries, native report portability and chart geometry."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_showcase import build
from scripts.build_powerbi import TABLES, MODEL_NAME
from scripts.build_public_powerbi import create
from scripts.run_analysis import wilson


class PortfolioTests(unittest.TestCase):
    def test_external_data_cannot_overwrite_a_public_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/"bundle";out.mkdir()
            (out/"data.json").write_text("previous safe bundle")
            with patch("scripts.build_showcase.load_ecommerce",return_value={"provenance":"external_unverified"}), patch("scripts.build_showcase.load_greenweez",return_value={"provenance":"synthetic_demo"}):
                with self.assertRaisesRegex(ValueError,"synthetic provenance only"):
                    build(root,out)
            self.assertEqual((out/"data.json").read_text(),"previous safe bundle")

    def test_missing_source_is_not_replaced_with_invented_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("scripts.build_showcase.load_ecommerce",return_value=None), patch("scripts.build_showcase.load_greenweez",return_value=None):
                with self.assertRaisesRegex(ValueError,"both synthetic"):
                    build(Path(temp))

    def test_portable_report_excludes_unrelated_sources_and_has_no_overlaps(self):
        rows={name:[] for name in TABLES}
        rows["ECommerceOrders"]=[{"date":"2024-01-01","completed_orders":1,"returned_orders":0,"completed_revenue":100,"returned_line_revenue":0}]
        rows["ECommerceSessions"]=[{"date":"2024-01-01","sessions":2,"converted_sessions":1,"page_view_events":3}]
        rows["GreenweezFinance"]=[{"date":"2024-01-01","transactions":1,"revenue":100,"operational_margin":50,"ads_cost":10,"ads_margin":40}]
        rows["CommerceLabEvents"]=[{"event_name":"PRIVATE_SENTINEL","event_count":999}]
        rows["SourceRegistry"]=[{"source":"PRIVATE_SENTINEL","status":"api_snapshot"}]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/"report"
            with patch("scripts.build_public_powerbi.build_showcase"), patch("scripts.build_public_powerbi.read_sources",return_value=(rows,[])):
                evidence=create(root,out)
            self.assertEqual(len(evidence["pages"]),4)
            project=out/"project"
            text="\n".join(p.read_text(encoding="utf-8") for p in project.rglob("*") if p.suffix in {".json",".tmdl"})
            self.assertNotIn("PRIVATE_SENTINEL",text)
            self.assertNotIn("File.Contents",text)
            self.assertNotIn("pDataFolder",text)
            for page in (project/(MODEL_NAME+".Report/definition/pages")).glob("*/page.json"):
                visuals=[json.loads(p.read_text()) for p in page.parent.glob("visuals/*/visual.json")]
                for i,left in enumerate(visuals):
                    a=left["position"]
                    self.assertGreaterEqual(a["x"],0);self.assertGreaterEqual(a["y"],0)
                    self.assertLessEqual(a["x"]+a["width"],1280)
                    self.assertLessEqual(a["y"]+a["height"],720)
                    for right in visuals[i+1:]:
                        b=right["position"]
                        overlaps=(a["x"]<b["x"]+b["width"] and a["x"]+a["width"]>b["x"] and a["y"]<b["y"]+b["height"] and a["y"]+a["height"]>b["y"])
                        self.assertFalse(overlaps,f"{page.parent.name}: {left['name']} overlaps {right['name']}")

    def test_wilson_intervals_preserve_uncertainty_at_boundaries(self):
        self.assertIsNone(wilson(0,0))
        lower,upper=wilson(0,5)
        self.assertAlmostEqual(lower,0)
        self.assertGreater(upper,.4)
        lower,upper=wilson(5,5)
        self.assertLess(lower,.6)
        self.assertAlmostEqual(upper,1)


if __name__ == "__main__":
    unittest.main()
