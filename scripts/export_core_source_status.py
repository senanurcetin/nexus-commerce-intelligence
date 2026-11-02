"""Project a strict, amount-free evidence allowlist from an ignored local snapshot."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import duckdb

from scripts.read_core_source import ROOT,PRIVATE_ROOT,CONTRACT
from scripts.profile_core_source import SEMANTICS,load


def project(receipt,analysis,dbt):
    contract_hash=hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    semantics_hash=hashlib.sha256(SEMANTICS.read_bytes()).hexdigest()
    aliases=set(json.loads(CONTRACT.read_text())['tables'])
    if receipt['contract_sha256']!=contract_hash or set(receipt['tables'])!=aliases:
        raise ValueError('Source contract mismatch')
    if analysis['financial_contract_sha256']!=semantics_hash:raise ValueError('Financial contract mismatch')
    if receipt['status']!='complete_observed_snapshot' or receipt['publication_allowed'] is not False:
        raise ValueError('Private complete snapshot required')
    if receipt['query_jobs_created']!=0 or receipt['storage_read_api_used'] is not False:
        raise ValueError('Unexpected source transport')
    if not 0<receipt['response_bytes']<=100_000_000:raise ValueError('Response budget mismatch')
    if analysis['snapshot_observed_at_utc']!=receipt['observed_at_utc']:raise ValueError('Mixed snapshot evidence')
    if not analysis['independent_raw_amount_reconciliation']:raise ValueError('Amount reconciliation failed')
    orders=analysis['greenweez']['keys']['orders']['rows']
    if dbt['source_orders']!=orders or not dbt['refund_adjusted_net_revenue_remains_null']:
        raise ValueError('Observed dbt population or refund gate mismatch')
    if not dbt['node_status_counts'].get('success') or any(k not in ('success','pass','warn') or type(v) is not int or v<0 for k,v in dbt['node_status_counts'].items()):
        raise ValueError('Unsuccessful observed dbt nodes')
    return {'schema_version':1,'observed_at_utc':receipt['observed_at_utc'],
        'origin_classification':receipt['origin_classification'],
        'transport':'bigquery_rest_tabledata_list','response_bytes':receipt['response_bytes'],
        'maximum_response_bytes':100_000_000,'query_jobs_created':0,'storage_read_api_used':False,
        'source_contract_sha256':contract_hash,'financial_contract_sha256':semantics_hash,
        'tables':{alias:{'rows':receipt['tables'][alias]['rows']} for alias in sorted(aliases)},
        'gates':{'ecommerce_unique_item_and_product_keys':all(k['unique_nonnull_keys'] for k in analysis['ecommerce']['keys'].values()),
            'greenweez_unique_order_component_keys':analysis['greenweez']['joins_safe'],
            'independent_raw_amount_reconciliation':True,
            'greenweez_dbt_refund_adjusted_net_revenue_remains_null':True,
            'currency_verified':False,'refund_meaning_verified':False,'transaction_time_cogs_verified':False,
            'original_real_business_origin_verified':False,'native_bi_execution_verified':False},
        'local_observed_greenweez_dbt':{'source_orders':orders,'node_status_counts':dbt['node_status_counts'],
            'synthetic_seeds_loaded':False,'financial_semantics_certified':False},
        'public_commerce_payload_replaced':False,'raw_rows_published':False,'financial_amounts_published':False}


def export(snapshot:Path):
    snapshot=snapshot.resolve()
    if PRIVATE_ROOT.resolve() not in snapshot.parents:raise ValueError('Private snapshot required')
    def read(relative):return json.loads((snapshot/relative).read_text(encoding='utf-8'))
    dbt=read('analysis/dbt/verified_build.json')
    for key,path in (('source_receipt_sha256','receipt.json'),('profile_sha256','analysis/profile.json')):
        if dbt[key]!=hashlib.sha256((snapshot/path).read_bytes()).hexdigest():raise ValueError('Stale observed dbt receipt')
    con=duckdb.connect()
    try:load(con,snapshot)  # Reject edited raw files even if the old receipts survive.
    finally:con.close()
    status=project(read('receipt.json'),read('analysis/profile.json'),dbt)
    out=ROOT/'docs/core-source';out.mkdir(exist_ok=True)
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
    return status


if __name__=='__main__':
    source=PRIVATE_ROOT/json.loads((PRIVATE_ROOT/'latest.json').read_text())['snapshot']
    status=export(source)
    print(json.dumps({'status':'amount_free_source_evidence_exported','tables':len(status['tables'])}))
