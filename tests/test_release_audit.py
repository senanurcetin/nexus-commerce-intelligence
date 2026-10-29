"""Release checks target the shipped archive, including corruption and stale data."""
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.release_audit import ROOT,audit,read_archive,research_bundle,website_bundle,write_report
from scripts.powerbi_acceptance import audit as powerbi_audit


class ReleaseAudit(unittest.TestCase):
    def test_actual_deliverables_pass_but_cannot_establish_native_acceptance(self):
        r=audit()
        self.assertTrue(r['artifact_delivery_ready'],r['errors'])
        self.assertEqual(r,json.loads((ROOT/'docs/release_audit.json').read_text()))
        self.assertEqual(len(r['checks']),3)
        self.assertEqual(r['native_bi_release_decision'],'HOLD')
        self.assertFalse(r['dax_engine_executed']);self.assertFalse(r['desktop_render_verified'])
        self.assertFalse(r['live_refresh_required_for_historical_portfolio'])

    def test_corrupt_actual_archive_fails_even_if_other_checks_can_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'powerbi').mkdir()
            shutil.copyfile(ROOT/'powerbi/package-manifest.json',root/'powerbi/package-manifest.json')
            (root/'powerbi/NEXUS_Commerce_Demo.zip').write_bytes(b'corrupted archive')
            r=audit(root)
            self.assertFalse(r['artifact_delivery_ready']);self.assertEqual(len(r['checks']),3)
            self.assertIn('size/SHA-256',r['errors'][0])

    def test_unsafe_case_duplicate_and_symbolic_archive_entries_fail_before_extraction(self):
        for entries in ([('../outside.txt',b'x')],[('C:/outside',b'x')],[('a\\b',b'x')],[('a.txt',b'x'),('A.txt',b'y')]):
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as z:
                for name,value in entries:
                    info=zipfile.ZipInfo('placeholder');info.filename=name
                    z.writestr(info,value)
            with self.subTest(entries=entries),self.assertRaises(ValueError):read_archive(data.getvalue())
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            info=zipfile.ZipInfo('symlink');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,b'target')
        with self.assertRaises(ValueError):read_archive(data.getvalue())

    def test_research_csv_edit_is_rejected_even_with_an_intact_project(self):
        files=read_archive((ROOT/'powerbi/NEXUS_Olist_Research.zip').read_bytes())
        m=json.loads((ROOT/'powerbi/olist-package-manifest.json').read_text())
        files['review_summary.csv']+=b'\n'
        with self.assertRaisesRegex(ValueError,'aggregate hash mismatch'):research_bundle(ROOT,files,m)

    def test_stale_report_and_unsupported_desktop_claim_are_rejected(self):
        files=read_archive((ROOT/'powerbi/NEXUS_Olist_Research.zip').read_bytes())
        m=json.loads((ROOT/'powerbi/olist-package-manifest.json').read_text())
        m['desktop_render_verified']=True
        with self.assertRaisesRegex(ValueError,'unsupported native'):research_bundle(ROOT,files,m)
        m['desktop_render_verified']=False;files['REVIEW_SELECTION.md']+=b'\nChanged conclusion\n'
        with self.assertRaisesRegex(ValueError,'differs from current documentation'):research_bundle(ROOT,files,m)

    def test_website_rejects_real_data_or_stale_scripts_and_handles_cross_platform_newlines(self):
        files=read_archive((ROOT/'showcase/NEXUS_Commerce_Web_Demo.zip').read_bytes())
        logo=(ROOT/'branding/nexus_official_transparent.png').read_bytes()
        for file in ('index.html','app.mjs','metrics.mjs','styles.css'):files[file]=files[file].replace(b'\r\n',b'\n')
        self.assertTrue(website_bundle(ROOT,files,logo)['synthetic_only'])
        data=json.loads(files['data.json']);data['sources']['ecommerce']['origin']='live_private';files['data.json']=json.dumps(data).encode()
        with self.assertRaisesRegex(ValueError,'not synthetic'):website_bundle(ROOT,files,logo)
        files['app.mjs']+=b'\nalert("stale");'
        with self.assertRaisesRegex(ValueError,'stale'):website_bundle(ROOT,files,logo)

    def test_failed_audit_replaces_stale_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'release_audit.json').write_text('{"artifact_delivery_ready":true}')
            write_report(audit(out/'missing'),out)
            self.assertFalse(json.loads((out/'release_audit.json').read_text())['artifact_delivery_ready'])
            self.assertIn('BLOCKED',(out/'RELEASE_READINESS.md').read_text())

    def test_packaged_editable_reports_are_found_without_claiming_a_render(self):
        result=powerbi_audit(ROOT)
        self.assertTrue(result['checks']['editable_report_present'])
        self.assertTrue(any('validated editable PBIP' in p for p in result['report_candidates']))
        self.assertEqual(result['release_decision'],'HOLD')
        self.assertFalse(result['checks']['actual_data_refresh'])

    def test_require_native_exit_code_fails_without_invalidating_portable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            run=subprocess.run([sys.executable,'-m','scripts.release_audit','--out',directory,'--require-native'],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(run.returncode,1,run.stderr)
            receipt=json.loads((Path(directory)/'release_audit.json').read_text())
            self.assertTrue(receipt['artifact_delivery_ready'])
            self.assertEqual(receipt['native_bi_release_decision'],'HOLD')


if __name__=='__main__':unittest.main()
