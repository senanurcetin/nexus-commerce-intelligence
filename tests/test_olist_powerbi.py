"""Public aggregate integrity, source separation and native report bindings."""
import json
import re
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.build_olist_powerbi import NAME, PAGES, ROOT, TABLES, create


class OlistPowerBI(unittest.TestCase):
    def test_portable_model_matches_aggregate_contract_and_visual_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            project=create(ROOT/'docs/advanced-analysis',Path(directory))
            model=project.parent/(NAME+'.SemanticModel/definition')
            text='\n'.join(p.read_text() for p in model.rglob('*.tmdl'))
            for forbidden in ('File.Contents','pDataFolder','customer_unique_id','order_id','ECommerceOrders','GreenweezFinance'):
                self.assertNotIn(forbidden,text)
            self.assertEqual({p.stem for p in (model/'tables').glob('*.tmdl')},set(TABLES))
            for filename in ('REPORT.md','CUSTOMER_PORTFOLIO.md','DELIVERY_OPERATIONS.md'):
                report=project.parent/filename
                self.assertTrue(report.exists())
                for picture in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',report.read_text(encoding='utf-8')):
                    self.assertTrue((project.parent/picture).is_file(),picture)
            pages=project.parent/(NAME+'.Report/definition/pages')
            self.assertEqual(json.loads((pages/'pages.json').read_text())['pageOrder'],[p['id'] for p in PAGES])
            for page in PAGES:
                visuals=[json.loads(p.read_text()) for p in (pages/page['id']/'visuals').rglob('visual.json')]
                self.assertTrue(any(v['name']=='nexus_brand_logo' for v in visuals))
                self.assertTrue(any('PUBLIC OLIST' in json.dumps(v) for v in visuals))
                for v in visuals:
                    pos=v['position']
                    self.assertGreaterEqual(pos['x'],0); self.assertGreaterEqual(pos['y'],0)
                    self.assertLessEqual(pos['x']+pos['width'],1280)
                    self.assertLessEqual(pos['y']+pos['height'],720)
                    for role in v['visual'].get('query',{}).get('queryState',{}).values():
                        for projection in role['projections']:
                            field=next(iter(projection['field'].values()))
                            entity=field['Expression']['SourceRef']['Entity']
                            self.assertIn(entity,TABLES)
                            self.assertIn(field['Property'],text)
                rectangles=[v['position'] for v in visuals]
                for i,a in enumerate(rectangles):
                    for b in rectangles[i+1:]:
                        overlap=min(a['x']+a['width'],b['x']+b['width'])>max(a['x'],b['x']) and min(a['y']+a['height'],b['y']+b['height'])>max(a['y'],b['y'])
                        self.assertFalse(overlap,page['id'])

    def test_edited_aggregate_and_wrong_population_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source'
            shutil.copytree(ROOT/'docs/advanced-analysis',source)
            with (source/'monthly.csv').open('a') as stream: stream.write('\n')
            with self.assertRaisesRegex(ValueError,'hash mismatch'): create(source,Path(directory)/'out')
            evidence=json.loads((source/'evidence.json').read_text())
            evidence['source_kind']='synthetic_dbt_seeds_only'
            (source/'evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError,'public Olist'): create(source,Path(directory)/'out')

    def test_different_raw_snapshot_and_edited_extension_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source'
            shutil.copytree(ROOT/'docs/advanced-analysis',source)
            evidence=json.loads((source/'extension_evidence.json').read_text())
            first=next(iter(evidence['quality']['files']))
            original=evidence['quality']['files'][first]['sha256']
            evidence['quality']['files'][first]['sha256']='0'*64
            (source/'extension_evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError,'snapshots differ'): create(source,Path(directory)/'out')
            evidence['quality']['files'][first]['sha256']=original
            original_fact=evidence['order_fact_sql_sha256']
            evidence['order_fact_sql_sha256']='0'*64
            (source/'extension_evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError,'fact definitions differ'): create(source,Path(directory)/'out')
            evidence['order_fact_sql_sha256']=original_fact
            (source/'extension_evidence.json').write_text(json.dumps(evidence))
            with (source/'repeat_curve.csv').open('a') as stream: stream.write('\n')
            with self.assertRaisesRegex(ValueError,'Extension aggregate file hash'): create(source,Path(directory)/'out')

    def test_operations_must_share_snapshot_and_preserve_all_aggregate_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source'
            shutil.copytree(ROOT/'docs/advanced-analysis',source)
            evidence=json.loads((source/'operations_evidence.json').read_text())
            first=next(iter(evidence['quality']['files']));original=evidence['quality']['files'][first]['sha256']
            evidence['quality']['files'][first]['sha256']='0'*64
            (source/'operations_evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError,'Operations source snapshots'):create(source,Path(directory)/'out')
            evidence['quality']['files'][first]['sha256']=original
            (source/'operations_evidence.json').write_text(json.dumps(evidence))
            with (source/'operations_strata.csv').open('a') as stream:stream.write('\n')
            with self.assertRaisesRegex(ValueError,'Packaged aggregate file hash'):create(source,Path(directory)/'out')


if __name__=='__main__': unittest.main()
