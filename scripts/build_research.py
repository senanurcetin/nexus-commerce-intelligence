"""Rebuild all five public Olist studies and native BI from six local CSVs.

No download, cloud query, browser, screen automation or paid service. Optional
schema checks retrieve only Microsoft JSON schemas if absent from the cache.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import advanced_olist as core
from scripts import olist_customer_portfolio as customer
from scripts import olist_delivery_operations as operations
from scripts import olist_review_selection as reviews
from scripts import olist_forecast as forecast
from scripts.build_olist_powerbi import create, package
from scripts.research_environment import inspect as inspect_environment


def pipeline_inputs():
    """Version the local scientific/reporting inputs, separately from raw CSVs."""
    paths=[core.ROOT/'scripts'/name for name in (
        'build_research.py','advanced_olist.py','olist_customer_portfolio.py','olist_delivery_operations.py',
        'olist_review_selection.py','olist_forecast.py','build_olist_powerbi.py','build_powerbi.py','powerbi_design.py','research_environment.py')]
    paths+=sorted(core.SQL.glob('*.sql'))
    paths+=[reviews.PROTOCOL,forecast.PROTOCOL,core.ROOT/'requirements-research.in',
            core.ROOT/'requirements-research.lock',core.ROOT/'branding/nexus_official_transparent.png']
    return {p.relative_to(core.ROOT).as_posix():core.sha256(p) for p in paths}


def build(raw: Path,out: Path,*,schemas=False) -> dict:
    raw,out=raw.resolve(),out.resolve()
    if raw==out or raw in out.parents or out in raw.parents:
        raise ValueError('Raw inputs and research outputs must be separate directories')
    out.mkdir(parents=True,exist_ok=True)
    receipt=out/'research_build.json'
    receipt.unlink(missing_ok=True)  # A failed rebuild cannot retain a success receipt.
    inputs=pipeline_inputs()
    core.run(raw,out)
    customer.run(raw,out)
    operations.run(raw,out)
    reviews.run(raw,out)
    forecast.run(raw,out)
    if pipeline_inputs()!=inputs:raise ValueError('Pipeline inputs changed during research build')
    project=create(out,out/'powerbi')
    count=None
    if schemas:
        from scripts.validate_powerbi_schema import validate
        count=validate(project.parent)
    archive=out/'NEXUS_Olist_Research.zip'
    package(project,archive)
    if pipeline_inputs()!=inputs:raise ValueError('Pipeline inputs changed during research export')
    result={'status':'complete','source_kind':'historical_public_olist','analytical_reports':[
        'REPORT.md','CUSTOMER_PORTFOLIO.md','DELIVERY_OPERATIONS.md','REVIEW_SELECTION.md','FORECAST_VALIDATION.md'],
        'project':project.relative_to(out).as_posix(),'archive':archive.name,
        'archive_sha256':core.sha256(archive),'schema_artifacts_validated':count,
        'environment':inspect_environment(),
        'pipeline_inputs_sha256':inputs,'pipeline_inputs_stable_during_build':True,
        'desktop_render_verified':False,'dax_engine_executed':False,
        'microsoft_tom_tmdl_parsed':False,
        'note':'Rebuild succeeded; native engine/parser acceptance remains separate from this command.'}
    receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=core.ROOT/'target/olist/raw')
    parser.add_argument('--out',type=Path,default=core.ROOT/'target/research')
    parser.add_argument('--schemas',action='store_true',help='Validate native JSON with official Microsoft schemas')
    args=parser.parse_args();print(json.dumps(build(args.raw,args.out,schemas=args.schemas),indent=2))
