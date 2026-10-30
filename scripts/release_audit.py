"""Validate the actual portable deliverables without running a UI or cloud query.

Archive integrity is a different acceptance level from Desktop refresh/render.
Nothing in this audit upgrades an unexecuted native BI gate.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPORTS=('REPORT.md','CUSTOMER_PORTFOLIO.md','DELIVERY_OPERATIONS.md','REVIEW_SELECTION.md','FORECAST_VALIDATION.md')
PRIVATE_FIELDS=re.compile(r'\b(?:order_id|order_item_id|customer_id|customer_unique_id|user_id|review_id)\b',re.I)


def digest(data):return hashlib.sha256(data).hexdigest()


def read_archive(data: bytes) -> dict[str,bytes]:
    """Bounded, case-insensitive path validation. Never extract or execute content."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries=archive.infolist()
        if len(entries)>500 or sum(e.file_size for e in entries)>25_000_000:
            raise ValueError('Archive exceeds the portable-deliverable limits')
        seen=set();files={}
        for entry in entries:
            name=entry.orig_filename;p=PurePosixPath(name)
            if (not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts
                or name!=p.as_posix() or name.casefold() in seen or entry.flag_bits&1
                or stat.S_ISLNK(entry.external_attr>>16)):
                raise ValueError('Unsafe, duplicate or encrypted archive path')
            seen.add(name.casefold())
            if not entry.is_dir():files[name]=archive.read(entry)
        return files


def load_pinned(root:Path,relative:str,manifest:dict):
    path=root/relative
    if Path(manifest['file']).name!=path.name or manifest['file']!=path.name:
        raise ValueError('Manifest must name the expected archive')
    if path.stat().st_size>25_000_000:raise ValueError('Archive exceeds the portable-deliverable limits')
    data=path.read_bytes()
    if len(data)!=manifest['bytes'] or digest(data)!=manifest['sha256']:
        raise ValueError('Archive size/SHA-256 differs from its manifest')
    files=read_archive(data)
    if 'entries' in manifest and len(files)!=manifest['entries']:raise ValueError('Archive entry count differs from manifest')
    return files,{'file':relative,'sha256':digest(data),'bytes':len(data),'entries':len(files)}


def native_project(files,name,pages,tables,logo):
    project=json.loads(files[name+'.pbip'])
    if project['artifacts']!=[{'report':{'path':name+'.Report'}}]:raise ValueError('Broken PBIP report binding')
    report=name+'.Report/';model=name+'.SemanticModel/'
    binding=json.loads(files[report+'definition.pbir'])['datasetReference']
    if binding!={'byPath':{'path':'../'+name+'.SemanticModel'}}:raise ValueError('Nonportable semantic-model binding')
    if model+'definition/model.tmdl' not in files or model+'definition.pbism' not in files:raise ValueError('Missing native semantic model')
    tmdl=[key for key in files if key.startswith(model+'definition/tables/') and key.endswith('.tmdl')]
    if len(tmdl)!=tables:raise ValueError('Unexpected semantic table count')
    for key in tmdl:
        text=files[key].decode('utf-8')
        if PRIVATE_FIELDS.search(text) or any(token in text for token in ('File.Contents','pDataFolder','Web.Contents')):
            raise ValueError('Portable model includes raw identifiers or external data paths')
    page_root=report+'definition/pages/'
    order=json.loads(files[page_root+'pages.json'])['pageOrder']
    actual={key[len(page_root):].split('/')[0] for key in files if key.startswith(page_root) and key.endswith('/page.json')}
    if len(order)!=pages or len(set(order))!=pages or actual!=set(order):raise ValueError('Page index and actual pages disagree')
    for page in order:
        visuals=[json.loads(value) for key,value in files.items() if key.startswith(page_root+page+'/visuals/') and key.endswith('/visual.json')]
        if not any(v['name']=='nexus_brand_logo' for v in visuals):raise ValueError('Page has no NEXUS logo visual')
    logos=[value for key,value in files.items() if '/RegisteredResources/' in key and key.endswith('.png')]
    if not logos or any(digest(value)!=digest(logo) for value in logos):raise ValueError('Bundled NEXUS logo differs from official asset')
    return {'pages':pages,'semantic_tables':tables,'embedded_data_only':True}


def research_bundle(root,files,manifest):
    if manifest.get('provenance')!='historical_public_olist_aggregate_only' or manifest.get('license')!='CC-BY-NC-SA-4.0':
        raise ValueError('Research provenance/license contract changed')
    if manifest.get('desktop_render_verified') is not False or manifest.get('dax_engine_executed') is not False:
        raise ValueError('Manifest asserts unsupported native BI acceptance')
    receipts=[json.loads(files[f]) for f in ('evidence.json','extension_evidence.json','operations_evidence.json','review_selection_evidence.json','forecast_evidence.json')]
    source=receipts[0]
    for receipt in receipts:
        if receipt['quality']['files']!=source['quality']['files']:raise ValueError('Research reports use different raw snapshots')
        for file,sha in receipt.get('aggregate_sha256',receipt.get('export_sha256',{})).items():
            if digest(files[file])!=sha:raise ValueError('Bundled research aggregate hash mismatch: '+file)
    for report in REPORTS:
        text=files[report].decode('utf-8')
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if not link.startswith(('https://','http://','#')) and link not in files:
                raise ValueError('Broken bundled report link: '+link)
        if files[report].replace(b'\r\n',b'\n')!=(root/'docs/advanced-analysis'/report).read_bytes().replace(b'\r\n',b'\n'):
            raise ValueError('Bundled report differs from current documentation: '+report)
    review=receipts[3]
    for file,key,canonical in (
        ('olist_review_protocol.json','protocol_sha256','contracts/olist_review_protocol.json'),
        ('review_selection.sql','query_sha256','analytics/olist/review_selection.sql')):
        if digest(files[file])!=review[key] or files[file]!=(root/canonical).read_bytes():
            raise ValueError('Research protocol/query is stale')
    if digest((root/'scripts/olist_review_selection.py').read_bytes())!=review['implementation_sha256']:
        raise ValueError('Review analysis implementation is newer than its evidence')
    prediction=receipts[4]
    for file,key,canonical in (
        ('olist_forecast_protocol.json','protocol_sha256','contracts/olist_forecast_protocol.json'),
        ('daily_order_volume.sql','query_sha256','analytics/olist/daily_order_volume.sql')):
        if digest(files[file])!=prediction[key] or files[file]!=(root/canonical).read_bytes():
            raise ValueError('Forecast protocol/query is stale')
    if digest((root/'scripts/olist_forecast.py').read_bytes())!=prediction['implementation_sha256']:
        raise ValueError('Forecast implementation is newer than its evidence')
    figures=[key for key in files if '/' not in key and key.endswith('.png')]
    if len(figures)!=12 or manifest.get('bundled_figures')!=12 or manifest.get('bundled_analytical_reports')!=5:
        raise ValueError('Research report/figure count contract changed')
    return {'reports':len(REPORTS),'figures':len(figures),'source_snapshots_match':True,'aggregate_hashes_match':True}


def website_bundle(root,files,logo):
    expected={'app.mjs','data.json','favicon.svg','index.html','metrics.mjs','nexus-logo.png','styles.css'}
    if set(files)!=expected:raise ValueError('Unexpected website files')
    for file in ('app.mjs','index.html','metrics.mjs','styles.css'):
        if files[file].replace(b'\r\n',b'\n')!=(root/'showcase'/file).read_bytes().replace(b'\r\n',b'\n'):
            raise ValueError('Website archive is stale: '+file)
    if files['nexus-logo.png']!=logo:raise ValueError('Website logo differs from official asset')
    data=json.loads(files['data.json']);sources=data['sources']
    if data.get('provenance')!='Synthetic dbt demonstration · not trading results' or set(sources)!={'ecommerce','greenweez'}:
        raise ValueError('Website must contain only separate synthetic commerce sources')
    if sources['ecommerce'].get('origin')!='synthetic_ci' or sources['greenweez'].get('origin')!='synthetic_demo':
        raise ValueError('Website source provenance is not synthetic')
    if PRIVATE_FIELDS.search(json.dumps(data)):raise ValueError('Website contains raw identifier fields')
    return {'synthetic_only':True,'source_files_current':True,'browser_render_verified':False}


def audit(root:Path=ROOT):
    root=root.resolve();checks=[];errors=[]
    def check(name,fn):
        try:checks.append({'name':name,'passed':True,'details':fn()})
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as error:
            errors.append(name+': '+str(error));checks.append({'name':name,'passed':False})
    def commerce():
        m=json.loads((root/'powerbi/package-manifest.json').read_text())['powerbi']
        if m['provenance']!='synthetic_dbt_seeds_only':raise ValueError('Public BI provenance changed')
        f,info=load_pinned(root,'powerbi/NEXUS_Commerce_Demo.zip',m)
        return {**info,**native_project(f,'NEXUS_Commerce',4,4,(root/'branding/nexus_official_transparent.png').read_bytes())}
    def research():
        m=json.loads((root/'powerbi/olist-package-manifest.json').read_text())
        f,info=load_pinned(root,'powerbi/NEXUS_Olist_Research.zip',m)
        return {**info,**native_project(f,'NEXUS_Olist_Research',9,16,(root/'branding/nexus_official_transparent.png').read_bytes()),**research_bundle(root,f,m)}
    def website():
        m=json.loads((root/'powerbi/package-manifest.json').read_text())['website']
        f,info=load_pinned(root,'showcase/NEXUS_Commerce_Web_Demo.zip',m)
        return {**info,**website_bundle(root,f,(root/'branding/nexus_official_transparent.png').read_bytes())}
    check('synthetic_powerbi_archive',commerce);check('public_research_archive',research);check('synthetic_website_archive',website)
    return {'schema_version':1,'artifact_delivery_ready':not errors,'checks':checks,'errors':errors,
        'native_bi_release_decision':'HOLD','desktop_render_verified':False,'native_refresh_verified':False,
        'dax_engine_executed':False,'browser_render_verified':False,'live_refresh_required_for_historical_portfolio':False,
        'scope':'Content-addressed offline portfolio artifacts. This audit does not run Power BI, a browser, DAX, or cloud queries.'}


def write_report(result,out,root=ROOT):
    out.mkdir(parents=True,exist_ok=True)
    (out/'release_audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    rows='\n'.join('| '+r['name']+' | '+('PASS' if r['passed'] else 'FAIL')+' |' for r in result['checks'])
    delivery=Path(os.path.relpath(root/'docs/DELIVERY.md',out)).as_posix()
    text=f'''# Portfolio delivery readiness

Regenerate with `python -m scripts.release_audit --out docs`. This checks the actual published ZIP bytes, not a different working build. It performs no network requests or UI automation.

**Portable artifact delivery: {'READY' if result['artifact_delivery_ready'] else 'BLOCKED'}. Native Power BI acceptance: HOLD.**

| Deliverable | Offline artifact checks |
| --- | --- |
{rows}

The checks cover pinned archive size/SHA-256, bounded safe archive paths, PBIP/report/model bindings, page/table counts, portable model paths, official logo bytes, matching research sources/aggregate hashes, current bundled reports/protocol/query, report links, and synthetic-only website provenance. They do not establish visual fidelity, successful refresh, or DAX results. Microsoft schema and TOM parser results are separate checks recorded in [delivery evidence]({delivery}).

The research package contains five reports and twelve figures alongside a nine-page/sixteen-table native BI project. Review-selection sensitivity is a companion report, without a separate native page; temporal forecasting has its own native page. E-Commerce and Greenweez fixtures remain synthetic, and Olist remains a separate historical public study under CC BY-NC-SA 4.0. A live private-source refresh is not required to present that explicitly historical portfolio; it is required before making new live-business claims.

Outstanding native acceptance requires actual Power BI opening, refresh, DAX execution and visual inspection. This command cannot promote those gates. Browser and PC-screen automation remain excluded from this workflow. PR review and merging are independent repository actions and are not performed by this audit.
'''
    if result['errors']:text+='\nArtifact errors:\n\n'+'\n'.join('- '+e for e in result['errors'])+'\n'
    (out/'RELEASE_READINESS.md').write_text(text,encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--out',type=Path,default=ROOT/'target/release');p.add_argument('--require-native',action='store_true')
    args=p.parse_args();result=audit(args.root);write_report(result,args.out,args.root)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['artifact_delivery_ready'] and not args.require_native else 1)
