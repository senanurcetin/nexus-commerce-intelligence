"""Independent raw-CSV replay of the review-selection customer bootstrap.

No production analysis, SQL/order-fact loader, bootstrap or quantile helper is
called. Raw identifiers exist only in memory; receipts contain aggregates/hashes.
Requires the four separately acquired local Olist inputs. No network or UI.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FILES = {name: 'olist_'+name+'_dataset.csv' for name in ('orders','customers','order_items','order_reviews')}
WINDOWS = (7,30,90)
ATOL = 1e-10
PROTOCOL_SHA = '9c6459137fc62d252d12a18e74381fce4136ad82af4873dddc624ebc0082aada'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def need(condition,message):
    if not condition:raise ValueError(message)


def rows(path,required):
    with path.open(encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream)
        need(set(required)<=set(reader.fieldnames or []),'Missing required CSV columns')
        yield from reader


def timestamp(value):
    if not value:return None
    result=datetime.fromisoformat(value)
    need(result.tzinfo is None,'Unexpected timezone in stored source timestamps')
    return result


def finite(value):
    result=float(value)
    need(math.isfinite(result),'Nonfinite numeric source value')
    return result


def reconstruct(raw,plan):
    """Streaming CSV selection; whole-customer ledgers shared across all windows."""
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
    item_keys=set();with_items=set();n=0
    for r in rows(raw/FILES['order_items'],('order_id','order_item_id','price','freight_value')):
        key=(r['order_id'],r['order_item_id'])
        need(key not in item_keys,'Duplicate order-item key');item_keys.add(key)
        need(r['order_id'] in orders,'Orphan item order')
        need(finite(r['price'])>0 and finite(r['freight_value'])>=0,'Invalid item value')
        with_items.add(r['order_id']);n+=1
    counts[FILES['order_items']]=n
    start=timestamp(plan['purchase_start']);cutoff=timestamp(plan['observation_cutoff_exclusive'])
    cohort={}
    for key,(person,status,purchased,delivered,promised) in orders.items():
        if (key in with_items and person and status=='delivered' and purchased and delivered and promised
            and start<=purchased<cutoff and delivered>=purchased and promised>=purchased.replace(hour=0,minute=0,second=0,microsecond=0)
            and delivered+timedelta(days=max(WINDOWS))<cutoff):
            cohort[key]=(person,delivered,delivered.date()>promised.date())
    need(bool(cohort),'No eligible mature orders')
    selected={};dated=Counter();post={};n=0
    for r in rows(raw/FILES['order_reviews'],('order_id','review_id','review_score','review_creation_date','review_answer_timestamp')):
        n+=1;key=r['order_id'];need(key in orders,'Orphan review order')
        score=finite(r['review_score']);need(score.is_integer() and 1<=score<=5,'Invalid review score')
        answered=timestamp(r['review_answer_timestamp']);created=timestamp(r['review_creation_date'])
        if key not in cohort or answered is None or answered>=cutoff:continue
        dated[key]+=1
        _,delivered,_=cohort[key]
        if answered<delivered:continue
        post[key]=min(answered,post.get(key,answered))
        priority=(answered,created or datetime.max,not bool(r['review_id']),r['review_id'],score)
        for window in WINDOWS:
            if answered<=delivered+timedelta(days=window):
                pair=(key,window)
                if pair not in selected or priority<selected[pair][0]:selected[pair]=(priority,int(score))
    counts[FILES['order_reviews']]=n
    ledgers=defaultdict(lambda:np.zeros((len(WINDOWS),6),dtype=np.int64));availability=Counter()
    for key,(person,_,late) in cohort.items():
        offset=0 if late else 3
        for j,window in enumerate(WINDOWS):
            ledger=ledgers[person];ledger[j,offset+2]+=1
            answer=selected.get((key,window))
            if answer:
                ledger[j,offset+1]+=1;ledger[j,offset]+=answer[1]<=plan['poor_score_max']
                reason='observed_within_window'
            elif not dated[key]:reason='no_dated_answer_before_cutoff'
            elif key not in post:reason='pre_delivery_answers_only'
            else:reason='post_delivery_answer_after_window'
            availability[(window,late,reason)]+=1
    return np.stack(list(ledgers.values())),availability,counts,len(cohort)


def estimates(totals):
    result=[]
    for lp,lr,ln,op,orr,on in totals:
        if min(lr,ln,orr,on)<=0:return None
        result.append((lp/lr-op/orr,lp/ln-(op+on-orr)/on,(lp+ln-lr)/ln-op/on))
    return np.array(result)


def percentile(values,q):
    """Linear order-statistic interpolation, without np.quantile/percentile."""
    need(len(values)>0 and math.isfinite(q) and 0<=q<=1,'Invalid percentile request')
    ordered=sorted(values);position=(len(ordered)-1)*q;lo=math.floor(position);hi=math.ceil(position)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)


def replay(ledgers,iterations,seed):
    need(ledgers.ndim==3 and ledgers.shape[1:]==(3,6) and len(ledgers)>0,'Invalid cluster-ledger shape')
    need(np.isfinite(ledgers).all() and (ledgers>=0).all() and (ledgers%1==0).all(),'Invalid integer cluster counts')
    need((ledgers[:,:,0]<=ledgers[:,:,1]).all() and (ledgers[:,:,1]<=ledgers[:,:,2]).all()
         and (ledgers[:,:,3]<=ledgers[:,:,4]).all() and (ledgers[:,:,4]<=ledgers[:,:,5]).all(),'Invalid nested cluster counts')
    need(isinstance(iterations,int) and iterations>=100,'At least 100 replicates required')
    frequencies=Counter(tuple(int(x) for x in ledger.flat) for ledger in ledgers)
    patterns=sorted(frequencies);probabilities=[frequencies[p]/len(ledgers) for p in patterns]
    rng=np.random.default_rng(seed);samples=[]
    # Separate scalar draws and explicit ledger accumulation, not the production
    # batched np.unique/matrix multiplication/quantile implementation.
    for _ in range(iterations):
        multiplicities=rng.multinomial(len(ledgers),probabilities)
        total=[sum(int(weight)*pattern[j] for weight,pattern in zip(multiplicities,patterns)) for j in range(18)]
        value=estimates(np.array(total).reshape(3,6))
        if value is not None:samples.append(value)
    need(len(samples)>=.95*iterations,'Insufficient two-group respondent bootstrap support')
    limits=np.empty((2,3,3))
    for side,q in enumerate((.025,.975)):
        for w in range(3):
            for k in range(3):limits[side,w,k]=percentile([s[w,k] for s in samples],q)
    return limits,{'customers':len(ledgers),'iterations':iterations,'valid_replicates':len(samples),
                   'seed':seed,'unique_cluster_patterns':len(patterns)}


def close(actual,expected,message):
    need(math.isfinite(float(actual)) and math.isfinite(float(expected)) and abs(float(actual)-float(expected))<=ATOL,message)


def validate(raw,published,protocol):
    evidence=json.loads((published/'review_selection_evidence.json').read_text(encoding='utf-8'))
    plan=json.loads(protocol.read_text(encoding='utf-8'))
    need(evidence['source_kind']=='historical_public_olist_review_selection' and evidence['synthetic'] is False,'Unsupported study provenance')
    need(plan==evidence['protocol'],'Protocol and published evidence differ')
    need(plan['version']==1 and plan['windows_days']==list(WINDOWS) and plan['primary_window_days']==30
         and plan['poor_score_max']==2 and plan['purchase_start']=='2017-01-01'
         and plan['observation_cutoff_exclusive']=='2018-08-01'
         and plan['bootstrap_iterations']==1000 and plan['bootstrap_seed']==20261029,'Unsupported retrospective protocol')
    need(digest(protocol)==evidence['protocol_sha256']==PROTOCOL_SHA,'Protocol hash mismatch')
    for filename in FILES.values():
        p=raw/filename;meta=evidence['quality']['files'][filename]
        need(p.stat().st_size==meta['bytes'] and digest(p)==meta['sha256'],'Raw source hash/size mismatch')
    for filename in ('review_groups.csv','review_summary.csv','review_availability.csv'):
        need(digest(published/filename)==evidence['aggregate_sha256'][filename],'Published aggregate hash mismatch')
    ledgers,availability,counts,n=reconstruct(raw,plan)
    for filename,count in counts.items():need(count==evidence['quality']['files'][filename]['rows'],'Raw row count mismatch')
    totals=ledgers.sum(axis=0)
    groups=list(rows(published/'review_groups.csv',('window_days','late','poor_ratings','observed_ratings','eligible_orders')))
    need(len(groups)==6,'Expected six group/window cells')
    seen=set()
    for r in groups:
        cell=(int(r['window_days']),r['late']);need(cell not in seen and cell[0] in WINDOWS and cell[1] in ('True','False'),'Invalid/repeated group cell');seen.add(cell)
        offset=0 if cell[1]=='True' else 3
        need(list(totals[WINDOWS.index(cell[0]),offset:offset+3])==[int(r[k]) for k in ('poor_ratings','observed_ratings','eligible_orders')],'Independent group counts differ')
    actual={}
    for r in rows(published/'review_availability.csv',('window_days','late','availability_reason','orders')):
        key=(int(r['window_days']),r['late']=='True',r['availability_reason'])
        need(r['late'] in ('True','False') and key not in actual,'Invalid/repeated availability cell');actual[key]=int(r['orders'])
    need(actual==dict(availability),'Independent availability ledger differs')
    limits,bootstrap=replay(ledgers,plan['bootstrap_iterations'],plan['bootstrap_seed'])
    need(all(evidence['bootstrap'][k]==v for k,v in bootstrap.items()),'Published bootstrap metadata differs')
    summary=list(rows(published/'review_summary.csv',('window_days','eligible_orders')))
    need(len(summary)==3 and {int(r['window_days']) for r in summary}==set(WINDOWS),'Expected three distinct window summaries')
    published_summary=evidence['summary'];need(len(published_summary)==3 and {s['window_days'] for s in published_summary}==set(WINDOWS),'Invalid evidence windows')
    observed=estimates(totals);need(observed is not None,'Insufficient observed group support')
    comparisons=[]
    for j,window in enumerate(WINDOWS):
        r=next(r for r in summary if int(r['window_days'])==window)
        e=next(s for s in published_summary if s['window_days']==window)
        need(int(r['eligible_orders'])==e['eligible_orders']==n,'Mature cohort denominator differs')
        expected={}
        for k,field in enumerate(('complete_case_difference','bound_low','bound_high')):expected[field]=float(observed[j,k])
        expected.update(late_response_rate=float(totals[j,1]/totals[j,2]),on_time_response_rate=float(totals[j,4]/totals[j,5]))
        for k,name in enumerate(('complete_case','lower_bound_endpoint','upper_bound_endpoint')):
            for side,label in enumerate(('low','high')):expected[name+'_ci_'+label]=float(limits[side,j,k])
        for field,value in expected.items():
            close(r[field],value,'Published CSV value differs: '+field)
            close(e[field],value,'Published evidence value differs: '+field)
        comparisons.append({'window_days':window,**expected})
    return {'eligible_orders':n,**bootstrap,'group_window_cells_reconciled':6,
            'availability_cells_reconciled':len(availability),'sampling_limits_replayed':18,
            'comparisons':comparisons,'customer_cluster_sampling_intervals_replayed':True}


def audit(raw,published,protocol=ROOT/'contracts/olist_review_protocol.json'):
    result={'schema_version':1,'acceptance':'FAIL','raw_rows_exported':False,
        'source':'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce','derived_license':'CC-BY-NC-SA-4.0',
        'runtime':{'python':platform.python_version(),'numpy':np.__version__},
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        'scope':'Raw review-selection cohort, first-answer policy, availability and pointwise customer-cluster percentile intervals only. Not the earlier delivery-association bootstrap, simultaneous-set coverage, source authenticity, causal identification, business validity or native BI.',
        'causal_acceptance':'HOLD','native_bi_acceptance':'HOLD'}
    try:
        inputs={**{'raw/'+f:raw/f for f in FILES.values()},**{'published/'+f:published/f for f in (
            'review_selection_evidence.json','review_groups.csv','review_summary.csv','review_availability.csv')},'protocol':protocol}
        def snapshot():
            return {k:(digest(p) if k.startswith('raw/') else hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()) for k,p in inputs.items()}
        before=snapshot();result['input_sha256']=before
        result['hash_basis']='raw inputs byte-exact; published text and protocol LF-normalized'
        result['details']=validate(raw,published,protocol)
        need(before==snapshot(),'Inputs changed during validation')
        need(result['implementation_sha256']==hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),'Validator changed during execution')
        result.update(acceptance='PASS',inputs_stable_during_validation=True)
    except (ValueError,KeyError,OSError,TypeError,OverflowError,csv.Error):
        # Never include raw key/value content, absolute paths or stale success details.
        result.pop('details',None);result['error']='Input integrity, protocol, cohort or independent sampling replay failed'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=ROOT/'target/olist/raw')
    parser.add_argument('--published',type=Path,default=ROOT/'docs/advanced-analysis')
    parser.add_argument('--out',type=Path,default=ROOT/'target/review-cluster-validation.json')
    args=parser.parse_args();raw=args.raw.resolve();out=args.out.resolve()
    protected={*(raw/f for f in FILES.values()),*(args.published.resolve()/f for f in (
        'review_selection_evidence.json','review_groups.csv','review_summary.csv','review_availability.csv')),ROOT/'contracts/olist_review_protocol.json',Path(__file__).resolve()}
    if out==raw or raw in out.parents or out in protected:parser.error('Receipt must be separate from raw/input files')
    result=audit(raw,args.published.resolve());out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'acceptance':result['acceptance'],'raw_rows_exported':False}))
    return 0 if result['acceptance']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
