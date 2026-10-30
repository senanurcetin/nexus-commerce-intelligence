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


def build(raw: Path,out: Path,*,schemas=False) -> dict:
    raw,out=raw.resolve(),out.resolve()
    if raw==out or raw in out.parents or out in raw.parents:
        raise ValueError('Raw inputs and research outputs must be separate directories')
    out.mkdir(parents=True,exist_ok=True)
    receipt=out/'research_build.json'
    receipt.unlink(missing_ok=True)  # A failed rebuild cannot retain a success receipt.
    core.run(raw,out)
    customer.run(raw,out)
    operations.run(raw,out)
    reviews.run(raw,out)
    forecast.run(raw,out)
    project=create(out,out/'powerbi')
    count=None
    if schemas:
        from scripts.validate_powerbi_schema import validate
        count=validate(project.parent)
    archive=out/'NEXUS_Olist_Research.zip'
    package(project,archive)
    result={'status':'complete','source_kind':'historical_public_olist','analytical_reports':[
        'REPORT.md','CUSTOMER_PORTFOLIO.md','DELIVERY_OPERATIONS.md','REVIEW_SELECTION.md','FORECAST_VALIDATION.md'],
        'project':project.relative_to(out).as_posix(),'archive':archive.name,
        'archive_sha256':core.sha256(archive),'schema_artifacts_validated':count,
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
