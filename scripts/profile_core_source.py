"""Profile authenticated core-source snapshots locally, without publishing amounts.

Unknown currency/refund/cost timing remain unknown. Public status contains only
table row counts and gate outcomes; all numerical finance output stays ignored.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP,localcontext
import hashlib
import json
from pathlib import Path

import duckdb

from scripts.read_core_source import ROOT,PRIVATE_ROOT,CONTRACT

SEMANTICS=ROOT/'contracts/financial_semantics.json'


def amount(column):return f'try_cast("{column}" as decimal(38,9))'


def key_quality(con,table,key):
    rows,present,distinct=con.execute(f'select count(*),count("{key}"),count(distinct "{key}") from "{table}"').fetchone()
    return {'rows':rows,'missing_keys':rows-present,'duplicate_key_rows':present-distinct,'unique_nonnull_keys':rows==present==distinct}


def load(con,snapshot):
    receipt=json.loads((snapshot/'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('status')!='complete_observed_snapshot' or receipt.get('query_jobs_created')!=0 or receipt.get('publication_allowed') is not False:
        raise ValueError('An observed no-query private snapshot is required')
    contract=json.loads(CONTRACT.read_text(encoding='utf-8'))
    if receipt['contract_sha256']!=hashlib.sha256(CONTRACT.read_bytes()).hexdigest() or set(receipt['tables'])!=set(contract['tables']):
        raise ValueError('Snapshot source contract differs from the current fixed contract')
    for alias,t in receipt['tables'].items():
        file=snapshot/(alias+'.csv')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=t['csv_sha256']:raise ValueError('Raw snapshot file hash mismatch')
        columns={c['name'] for c in t['columns']}
        if columns!=set(contract['tables'][alias]):raise ValueError('Unexpected snapshot projection')
        con.execute(f'create table "{alias}" as select * from read_csv(?,header=true,all_varchar=true)',[str(file)])
        if con.execute(f'select count(*) from "{alias}"').fetchone()[0]!=t['rows']:raise ValueError('Snapshot row count does not reconcile')
    return receipt


def independent_sum(path,column):
    total=Decimal(0)
    with path.open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            value=row[column]
            if value:
                try:
                    with localcontext() as ctx:
                        ctx.prec=50
                        d=Decimal(value)
                        if not d.is_finite() or abs(d)>=Decimal('1e29'):continue
                        total+=d.quantize(Decimal('.000000001'),rounding=ROUND_HALF_UP)
                except InvalidOperation:continue
    return total


def ecommerce(con):
    keys={t:key_quality(con,'ecommerce.'+t,'id') for t in ('order_items','products')}
    statuses=con.execute('''select coalesce(status,'__missing__') as status,count(*) as item_rows
        from "ecommerce.order_items" group by 1 order by 1''').df()
    base=con.execute(f'''select count(*) as item_rows,count(distinct order_id) as period_distinct_order_keys,
        count(*) filter(where order_id is null) as missing_order_keys,
        count(*) filter(where user_id is null) as missing_customer_keys,
        count(*) filter(where {amount('sale_price')} is null) as invalid_or_missing_sale_prices,
        count(*) filter(where {amount('sale_price')}<0) as negative_sale_prices,
        count(*) filter(where try_cast(created_at as double) is null) as invalid_or_missing_creation_timestamps,
        min((to_timestamp(try_cast(created_at as double)) at time zone 'UTC')::date) as item_created_start_utc,
        max((to_timestamp(try_cast(created_at as double)) at time zone 'UTC')::date) as item_created_end_utc
        from "ecommerce.order_items"''').df().to_dict('records')[0]
    eligible=keys['order_items']['unique_nonnull_keys'] and keys['products']['unique_nonnull_keys']
    result={'keys':keys,'source_profile':base,'cost_join_safe':eligible}
    if eligible:
        con.execute(f'''create table item_costs as select o.*,p.category,
            {amount('sale_price')} as value,try_cast(p.cost as decimal(38,9)) as catalogue_cost,
            p.id is not null as product_matched
            from "ecommerce.order_items" o left join "ecommerce.products" p on o.product_id=p.id''')
        result['joined_rows']=con.execute('select count(*) from item_costs').fetchone()[0]
        if result['joined_rows']!=keys['order_items']['rows']:raise ValueError('Item/product join expanded the source')
        result['orphan_product_rows']=con.execute('select count(*) from item_costs where not product_matched').fetchone()[0]
        result['completed_cost_coverage']=con.execute('''select count(*) as completed_item_rows,
            count(*) filter(where catalogue_cost>=0 and value>=0) as eligible_cost_rows,
            sum(value) as completed_item_value,
            sum(case when catalogue_cost>=0 and value>=0 then value end) as known_cost_completed_value,
            sum(case when catalogue_cost>=0 and value>=0 then value-catalogue_cost end) as known_cost_catalogue_contribution
            from item_costs where lower(status)='complete' ''').df().to_dict('records')[0]
    return result,statuses


def greenweez(con):
    tables={'orders':'gwz_finance_orders_orders','shipping':'gwz_finance_shipping_shipping','refund':'gwz_finance_refund_sheet_1'}
    keys={key:key_quality(con,'greenweez.'+table,'orders_id') for key,table in tables.items()}
    fields={'orders':('turnover','purchase_cost','ship_fee'),'shipping':('log_cost','ship_cost'),'refund':('refund',)}
    quality={}
    for key,columns in fields.items():
        table='greenweez.'+tables[key]
        quality[key]={column:con.execute(f'''select count(*) filter(where {amount(column)} is null),
            count(*) filter(where {amount(column)}=0),count(*) filter(where {amount(column)}<0) from "{table}"''').fetchone() for column in columns}
    result={'keys':keys,'amount_quality_missing_zero_negative':quality,'joins_safe':all(k['unique_nonnull_keys'] for k in keys.values()),
            'refund_unit_verified':False,'currency_verified':False,'net_revenue_after_refunds':None}
    if not result['joins_safe']:return result,None
    con.execute('''create table finance_components as
        select o.orders_id,try_cast(substr(o.datetime,1,10) as date) as order_day,
        try_cast(s.date_date as date) as shipping_day,try_cast(substr(r.datetime,1,10) as date) as refund_day,
        try_cast(o.turnover as decimal(38,9)) as turnover,
        try_cast(o.purchase_cost as decimal(38,9)) as purchase_cost,
        try_cast(o.ship_fee as decimal(38,9)) as ship_fee,
        try_cast(s.log_cost as decimal(38,9)) as log_cost,
        try_cast(s.ship_cost as decimal(38,9)) as ship_cost,
        try_cast(r.refund as decimal(38,9)) as refund_value,
        s.orders_id is not null as shipping_matched,r.orders_id is not null as refund_matched
        from "greenweez.gwz_finance_orders_orders" o
        left join "greenweez.gwz_finance_shipping_shipping" s using(orders_id)
        left join "greenweez.gwz_finance_refund_sheet_1" r using(orders_id)''')
    if con.execute('select count(*) from finance_components').fetchone()[0]!=keys['orders']['rows']:
        raise ValueError('Finance component join expanded orders')
    con.execute('''create table finance_eligible as select *,
        order_day is not null and order_day=shipping_day and turnover>=0 and purchase_cost>=0
        and ship_fee>=0 and log_cost>=0 and ship_cost>=0 as complete_components
        from finance_components''')
    summary=con.execute('''select count(*) as source_orders,
        count(*) filter(where not shipping_matched) as missing_shipping,
        count(*) filter(where not refund_matched) as missing_refund,
        count(*) filter(where order_day is null) as missing_or_invalid_order_dates,
        count(*) filter(where shipping_matched and shipping_day<>order_day) as shipping_order_date_mismatches,
        count(*) filter(where refund_matched and refund_day<>order_day) as refund_order_date_mismatches,
        count(*) filter(where refund_value>turnover) as numeric_refund_above_turnover,
        count(*) filter(where complete_components) as complete_component_orders,
        sum(turnover) as source_turnover,
        sum(case when complete_components then turnover end) as complete_component_turnover,
        sum(case when complete_components then turnover-purchase_cost+ship_fee-log_cost-ship_cost end) as complete_component_subtotal
        from finance_eligible''').df().to_dict('records')[0]
    result['component_coverage']=summary
    result['refund_distribution']=con.execute('''select min(refund_value),max(refund_value),
        count(distinct refund_value),count(*) filter(where refund_value>0) from finance_eligible''').fetchone()
    daily=con.execute('''select order_day,count(*) as source_orders,sum(turnover) as turnover_as_stored,
        count(*) filter(where complete_components) as complete_component_orders,
        sum(case when complete_components then turnover-purchase_cost+ship_fee-log_cost-ship_cost end) as complete_component_subtotal
        from finance_eligible group by 1 order by 1''').df()
    return result,daily


def profile(snapshot:Path):
    snapshot=snapshot.resolve()
    if PRIVATE_ROOT.resolve() not in snapshot.parents:raise ValueError('Only local ignored core-source snapshots are accepted')
    out=snapshot/'analysis';out.mkdir(exist_ok=True)
    (out/'profile.json').unlink(missing_ok=True)
    con=duckdb.connect()
    try:
        receipt=load(con,snapshot);ecom,statuses=ecommerce(con);finance,daily=greenweez(con)
        for alias,column in (('ecommerce.order_items','sale_price'),('greenweez.gwz_finance_orders_orders','turnover')):
            expected=independent_sum(snapshot/(alias+'.csv'),column)
            observed=con.execute(f'select sum({amount(column)}) from "{alias}"').fetchone()[0]
            if abs(expected-(observed or Decimal(0)))>Decimal('.001'):raise ValueError('Independent raw scalar reconciliation failed')
    finally:con.close()
    statuses.to_csv(out/'ecommerce_status_counts.csv',index=False,lineterminator='\n')
    if daily is not None:daily.to_csv(out/'greenweez_observed_daily.csv',index=False,lineterminator='\n')
    result={'provenance':receipt['origin_classification'],'snapshot_observed_at_utc':receipt['observed_at_utc'],
        'ecommerce':ecom,'greenweez':finance,'independent_raw_amount_reconciliation':True,
        'financial_contract_sha256':hashlib.sha256(SEMANTICS.read_bytes()).hexdigest(),
        'raw_rows_publication_allowed':False,'financial_amounts_publication_allowed':False,'profit_certified':False,
        'interpretation':'Source-observed fields and catalogue-cost/component arithmetic. Currency, tax/shipping inclusion, refund meaning, transaction-time COGS and original real-business provenance remain unverified.'}
    (out/'profile.json').write_text(json.dumps(result,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')
    (out/'REPORT.md').write_text('''# Private core-source profile

These are authenticated warehouse observations, not proof of original real business transactions. Amounts stay local. No SQL query job, Storage API or public snapshot replacement was performed.

`profile.json` records source key quality, coverage, numeric-field problems, date mismatches, and independent raw amount reconciliation. `ecommerce_status_counts.csv` retains current item statuses. `greenweez_observed_daily.csv` contains as-stored daily observations and a same-date complete-component subtotal.

E-Commerce item creation timestamps are converted from the source TIMESTAMP epoch to UTC calendar dates; they are not asserted order booking dates. Completed value and catalogue-cost contribution do not certify recognised revenue or transaction-time profit. Return status does not establish cash refunded.

Greenweez date strings use their explicit first ten ISO characters, consistent with the existing staging contract. Refund meaning stays unverified and no refund amount is subtracted. A numerically larger refund field does not prove an over-refund when units are unknown. Complete-component subtotals select unique, valid-date, nonnegative source components; they are not whole-business profit or monetary bounds. Advertising is not allocated to those selected orders.

The static public commerce demo is unchanged. These outputs are ignored local files, separate from historical public Olist research and the original Greenweez raw-branch synthetic fixtures.
''',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path);a=p.parse_args()
    source=a.snapshot or PRIVATE_ROOT/json.loads((PRIVATE_ROOT/'latest.json').read_text())['snapshot']
    result=profile(source)
    print(json.dumps({'ecommerce_item_rows':result['ecommerce']['keys']['order_items']['rows'],
        'ecommerce_product_keys_safe':result['ecommerce']['keys']['products']['unique_nonnull_keys'],
        'greenweez_order_rows':result['greenweez']['keys']['orders']['rows'],
        'greenweez_joins_safe':result['greenweez']['joins_safe'],
        'independent_raw_amount_reconciliation':result['independent_raw_amount_reconciliation'],
        'currency_verified':False,'refund_meaning_verified':False,'public_demo_changed':False},indent=2))
