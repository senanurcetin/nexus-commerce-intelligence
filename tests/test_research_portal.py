"""Portal values, archive provenance and local evidence navigation are inspectable."""
import hashlib
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from functools import partial
import json
import re
import runpy
from pathlib import Path,PurePosixPath
import tempfile
import threading
import unittest
from urllib.request import urlopen
from unittest.mock import patch

from scripts.build_research_portal import ROOT,assets,payload,RECEIPTS
from scripts.release_audit import read_archive,website_bundle
from scripts.build_showcase import build
from scripts.serve_portfolio import PortfolioHandler


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        for key in ('src','href'):
            if key in a:self.links.append(a[key])


class ResearchPortal(unittest.TestCase):
    def test_source_projection_matches_receipts_and_keeps_populations_separate(self):
        a=assets();data=json.loads(a['data.json'])
        self.assertEqual(data['provenance'],'historical_public_olist');self.assertFalse(data['synthetic'])
        self.assertEqual(len(data['studies']),5);self.assertEqual(data['source_orders'],99441)
        self.assertEqual(len(data['forecast']['rows']),840)
        for r in data['forecast']['rows']:
            self.assertGreaterEqual(r['day'],'2018-01-01');self.assertLessEqual(r['day'],'2018-07-29')
            self.assertEqual(set(r),{'day','origin','method','actual_orders','prediction','lower','upper'})
        self.assertIn('ALL placed orders',data['studies'][-1]['population'])
        self.assertIn('not demonstrate superiority',data['studies'][-1]['finding'])
        self.assertEqual(data['review']['groups']['late']['total'],4984)
        receipt=json.loads(a['portal-manifest.json'])
        for file,digest in receipt['files_sha256'].items():self.assertEqual(hashlib.sha256(a[file]).hexdigest(),digest)

    def test_static_html_and_dynamic_case_links_resolve_inside_the_built_site(self):
        a=assets();parser=Links();parser.feed(a['index.html'].decode())
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        client=(ROOT/'showcase/research/research.mjs').read_text(encoding='utf-8')
        for identifier in re.findall(r"\$\('([^']+)'\)",client):self.assertIn(identifier,parser.ids)
        root_links={'../index.html','../favicon.svg','../nexus-logo.png'}
        for link in parser.links:
            if link.startswith(('http','#')) or link in root_links:continue
            self.assertIn(PurePosixPath(link).as_posix().removeprefix('./'),a,link)
        for study in json.loads(a['data.json'])['studies']:
            for file in [study['report'],study['receipt'],*study['figures']]:self.assertIn(file,a)

    def test_method_comparison_rejects_misaligned_future_dates_or_unequal_method_counts(self):
        files=read_archive((ROOT/'powerbi/NEXUS_Olist_Research.zip').read_bytes())
        files['forecast_daily.csv']=files['forecast_daily.csv'].replace(b'evaluation,seasonal_naive,',b'evaluation,past_mae_selector,',1)
        with self.assertRaisesRegex(ValueError,'identical evaluation dates'):payload(files,'test')

    def test_corrupt_research_cannot_overwrite_a_previous_synthetic_build(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'data.json').write_text('previous safe bundle')
            with patch('scripts.build_showcase.load_ecommerce',return_value={'provenance':'synthetic_ci','tables':{'orders':[],'sessions':[]}}),patch('scripts.build_showcase.load_greenweez',return_value={'provenance':'synthetic_demo','tables':{'daily':[],'marketing_source':[]}}),patch('scripts.build_research_portal.assets',side_effect=ValueError('Research hash mismatch')):
                with self.assertRaisesRegex(ValueError,'Research hash'):build(ROOT,out)
            self.assertEqual((out/'data.json').read_text(),'previous safe bundle')

    def test_editing_a_bundled_interactive_value_is_rejected(self):
        files=read_archive((ROOT/'showcase/NEXUS_Commerce_Web_Demo.zip').read_bytes())
        data=json.loads(files['research/data.json']);data['review']['groups']['late']['poor']+=1
        files['research/data.json']=json.dumps(data).encode()
        with self.assertRaisesRegex(ValueError,'portal asset differs'):website_bundle(ROOT,files,(ROOT/'branding/nexus_official_transparent.png').read_bytes())

    def test_every_shipped_asset_is_served_over_local_http_with_a_javascript_module_mime(self):
        files=read_archive((ROOT/'showcase/NEXUS_Commerce_Web_Demo.zip').read_bytes())
        class QuietHandler(PortfolioHandler):
            def log_message(self,*args):pass
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,data in files.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            self.assertEqual(runpy.run_path(str(root/'serve.py'))['DEFAULT_DIRECTORY'],root)
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=directory))
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
            try:
                for name,data in files.items():
                    with urlopen(f'http://127.0.0.1:{server.server_port}/{name}',timeout=5) as response:
                        self.assertEqual(response.status,200);self.assertEqual(response.read(),data,name)
                        if name.endswith('.mjs'):self.assertIn(response.headers.get_content_type(),{'text/javascript','application/javascript'})
            finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
