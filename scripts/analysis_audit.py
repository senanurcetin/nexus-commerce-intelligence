"""Replay published calculations independently, then check evidence and delivery.

Uses aggregate/public evidence only. No production estimator helpers, raw source
access, cloud calls, browser, DAX engine or new inferential claims.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ATOL=1e-7


def need(condition,message):
    if not condition:raise ValueError(message)


def near(actual,expected,message):
    if expected is None:
        need(actual is None or bool(np.asarray(pd.isna(actual)).all()),message);return
    a=np.asarray(actual,dtype=float);b=np.asarray(expected,dtype=float)
    need(a.shape==b.shape and np.array_equal(np.isnan(a),np.isnan(b))
         and not np.isinf(a).any() and not np.isinf(b).any()
         and np.allclose(a,b,atol=ATOL,rtol=1e-10,equal_nan=True),message)


def read(folder,name):return json.loads((folder/name).read_text(encoding='utf-8'))


def forecast(folder):
    receipt=read(folder,'forecast_evidence.json');plan=receipt['protocol']
    methods=plan['models'];selector=plan['primary_method'];all_methods=[*methods,selector]
    need(methods==['seasonal_naive','weekday_mean_28','ridge_calendar_180'] and selector=='past_mae_selector'
         and plan['ridge_days']==180 and plan['horizon_days']==7 and plan['origin_step_days']==7,'Unsupported forecast replay protocol')
    volume=pd.read_csv(folder/'forecast_volume.csv',parse_dates=['day']).set_index('day').placed_orders
    expected_dates=pd.date_range(plan['series_start'],pd.Timestamp(plan['series_end_exclusive'])-pd.Timedelta(days=1))
    need(volume.index.equals(expected_dates) and np.isfinite(volume).all() and (volume>=0).all()
         and (volume%1==0).all(),'Invalid or incomplete daily target')
    near(receipt['placed_orders'],int(volume.sum()),'Receipt placed-order population differs from daily counts')
    near(receipt['series_days'],len(volume),'Receipt daily population differs from target window')
    daily=pd.read_csv(folder/'forecast_daily.csv',parse_dates=['origin','day','training_end','calibration_end'])
    origins=[d for d in pd.date_range(plan['calibration_origin_start'],volume.index[-1],freq='7D') if d+pd.Timedelta(days=6)<=volume.index[-1]]
    need(set(daily.method)==set(all_methods) and len(daily)==len(origins)*28
         and set(daily.origin)==set(origins),'Forecast population/methods/origins differ from protocol')
    need(not daily.duplicated(['origin','day','method']).any(),'Duplicate forecast observations')
    histories={m:[] for m in all_methods};evaluation={m:[] for m in all_methods};weekly=[]
    for origin in origins:
        days=pd.date_range(origin,periods=7);past=volume[volume.index<origin];y=volume.loc[days].to_numpy(dtype=float)
        need(len(past)>=180,'Insufficient genuine past training history')
        # Independent reference arithmetic; ridge uses augmented least squares,
        # while production uses normal equations. No production helper is imported.
        future_weekdays=days.dayofweek
        fit_days=past.index[-180:];center=past.index[-1]
        def matrix(index):
            return np.column_stack([np.ones(len(index)),(index-center).days/180,np.eye(7)[index.dayofweek,1:]])
        penalty=np.diag([0.]+[math.sqrt(plan['ridge_penalty'])]*7)
        coefficients=np.linalg.lstsq(np.vstack([matrix(fit_days),penalty]),np.r_[past.values[-180:],np.zeros(8)],rcond=None)[0]
        reference={'seasonal_naive':volume.loc[days-pd.Timedelta(days=7)].to_numpy(dtype=float),
            'weekday_mean_28':past.iloc[-28:].groupby(past.index[-28:].dayofweek).mean().reindex(future_weekdays).to_numpy(),
            'ridge_calendar_180':np.maximum(0,matrix(days)@coefficients)}
        chosen=(min(methods,key=lambda m:(np.mean([r['mae'] for r in histories[m][-plan['selector_history_weeks']:]]),methods.index(m)))
                if histories[methods[0]] else plan['selector_fallback'])
        reference[selector]=reference[chosen]
        scale=float(np.abs(past.values[7:]-past.values[:-7]).mean())
        phase='evaluation' if origin>=pd.Timestamp(plan['evaluation_start']) else 'calibration'
        current={}
        for method in all_methods:
            rows=daily[(daily.origin==origin)&(daily.method==method)].sort_values('day')
            need(rows.day.tolist()==list(days) and rows.horizon.tolist()==list(range(1,8)),'Missing or reordered forecast horizon')
            need((rows.phase==phase).all() and (rows.training_end==origin-pd.Timedelta(days=1)).all(),'Invalid phase or future training endpoint')
            need((rows.chosen_model==(chosen if method==selector else method)).all(),'Selector differs from completed past-fold MAE')
            near(rows.actual_orders.to_numpy(),y,'Forecast target differs from daily volume')
            p=reference[method];near(rows.prediction.to_numpy(),p,'Published forecast differs from independent fit')
            near(rows.mase_scale.to_numpy(),np.repeat(scale,7) if scale else None,'Invalid past-only MASE scale')
            previous=histories[method][-plan['calibration_weeks']:]
            need((rows.calibration_blocks==len(previous)).all(),'Calibration population differs from past blocks')
            if previous:need((rows.calibration_end==previous[-1]['end']).all(),'Calibration endpoint is not the last completed past block')
            else:need(rows.calibration_end.isna().all(),'Invented initial calibration endpoint')
            rank=math.ceil((len(previous)+1)*(1-plan['alpha']))
            radius=sorted(r['max_error'] for r in previous)[rank-1] if 0<rank<=len(previous) else None
            errors=np.abs(y-p)
            record={'mae':float(errors.mean()),'max_error':float(errors.max()),'end':days[-1]}
            if radius is None:need(rows[['lower','upper']].isna().all().all(),'Invented early interval')
            else:
                lo=np.maximum(0,p-radius);hi=p+radius
                near(rows.lower.to_numpy(),lo,'Lower interval used the wrong calibration scores')
                near(rows.upper.to_numpy(),hi,'Upper interval used the wrong calibration scores')
                covered=(y>=lo-ATOL)&(y<=hi+ATOL)
                if phase=='evaluation':evaluation[method].append({'errors':errors,'y':y,'scaled':record['mae']/scale if scale else None,
                    'coverage':covered,'width':hi-lo,'score':hi-lo+2/plan['alpha']*(np.maximum(lo-y,0)+np.maximum(y-hi,0))})
            if phase=='evaluation':need(radius is not None,'Uncalibrated evaluation interval')
            current[method]=record
        if phase=='evaluation':weekly.append(current[methods[0]]['mae']-current[selector]['mae'])
        for method in all_methods:histories[method].append(current[method])
    summaries=pd.read_csv(folder/'forecast_metrics.csv').set_index('method')
    need(summaries.index.is_unique and set(summaries.index)==set(all_methods),'Duplicate or missing method metrics')
    for method,folds in evaluation.items():
        errors=np.concatenate([r['errors'] for r in folds]);ys=np.concatenate([r['y'] for r in folds]);coverage=np.concatenate([r['coverage'] for r in folds])
        expected={'evaluated_days':len(errors),'evaluated_weeks':len(folds),'mae':float(errors.mean()),'rmse':float(np.sqrt(np.mean(errors**2))),
            'wape':float(errors.sum()/ys.sum()) if ys.sum() else None,'mase':float(np.mean([r['scaled'] for r in folds])) if all(r['scaled'] is not None for r in folds) else None,
            'day_coverage':float(coverage.mean()),'week_coverage':float(np.mean([r['coverage'].all() for r in folds])),
            'mean_width':float(np.concatenate([r['width'] for r in folds]).mean()),'interval_score':float(np.concatenate([r['score'] for r in folds]).mean())}
        published=next(r for r in receipt['metrics'] if r['method']==method)
        for field,value in expected.items():
            near(summaries.loc[method,field],value,'Forecast metric CSV does not replay: '+field)
            near(published[field],value,'Forecast metric receipt does not replay: '+field)
    uncertainty=pd.read_csv(folder/'forecast_uncertainty.csv').set_index('block_weeks')
    need(uncertainty.index.is_unique and set(uncertainty.index)==set(plan['paired_bootstrap_blocks_weeks']),'Missing/duplicate paired uncertainty blocks')
    need(len(receipt['paired_uncertainty'])==len(uncertainty),'Duplicate paired uncertainty receipt entries')
    primary=None
    for block in plan['paired_bootstrap_blocks_weeks']:
        n=len(weekly);need(n>=block,'Insufficient paired evaluation weeks')
        rng=np.random.default_rng(plan['bootstrap_seed'])
        starts=rng.integers(0,n,size=(plan['bootstrap_iterations'],math.ceil(n/block)))
        indices=((starts[:,:,None]+np.arange(block))%n).reshape(plan['bootstrap_iterations'],-1)[:,:n]
        samples=np.asarray(weekly)[indices].mean(axis=1);lower,upper=np.quantile(samples,[.025,.975])
        published=next(r for r in receipt['paired_uncertainty'] if r['block_weeks']==block)
        for field,value in {'mae_improvement':float(np.mean(weekly)),'ci_low':lower,'ci_high':upper,'iterations':plan['bootstrap_iterations'],'seed':plan['bootstrap_seed']}.items():
            near(uncertainty.loc[block,field],value,'Paired uncertainty CSV does not replay: '+field)
            near(published[field],value,'Paired uncertainty receipt does not replay: '+field)
        if block==plan['primary_bootstrap_block_weeks']:primary={'improvement':float(np.mean(weekly)),'ci_low':float(lower),'ci_high':float(upper)}
    need(primary is not None,'Missing declared primary paired interval')
    near(receipt['evaluation_weeks'],len(weekly),'Receipt evaluation weeks differ from replay')
    near(receipt['evaluation_days'],len(weekly)*7,'Receipt evaluation days differ from replay')
    return {'origins_replayed':len(origins),'evaluation_weeks':len(weekly),'methods_replayed':len(all_methods),
        'prediction_fits_selection_calibration_metrics_and_paired_bootstrap_replayed':True,'primary_interval':primary,
        'primary_superiority_demonstrated':primary['ci_low']>0,'original_ingestion_times_verified':False}


def reviews(folder):
    receipt=read(folder,'review_selection_evidence.json');groups=pd.read_csv(folder/'review_groups.csv')
    summary=pd.read_csv(folder/'review_summary.csv').set_index('window_days');primary=None
    need(summary.index.is_unique and len(receipt['summary'])==len(summary),'Duplicate review windows')
    for window in receipt['protocol']['windows_days']:
        rows=groups[groups.window_days==window].set_index('late')
        need(rows.index.is_unique and set(rows.index)=={True,False},'Review delivery-group population differs')
        ordered=rows.reindex([True,False])
        observed=ordered.observed_ratings.to_numpy(dtype=float)
        poor=ordered.poor_ratings.to_numpy(dtype=float);total=ordered.eligible_orders.to_numpy(dtype=float)
        need(np.isfinite([poor,observed,total]).all() and (total>0).all() and (poor>=0).all()
             and (poor<=observed).all() and (observed<=total).all() and (np.r_[poor,observed,total]%1==0).all(),'Invalid review outcome counts')
        expected={'complete_case_difference':float(poor[0]/observed[0]-poor[1]/observed[1]) if (observed>0).all() else None,
            'bound_low':float(poor[0]/total[0]-(poor[1]+total[1]-observed[1])/total[1]),
            'bound_high':float((poor[0]+total[0]-observed[0])/total[0]-poor[1]/total[1]),
            'late_response_rate':observed[0]/total[0],'on_time_response_rate':observed[1]/total[1],'eligible_orders':total.sum()}
        published=[r for r in receipt['summary'] if r['window_days']==window];need(len(published)==1,'Duplicate primary review receipt')
        for field,value in expected.items():
            near(summary.loc[window,field],value,'Review summary CSV differs from outcome counts: '+field)
            near(published[0][field],value,'Review receipt differs from outcome counts: '+field)
        if window==receipt['protocol']['primary_window_days']:
            primary=expected;grid=pd.read_csv(folder/'review_sensitivity.csv')
            q=grid[['q_late_missing','q_on_time_missing']].to_numpy(dtype=float)
            need(np.isfinite(q).all() and ((q>=0)&(q<=1)).all(),'Invalid missing-rating assumption grid')
            points=np.arange(0,1+receipt['protocol']['sensitivity_grid_step']/2,receipt['protocol']['sensitivity_grid_step'])
            expected_grid={(round(float(a),12),round(float(b),12)) for a in points for b in points}
            need(len(q)==len(expected_grid) and {tuple(np.round(row,12)) for row in q}==expected_grid,'Incomplete or duplicate missing-rating scenario grid')
            rates=(poor+(total-observed)*q)/total
            near(grid.risk_difference.to_numpy(),rates[:,0]-rates[:,1],'Sensitivity grid does not follow declared missing-outcome identity')
    need(primary is not None,'Missing primary review window')
    return {'windows_replayed':len(summary),'sharp_bounds_and_sensitivity_grid_replayed':True,
        'primary_bounds_include_zero':primary['bound_low']<=0<=primary['bound_high'],
        'customer_cluster_sampling_intervals_replayed':False,'causal_effect_identified':False}


def evidence(root):
    folder=root/'docs/advanced-analysis';base=read(folder,'evidence.json');exports=0
    for name in ('evidence.json','extension_evidence.json','operations_evidence.json','review_selection_evidence.json','forecast_evidence.json'):
        receipt=read(folder,name);need(receipt['quality']['files']==base['quality']['files'],'Research snapshots differ')
        for name,sha in receipt.get('export_sha256',receipt.get('aggregate_sha256',{})).items():
            need(hashlib.sha256((folder/name).read_bytes()).hexdigest()==sha,'Research aggregate file hash mismatch');exports+=1
    reproduction=read(root/'docs','research_reproduction.json')
    for prefix in ('review','forecast'):
        name='review_selection_evidence.json' if prefix=='review' else 'forecast_evidence.json'
        receipt=read(folder,name);contract=root/'contracts'/('olist_'+prefix+'_protocol.json')
        need(receipt['protocol']==json.loads(contract.read_text()) and receipt['protocol_sha256']==hashlib.sha256(contract.read_bytes()).hexdigest(),'Published protocol differs from its contract')
    for name,sha in reproduction['pipeline_inputs_sha256'].items():
        need(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,'Historical reproduction pipeline fingerprint is stale')
    for comparison in reproduction['aggregate_comparisons']:
        need(hashlib.sha256((folder/comparison['file']).read_bytes()).hexdigest()==comparison['reproduced_sha256'],'Reproduction aggregate comparison is stale')
    from scripts.executive_readout import render
    text,ledger=render(root)
    need(text==(root/'docs/EXECUTIVE_READOUT.md').read_text(encoding='utf-8') and ledger==read(root/'docs','executive_readout.json'),'Executive readout is stale')
    return {'source_consistent_studies':5,'aggregate_hashes_checked':exports,'executive_readout_current':True,'reproduction_fingerprints_current':True}


def fingerprints(root):
    paths=[p for p in (root/'docs/advanced-analysis').iterdir() if p.suffix in {'.csv','.json'}]
    paths+=[root/name for name in ('docs/research_reproduction.json','docs/executive_readout.json','docs/EXECUTIVE_READOUT.md',
        'docs/core-source/status.json','contracts/financial_semantics.json','powerbi/olist-package-manifest.json','powerbi/package-manifest.json',
        'scripts/executive_readout.py','scripts/release_audit.py','scripts/build_research_portal.py')]
    result={}
    for path in sorted(paths):
        raw=path.read_bytes()
        if path.suffix=='.json':raw=json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
        else:raw=raw.replace(b'\r\n',b'\n')
        result[path.relative_to(root).as_posix()]=hashlib.sha256(raw).hexdigest()
    return result


def audit(root=ROOT):
    checks=[]
    implementation=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    def check(name,action):
        try:details=action();checks.append({'name':name,'passed':True,'details':details})
        except Exception as error:checks.append({'name':name,'passed':False,'error':type(error).__name__+': '+str(error)})
    folder=root/'docs/advanced-analysis'
    check('input_snapshot',lambda:fingerprints(root))
    before=checks[-1].get('details',{})
    check('published_evidence_integrity',lambda:evidence(root))
    check('independent_forecast_replay',lambda:forecast(folder))
    check('independent_missing_rating_replay',lambda:reviews(folder))
    from scripts.release_audit import audit as artifacts
    def delivery():
        result=artifacts(root);need(result['artifact_delivery_ready'],'Portable archive acceptance failed: '+'; '.join(result['errors']))
        return {'archives_verified':len(result['checks']),'native_bi_acceptance':'HOLD'}
    check('portable_deliverables',delivery)
    def stable():
        need(bool(before) and before==fingerprints(root),'Audit input files changed during validation')
        need(implementation==hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),'Audit implementation changed during validation')
        return {'fingerprinted_files':len(before),'hash_basis':'canonical JSON; LF-normalized other text'}
    check('input_stability',stable)
    return {'schema_version':1,'published_calculation_acceptance':'PASS' if all(c['passed'] for c in checks) else 'FAIL',
        'implementation_sha256':implementation,
        'runtime_versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__},
        'derived_public_olist_license':'CC-BY-NC-SA-4.0','noncommercial':True,
        'absolute_numeric_tolerance':ATOL,'relative_numeric_tolerance':1e-10,'checks':checks,
        'financial_semantics_acceptance':'HOLD','native_bi_acceptance':'HOLD','operational_forecast_acceptance':'HOLD',
        'scope':'Independent aggregate-based forecast and missing-rating calculation replay plus evidence/delivery integrity. No raw-data authenticity, original ingestion history, review cluster-bootstrap replay, current business validity, causal effect or native engine verification.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--out',type=Path,default=ROOT/'target/analysis-validation.json');args=p.parse_args()
    result=audit(args.root);args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['published_calculation_acceptance']=='PASS' else 1)
