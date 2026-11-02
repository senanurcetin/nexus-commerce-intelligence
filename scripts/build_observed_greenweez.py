"""Build selected existing finance marts against the ignored observed snapshot.

Local DuckDB only. Does not seed, call cloud jobs, overwrite demo databases or
certify financial interpretation. Logs, model SQL, rows and amounts stay private.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import duckdb
from scripts.profile_core_source import load,profile
from scripts.read_core_source import ROOT,PRIVATE_ROOT


def build(snapshot:Path):
    snapshot=snapshot.resolve()
    if PRIVATE_ROOT.resolve() not in snapshot.parents:raise ValueError('Private observed snapshot required')
    out=snapshot/'analysis/dbt';out.mkdir(parents=True,exist_ok=True)
    success=out/'verified_build.json'
    success.unlink(missing_ok=True)
    analysis=profile(snapshot)
    if not analysis['greenweez']['joins_safe']:raise ValueError('Unsafe source join keys; build blocked')
    database=out/'observed.duckdb'
    con=duckdb.connect(str(database))
    try:
        for alias in json.loads((snapshot/'receipt.json').read_text())['tables']:
            con.execute(f'drop table if exists "{alias}"')
        load(con,snapshot)
        con.execute('create schema if not exists analytics')
        for alias in json.loads((snapshot/'receipt.json').read_text())['tables']:
            if alias.startswith('greenweez.'):
                table=alias.split('.',1)[1]
                con.execute(f'create or replace table analytics."{table}" as select * from "{alias}"')
        # Source aliases are only temporary import bindings; private finance tables persist.
        for alias in json.loads((snapshot/'receipt.json').read_text())['tables']:
            con.execute(f'drop table "{alias}"')
    finally:con.close()
    profiles=out/'profiles';profiles.mkdir(exist_ok=True)
    (profiles/'profiles.yml').write_text('default:\n  target: observed\n  outputs:\n    observed:\n      type: duckdb\n      path: '+json.dumps(str(database))+'\n      schema: analytics\n      threads: 1\n',encoding='utf-8')
    command=[sys.executable,'-m','dbt.cli.main','build','--project-dir',str(ROOT/'integrations/greenweez'),
        '--profiles-dir',str(profiles),'--target','observed','--target-path',str(out/'target'),
        '--log-path',str(out/'logs'),'--vars',json.dumps({'source_system':'fvt_gsheet','refund_unit_verified':False}),
        '--select','+finance_days','+finance_refunds_month','+finance_campaigns_month',
        '--indirect-selection','cautious','--exclude','test_type:unit']
    with (out/'console.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=False)
    if result.returncode:raise RuntimeError('Observed local dbt build failed; inspect private console.log')
    results=json.loads((out/'target/run_results.json').read_text())['results']
    counts={status:sum(r['status']==status for r in results) for status in sorted({r['status'] for r in results})}
    if any(r['status'] not in ('success','pass','warn') for r in results):raise RuntimeError('Observed dbt result was not successful')
    with duckdb.connect(str(database),read_only=True) as con:
        orders=con.execute('select count(*) from analytics.int_orders_margin').fetchone()[0]
        expected=analysis['greenweez']['keys']['orders']['rows']
        if orders!=expected:raise ValueError('Observed dbt order population differs from source')
        # Default dbt custom-schema naming is analytics_finance.
        leaked=con.execute('select count(*) from analytics_finance.finance_refunds_month where net_revenue_after_refunds is not null').fetchone()[0]
        if leaked:raise ValueError('Unverified refund units produced net revenue')
    receipt={'scope':'private_local_observed_greenweez_selected_finance_marts','source_orders':orders,
        'source_receipt_sha256':hashlib.sha256((snapshot/'receipt.json').read_bytes()).hexdigest(),
        'profile_sha256':hashlib.sha256((snapshot/'analysis/profile.json').read_bytes()).hexdigest(),
        'node_status_counts':counts,'refund_adjusted_net_revenue_remains_null':True,
        'query_jobs_created':0,'synthetic_seeds_loaded':False,'financial_semantics_certified':False}
    success.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return receipt


if __name__=='__main__':
    source=PRIVATE_ROOT/json.loads((PRIVATE_ROOT/'latest.json').read_text())['snapshot']
    print(json.dumps(build(source),indent=2))
