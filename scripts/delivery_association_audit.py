"""Independent raw replay of the original retrospective delivery association.

Reuses only the separate CSV audit's parsing/hash/order-statistic primitives;
never imports the production order fact, SQL, analysis or bootstrap. No network.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform

import numpy as np

from scripts import review_cluster_audit as helper
from scripts.review_cluster_audit import FILES,ROOT,rows,timestamp,finite,digest,need,percentile,close

START=datetime(2017,1,1)
CUTOFF=datetime(2018,8,1)


def reconstruction(raw):
    customers={};counts={}
    for r in rows(raw/FILES['customers'],('customer_id','customer_unique_id')):
        key=r['customer_id'];need(key and key not in customers,'Invalid customer primary key')
        customers[key]=r['customer_unique_id']
    counts[FILES['customers']]=len(customers)
    orders={}
    for r in rows(raw/FILES['orders'],('order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date')):
        key=r['order_id'];need(key and key not in orders,'Invalid order primary key')
        need(r['customer_id'] in customers,'Orphan order customer')
        orders[key]=(customers[r['customer_id']],r['order_status'],timestamp(r['order_purchase_timestamp']),
                     timestamp(r['order_delivered_customer_date']),timestamp(r['order_estimated_delivery_date']))
    counts[FILES['orders']]=len(orders)
    items=set();positive=set();n=0
    for r in rows(raw/FILES['order_items'],('order_id','order_item_id','price','freight_value')):
        key=(r['order_id'],r['order_item_id']);need(key not in items,'Duplicate order-item key');items.add(key)
        need(r['order_id'] in orders,'Orphan item order')
        need(finite(r['price'])>0 and finite(r['freight_value'])>=0,'Invalid item value')
        positive.add(r['order_id']);n+=1
    counts[FILES['order_items']]=n
    latest={};before_cutoff={};n=0
    for r in rows(raw/FILES['order_reviews'],('order_id','review_id','review_score','review_creation_date','review_answer_timestamp')):
        key=r['order_id'];need(key in orders,'Orphan review order');n+=1
        score=finite(r['review_score']);need(score.is_integer() and 1<=score<=5,'Invalid review score')
        answered=timestamp(r['review_answer_timestamp']);created=timestamp(r['review_creation_date'])
        priority=(answered or datetime.min,created or datetime.min,bool(r['review_id']),r['review_id'],int(score))
        entry=(priority,int(score),answered)
        if key not in latest or priority>latest[key][0]:latest[key]=entry
        if answered is not None and answered<CUTOFF:
            if key not in before_cutoff or priority>before_cutoff[key][0]:before_cutoff[key]=entry
    counts[FILES['order_reviews']]=n
    clusters=defaultdict(lambda:np.zeros(4,dtype=np.int64));months=defaultdict(lambda:np.zeros(4,dtype=np.int64))
    all_timing=np.zeros(4,dtype=np.int64);restricted=np.zeros(4,dtype=np.int64);temporal=Counter()
    def add(vector,late,score):
        offset=0 if late else 2;vector[offset]+=score<=2;vector[offset+1]+=1
    for key,(person,status,purchased,delivered,promised) in orders.items():
        if not (person and key in positive and status=='delivered' and purchased and delivered and promised
                and START<=purchased<CUTOFF and delivered>=purchased
                and promised>=purchased.replace(hour=0,minute=0,second=0,microsecond=0)):continue
        late=delivered.date()>promised.date();entry=latest.get(key)
        if entry:
            add(all_timing,late,entry[1])
            if entry[2] is not None and entry[2]>=delivered:
                add(clusters[person],late,entry[1]);add(months[purchased.strftime('%Y-%m-01')],late,entry[1])
                temporal['sample_orders']+=1
                temporal['delivery_on_or_after_cutoff']+=delivered>=CUTOFF
                temporal['selected_answer_on_or_after_cutoff']+=entry[2]>=CUTOFF
                temporal['delivery_or_selected_answer_on_or_after_cutoff']+=(delivered>=CUTOFF or entry[2]>=CUTOFF)
        # Select latest *within* the event boundary first, rather than merely
        # filtering the retrospectively selected latest answer afterward.
        historical=before_cutoff.get(key)
        if delivered<CUTOFF and historical and historical[2]>=delivered:
            add(restricted,late,historical[1])
            temporal['post_cutoff_latest_replaced_with_earlier_eligible_answer_orders']+=(entry is not None and entry[2] is not None and entry[2]>=CUTOFF)
    need(bool(clusters),'No eligible reviewed customers')
    ledger=np.stack([clusters[person] for person in sorted(clusters)])
    return ledger,months,all_timing,dict(temporal),restricted,counts


def difference(counts):
    return float(counts[0]/counts[1]-counts[2]/counts[3]) if min(counts[1],counts[3])>0 else None


def bootstrap(ledger,iterations=1000,seed=20261027):
    ledger=np.asarray(ledger)
    need(ledger.ndim==2 and ledger.shape[1]==4 and len(ledger)>0,'Invalid customer ledger')
    need(np.isfinite(ledger).all() and (ledger>=0).all() and (ledger%1==0).all(),'Invalid integer cluster counts')
    need((ledger[:,0]<=ledger[:,1]).all() and (ledger[:,2]<=ledger[:,3]).all(),'Poor counts exceed group counts')
    need(isinstance(iterations,int) and iterations>=100,'At least 100 replicates required')
    need(difference(ledger.sum(axis=0)) is not None,'Both delivery groups required')
    rng=np.random.default_rng(seed);values=[]
    for _ in range(iterations):
        # Identical declared random indices, independent multiplicity-weighted
        # reduction instead of a copied resampled order-count matrix.
        indices=rng.integers(0,len(ledger),len(ledger))
        multiplicities=np.bincount(indices,minlength=len(ledger))
        estimate=difference(multiplicities@ledger)
        if estimate is not None:values.append(estimate)
    need(len(values)>=.95*iterations,'Insufficient two-group bootstrap support')
    total=ledger.sum(axis=0)
    return {'risk_difference':difference(total),'ci_low':float(percentile(values,.025)),
        'ci_high':float(percentile(values,.975)),'customers':len(ledger),'iterations':iterations,
        'valid_replicates':len(values),'seed':seed,
        **{name:int(value) for name,value in zip(('late_poor','late_orders','on_time_poor','on_time_orders'),total)}}


def validate(raw,published):
    evidence=json.loads((published/'evidence.json').read_text(encoding='utf-8'))
    need(evidence['source_kind']=='historical_public_olist' and evidence['synthetic'] is False,'Unsupported study provenance')
    need(evidence['summary']['cutoff']=='2018-08-01','Unsupported study cutoff')
    original=evidence['summary']['delivery_association']
    need(original['iterations']==1000 and original['seed']==20261027,'Unsupported bootstrap specification')
    for filename in FILES.values():
        path=raw/filename;meta=evidence['quality']['files'][filename]
        need(digest(path)==meta['sha256'] and path.stat().st_size==meta['bytes'],'Raw hash/size mismatch')
    for filename in ('delivery_months.csv','delivery_common_support.csv'):
        need(digest(published/filename)==evidence['export_sha256'][filename],'Published aggregate hash mismatch')
    ledger,months,all_timing,temporal,restricted,counts=reconstruction(raw)
    need(all(counts[f]==evidence['quality']['files'][f]['rows'] for f in counts),'Raw row counts differ')
    result=bootstrap(ledger)
    need(set(original)==set(result),'Published association fields differ')
    for key,value in result.items():
        if key in ('risk_difference','ci_low','ci_high'):close(original[key],value,'Independent association differs: '+key)
        else:need(original[key]==value,'Independent bootstrap metadata/counts differ')
    observed={}
    for r in rows(published/'delivery_months.csv',('month','late','orders','poor')):
        key=(r['month'],r['late']);need(key not in observed and r['late'] in ('True','False'),'Invalid/repeated monthly cell')
        observed[key]=(int(r['orders']),int(r['poor']))
    expected={}
    for month,values in months.items():
        for flag,offset in (('True',0),('False',2)):
            if values[offset+1]:expected[month,flag]=(int(values[offset+1]),int(values[offset]))
    need(observed==expected,'Independent monthly cells differ')
    common={month:(int(v[1]+v[3]),difference(v)) for month,v in months.items() if min(v[1],v[3])>=30}
    common_path=published/'delivery_common_support.csv'
    table=list(rows(common_path,('month','orders','risk_difference'))) if common or common_path.read_text(encoding='utf-8').strip() else []
    need(len(table)==len(common)==evidence['summary']['common_support_months'],'Common-support count differs')
    seen=set()
    for row in table:
        month=row['month'];need(month not in seen and month in common,'Invalid/repeated common-support month');seen.add(month)
        n,contrast=common[month];need(int(row['orders'])==n,'Pooled month denominator differs')
        close(row['risk_difference'],contrast,'Common-month contrast differs')
    standardized=sum(n*d for n,d in common.values())/sum(n for n,_ in common.values()) if common else None
    if standardized is None:need(evidence['summary']['month_standardized_risk_difference'] is None,'Unavailable standardization must stay null')
    else:close(evidence['summary']['month_standardized_risk_difference'],standardized,'Month standardization differs')
    timing=evidence['summary']['all_review_timing_sensitivity']
    for key,value in zip(('late_poor','late_orders','on_time_poor','on_time_orders'),all_timing):need(timing[key]==int(value),'All-timing count differs')
    close(timing['risk_difference'],difference(all_timing),'All-timing contrast differs')
    return {'association':result,'monthly_cells_reconciled':len(observed),'common_support_months':len(common),
        'month_standardized_risk_difference':standardized,'all_review_timing_counts_reconciled':True,
        'retrospective_event_boundary':temporal,
        'event_time_restricted_sensitivity':{
            **{name:int(value) for name,value in zip(('late_poor','late_orders','on_time_poor','on_time_orders'),restricted)},
            'risk_difference':difference(restricted),'sampling_interval_computed':False,
            'policy':'Delivery before 2018-08-01; select latest dated answer before cutoff, then require answer at/after delivery; same purchase window and final delivered status.',
            'original_ingestion_or_status_availability_verified':False,'genuine_point_in_time_backtest':False,
            'interpretation':'Different event-restricted selected sample; descriptive sensitivity only, not a causal effect or live-data reconstruction.'}}


def audit(raw,published):
    implementation=lambda:hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    result={'schema_version':1,'acceptance':'FAIL','implementation_sha256':implementation(),
        'runtime':{'python':platform.python_version(),'numpy':np.__version__},'raw_rows_exported':False,
        'derived_license':'CC-BY-NC-SA-4.0','source':'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce',
        'scope':'Original retrospective delivery-association raw cohort, latest review, customer-cluster percentile limits, monthly/common-support and all-timing arithmetic; event-boundary counts and separate descriptive event-restricted sensitivity. Not state Fisher/FDR, source authenticity, causality, real as-of availability or native BI.',
        'causal_acceptance':'HOLD','native_bi_acceptance':'HOLD'}
    try:
        paths={**{'raw/'+f:raw/f for f in FILES.values()},
            **{'published/'+f:published/f for f in ('evidence.json','delivery_months.csv','delivery_common_support.csv')},
            'independent_csv_helper':Path(helper.__file__)}
        def snapshot():return {key:(digest(path) if key.startswith('raw/') else hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()) for key,path in paths.items()}
        before=snapshot();result['input_sha256']=before
        result['details']=validate(raw,published)
        need(before==snapshot() and implementation()==result['implementation_sha256'],'Inputs or validator changed during replay')
        result.update(acceptance='PASS',inputs_stable_during_validation=True,
            hash_basis='raw inputs byte-exact; public text/helper LF-normalized',numpy_rng_shared_for_declared_seed=True)
    except (ValueError,KeyError,TypeError,OSError,OverflowError,csv.Error):
        result.pop('details',None);result['error']='Input integrity, cohort, aggregation or independent cluster replay failed'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=ROOT/'target/olist/raw')
    parser.add_argument('--published',type=Path,default=ROOT/'docs/advanced-analysis')
    parser.add_argument('--out',type=Path,default=ROOT/'target/delivery-association-validation.json')
    args=parser.parse_args();raw=args.raw.resolve();published=args.published.resolve();out=args.out.resolve()
    protected={*(raw/f for f in FILES.values()),*(published/f for f in ('evidence.json','delivery_months.csv','delivery_common_support.csv')),Path(__file__).resolve(),Path(helper.__file__).resolve()}
    if out==raw or raw in out.parents or out in protected:parser.error('Receipt must be separate from raw/input files')
    out.parent.mkdir(parents=True,exist_ok=True);out.unlink(missing_ok=True)
    result=audit(raw,published);out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'acceptance':result['acceptance'],'raw_rows_exported':False}))
    return 0 if result['acceptance']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
