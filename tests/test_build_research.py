"""Rebuild safety: source protection and stale-success rejection."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_research import build


class ResearchSafety(unittest.TestCase):
    def test_source_directory_cannot_be_an_output_or_its_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=root/'raw';raw.mkdir()
            marker=raw/'source.csv';marker.write_text('unchanged')
            for out in (root,raw,raw/'nested'):
                with self.subTest(out=out),self.assertRaises(ValueError):build(raw,out)
            self.assertEqual(marker.read_text(),'unchanged')

    def test_failed_analysis_removes_stale_success_and_cannot_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=root/'raw';raw.mkdir();out=root/'out';out.mkdir()
            receipt=out/'research_build.json';receipt.write_text('{"status":"complete"}')
            with patch('scripts.build_research.core.run',side_effect=RuntimeError('Source validation failed')),patch('scripts.build_research.create') as export:
                with self.assertRaisesRegex(RuntimeError,'Source validation'):build(raw,out)
                export.assert_not_called()
            self.assertFalse(receipt.exists())

    def test_failed_fourth_study_also_prevents_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=root/'raw';raw.mkdir();out=root/'out';out.mkdir()
            receipt=out/'research_build.json';receipt.write_text('{"status":"complete"}')
            with patch('scripts.build_research.core.run'),patch('scripts.build_research.customer.run'),patch('scripts.build_research.operations.run'),patch('scripts.build_research.reviews.run',side_effect=ValueError('Review controls failed')),patch('scripts.build_research.create') as export:
                with self.assertRaisesRegex(ValueError,'Review controls'):build(raw,out)
                export.assert_not_called()
            self.assertFalse(receipt.exists())


if __name__=='__main__':unittest.main()
