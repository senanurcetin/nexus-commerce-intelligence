"""Test static Power BI gates are not misrepresented as a fresh Desktop QA."""
from pathlib import Path
import tempfile
import shutil
import unittest

from scripts.powerbi_acceptance import audit, ROOT
from dashboard.nexus_theme import COLORS, plot_layout


class NexusDesignPowerBIAcceptanceTests(unittest.TestCase):
    def test_reference_margin_denominator_must_use_the_known_cost_population(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'docs').mkdir();(root/'powerbi/themes').mkdir(parents=True)
            for name in ('POWER_BI_VISUAL_QA.md','dax-measures.md'):shutil.copyfile(ROOT/'docs'/name,root/'docs'/name)
            shutil.copyfile(ROOT/'powerbi/themes/nexus-commerce.json',root/'powerbi/themes/nexus-commerce.json')
            path=root/'docs/dax-measures.md'
            path.write_text(path.read_text().replace('DIVIDE([Known-Cost Product Contribution], [Known-Cost Completed Item Value])',
                'DIVIDE([Known-Cost Product Contribution], [Completed Item Value])'))
            result=audit(root)
            self.assertTrue(result['checks']['dax_documentation'])
            self.assertFalse(result['checks']['dax_semantics'])
            self.assertEqual(result['release_decision'],'HOLD')

    def test_theme_and_documented_kpis_ok_but_release_stays_on_hold(self):
        result = audit(ROOT)
        self.assertTrue(result["checks"]["theme_json"])
        self.assertTrue(result["checks"]["dax_documentation"])
        self.assertTrue(result["checks"]["dax_semantics"])
        self.assertEqual(result["release_decision"], "HOLD")
        self.assertFalse(result["checks"]["actual_desktop_render"])
        self.assertFalse(result["checks"]["actual_data_refresh"])
        self.assertFalse(result["checks"]["financial_reconciliation"])

    def test_even_an_existing_editable_file_cannot_self_prove_render(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "source.pbix"
            report.write_bytes(b"CI placeholder, never a real Power BI report")
            result = audit(ROOT, report)
            self.assertTrue(result["checks"]["editable_report_present"])
            self.assertFalse(result["checks"]["actual_desktop_render"])
            self.assertEqual(result["release_decision"], "HOLD")

    def test_nexus_chart_tokens_are_consistent(self):
        fig = plot_layout("NEXUS chart")
        self.assertEqual(fig["paper_bgcolor"], COLORS["page"])
        self.assertEqual(fig["plot_bgcolor"], COLORS["surface"])
        self.assertEqual(fig["title"]["text"], "NEXUS chart")
        self.assertEqual(COLORS["cyan"], "#47DFF2")


if __name__ == "__main__":
    unittest.main()
