"""Decision reporting follows evidence and rejects changed populations/gates."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.executive_readout import ROOT,INPUTS,render


class DecisionReadout(unittest.TestCase):
    def fixture(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        root=Path(directory.name)
        for name in INPUTS:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        return root

    def edit(self,root,index,change):
        p=root/INPUTS[index];data=json.loads(p.read_text());change(data);p.write_text(json.dumps(data))

    def test_published_readout_matches_current_receipts_and_does_not_promote_negative_results(self):
        text,ledger=render()
        self.assertEqual(text,(ROOT/'docs/EXECUTIVE_READOUT.md').read_text(encoding='utf-8'))
        self.assertEqual(ledger,json.loads((ROOT/'docs/executive_readout.json').read_text()))
        self.assertFalse(ledger['historical_public_olist']['selector_superiority_demonstrated'])
        self.assertIn('No demonstrated primary selector improvement',text)
        self.assertIn('direction is not identified',text)
        self.assertEqual(ledger['private_core_observation']['financial_acceptance'],'HOLD')
        root=self.fixture()
        for name in INPUTS:
            p=root/name;p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        self.assertEqual(render(root),(text,ledger))

    def test_mixed_snapshots_and_changed_financial_or_primary_gates_are_rejected(self):
        changes=[(1,lambda x:x['quality']['files'].clear(),'Mixed'),
            (5,lambda x:x['gates'].update(currency_verified=True),'acceptance gates changed'),
            (5,lambda x:x['gates'].update(independent_raw_amount_reconciliation=False),'engineering acceptance'),
            (4,lambda x:x['protocol'].update(primary_bootstrap_block_weeks=8),'protocol changed'),
            (3,lambda x:x['summary'].append(x['summary'][1]),'Exactly one primary')]
        changes.append((7, lambda x: x['summary'].update(item_rows=1), 'denominator differs'))
        changes.append((7, lambda x: x.update(snapshot_observed_at_utc='2000-01-01T00:00:00Z'), 'snapshot differs'))
        for index,change,message in changes:
            with self.subTest(index=index,message=message):
                root=self.fixture();self.edit(root,index,change)
                with self.assertRaisesRegex(ValueError,message):render(root)

    def test_forecast_conclusion_tracks_primary_interval_and_excludes_private_amount_fields(self):
        root=self.fixture()
        def positive(data):
            for block in data['paired_uncertainty']:
                if block['block_weeks']==4:block.update(ci_low=1.0,ci_high=3.0)
        self.edit(root,4,positive)
        self.edit(root,5,lambda x:x.update(private_amount='NEVER_PUBLISH_THIS_AMOUNT'))
        text,ledger=render(root)
        self.assertTrue(ledger['historical_public_olist']['selector_superiority_demonstrated'])
        self.assertIn('future utility acceptance remains open',text)
        self.assertNotIn('NEVER_PUBLISH_THIS_AMOUNT',text+json.dumps(ledger))


if __name__=='__main__':unittest.main()
