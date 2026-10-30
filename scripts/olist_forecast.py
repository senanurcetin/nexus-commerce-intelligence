"""As-of weekly forecasting benchmark with past-only selection and calibration.

No future order status, random row split, cloud query or LLM model is used.
Rolling conformal-style bands are empirical, not guaranteed under temporal drift.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from scripts.advanced_olist import ROOT,SQL,SOURCE,load_fact,sha256

PROTOCOL=ROOT/'contracts/olist_forecast_protocol.json'
MODELS=('seasonal_naive','weekday_mean_28','ridge_calendar_180')
SELECTOR='past_mae_selector'
REFERENCES=['https://otexts.com/fpp3/tscv.html','https://otexts.com/fpp3/accuracy.html',
            'https://papers.neurips.cc/paper/2021/file/312f1ba2a72318edaaa995a67835fad5-Paper.pdf']


def design(dates,center):
    dates=pd.DatetimeIndex(dates)
    return np.column_stack([np.ones(len(dates)),(dates-pd.Timestamp(center)).days.to_numpy()/180,
                            *[(dates.dayofweek==i).astype(float) for i in range(1,7)]])


def predictions(history:pd.Series,future:pd.DatetimeIndex,penalty=10.):
    y=history.to_numpy(dtype=float);future=pd.DatetimeIndex(future)
    if len(y)<180 or not np.isfinite(y).all() or (y<0).any() or penalty<=0:
        raise ValueError('At least 180 nonnegative finite historical daily counts and positive penalty required')
    if not np.array_equal(history.index.values,pd.date_range(history.index[0],periods=len(history)).values) or not np.array_equal(future.values,pd.date_range(history.index[-1]+pd.Timedelta(days=1),periods=7).values):
        raise ValueError('Contiguous daily history and exactly the next seven dates required')
    center=history.index[-1];x=design(history.index[-180:],center);xf=design(future,center)
    ridge=np.diag([0.]+[penalty]*7)
    coef=np.linalg.solve(x.T@x+ridge,x.T@y[-180:])
    return {'seasonal_naive':y[-7:].copy(),
            'weekday_mean_28':y[-28:].reshape(4,7).mean(axis=0),
            'ridge_calendar_180':np.maximum(0,xf@coef)}


def calibration_radius(scores,alpha=.1):
    values=np.asarray(scores,dtype=float)
    if not 0<alpha<1 or not np.isfinite(values).all() or (values<0).any():raise ValueError('Invalid calibration scores/alpha')
    rank=math.ceil((len(values)+1)*(1-alpha))
    # The exact upper rank is unattainable with a tiny calibration set. No
    # interpolated quantile or invented finite interval is substituted.
    return float(np.sort(values)[rank-1]) if 0<rank<=len(values) else None


def interval_score(y,lower,upper,alpha=.1):
    y,lo,hi=np.broadcast_arrays(np.asarray(y,dtype=float),np.asarray(lower,dtype=float),np.asarray(upper,dtype=float))
    if not 0<alpha<1 or not np.isfinite([y,lo,hi]).all() or (lo>hi).any():raise ValueError('Invalid interval inputs')
    return hi-lo+2/alpha*np.maximum(lo-y,0)+2/alpha*np.maximum(y-hi,0)


def block_interval(improvements,block=4,iterations=2000,seed=20261029):
    d=np.asarray(improvements,dtype=float)
    if d.ndim!=1 or len(d)<block or block<1 or iterations<100 or not np.isfinite(d).all():raise ValueError('Invalid paired weekly improvements/block')
    rng=np.random.default_rng(seed);samples=[]
    for _ in range(iterations):
        starts=rng.integers(0,len(d),math.ceil(len(d)/block))
        idx=((starts[:,None]+np.arange(block))%len(d)).ravel()[:len(d)]
        samples.append(float(d[idx].mean()))
    lo,hi=np.quantile(samples,[.025,.975])
    return {'block_weeks':block,'mae_improvement':float(d.mean()),'ci_low':float(lo),'ci_high':float(hi),
            'iterations':iterations,'seed':seed}


def backtest(series,plan):
    methods=(*MODELS,SELECTOR);history={m:[] for m in methods};rows=[];folds=[]
    start=pd.Timestamp(plan['calibration_origin_start']);end=series.index[-1]
    evaluation=pd.Timestamp(plan['evaluation_start'])
    for fold,origin in enumerate(pd.date_range(start,end,freq='7D')):
        future=pd.date_range(origin,periods=7)
        if future[-1]>end:break
        past=series[series.index<origin]
        predicted=predictions(past,future,plan['ridge_penalty'])
        # Selection and interval calibration happen BEFORE reading this week's y.
        chosen=min(MODELS,key=lambda m:(np.mean([r['mae'] for r in history[m][-plan['selector_history_weeks']:]]) if history[m] else float('inf'),MODELS.index(m)))
        predicted[SELECTOR]=predicted[chosen].copy()
        scale=float(np.abs(past.to_numpy()[7:]-past.to_numpy()[:-7]).mean())
        current=[]
        for method in methods:
            previous=history[method][-plan['calibration_weeks']:]
            radius=calibration_radius([r['max_error'] for r in previous],plan['alpha'])
            last_end=previous[-1]['end'] if previous else None
            if last_end is not None and last_end>=origin:raise ValueError('Future calibration outcome leaked into an origin')
            y=series.loc[future].to_numpy(dtype=float);p=predicted[method]
            lo=np.maximum(0,p-radius) if radius is not None else np.full(7,np.nan)
            hi=p+radius if radius is not None else np.full(7,np.nan)
            error=np.abs(y-p);covered=(y>=lo)&(y<=hi)
            iscore=interval_score(y,lo,hi,plan['alpha']).mean() if radius is not None else None
            phase='evaluation' if origin>=evaluation else 'calibration'
            for j,day in enumerate(future):
                rows.append({'origin':origin,'day':day,'phase':phase,'method':method,'chosen_model':chosen if method==SELECTOR else method,
                    'horizon':j+1,'actual_orders':int(y[j]),'prediction':float(p[j]),'lower':float(lo[j]) if radius is not None else None,
                    'upper':float(hi[j]) if radius is not None else None,'training_end':past.index[-1],
                    'calibration_blocks':len(previous),'calibration_end':last_end,'mase_scale':scale if scale else None})
            record={'origin':origin,'end':future[-1],'phase':phase,'method':method,'chosen_model':chosen if method==SELECTOR else method,
                'mae':float(error.mean()),'mse':float(np.mean((y-p)**2)),'max_error':float(error.max()),
                'mase':float(error.mean()/scale) if scale else None,'actual_orders':int(y.sum()),
                'day_coverage':float(covered.mean()) if radius is not None else None,
                'week_coverage':bool(covered.all()) if radius is not None else None,
                'mean_width':float((hi-lo).mean()) if radius is not None else None,'interval_score':float(iscore) if iscore is not None else None}
            current.append(record);folds.append(record)
        for record in current:history[record['method']].append(record)
    forecasts=pd.DataFrame(rows);folds=pd.DataFrame(folds)
    if forecasts.empty:raise ValueError('No complete forecast blocks')
    evaluation_rows=forecasts[forecasts.phase=='evaluation'];summaries=[]
    for method in methods:
        d=evaluation_rows[evaluation_rows.method==method];f=folds[(folds.phase=='evaluation')&(folds.method==method)]
        if d.empty or d[['lower','upper']].isna().any().any():raise ValueError('Evaluation requires mature past-only calibration')
        errors=d.actual_orders-d.prediction;absolute=errors.abs()
        summaries.append({'method':method,'evaluated_days':len(d),'evaluated_weeks':len(f),'mae':float(absolute.mean()),
            'rmse':float(np.sqrt((errors**2).mean())),'wape':float(absolute.sum()/d.actual_orders.sum()) if d.actual_orders.sum() else None,
            'mase':float(f.mase.mean()) if f.mase.notna().all() else None,'day_coverage':float(f.day_coverage.mean()),
            'week_coverage':float(f.week_coverage.mean()),'mean_width':float(f.mean_width.mean()),'interval_score':float(f.interval_score.mean())})
    f=folds[folds.phase=='evaluation'].pivot(index='origin',columns='method',values='mae')
    improvements=(f.seasonal_naive-f[SELECTOR]).to_numpy()
    uncertainty=pd.DataFrame([block_interval(improvements,b,plan['bootstrap_iterations'],plan['bootstrap_seed']) for b in plan['paired_bootstrap_blocks_weeks']])
    return {'forecast_daily':forecasts,'forecast_folds':folds,'forecast_metrics':pd.DataFrame(summaries),'forecast_uncertainty':uncertainty}


def load_series(con,raw,plan):
    daily=con.execute((SQL/'daily_order_volume.sql').read_text(),{'start':plan['series_start'],'end':plan['series_end_exclusive']}).df()
    counts=Counter()
    with (raw/'olist_orders_dataset.csv').open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            stamp=row['order_purchase_timestamp']
            if not stamp:raise ValueError('Missing purchase timestamps prevent complete-volume reconstruction')
            day=date.fromisoformat(stamp[:10])
            if date.fromisoformat(plan['series_start'])<=day<date.fromisoformat(plan['series_end_exclusive']):counts[day]+=1
    expected=[counts[d.date()] for d in daily.day]
    if not np.array_equal(daily.placed_orders,expected):raise ValueError('Daily volume differs from independent raw CSV count')
    series=pd.Series(daily.placed_orders.to_numpy(),index=pd.DatetimeIndex(daily.day))
    return series,daily


def present(tables,plan,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.facecolor':'#0B0F19','axes.facecolor':'#0B0F19','text.color':'#EDF2F8',
        'axes.labelcolor':'#B9C5CE','xtick.color':'#B9C5CE','ytick.color':'#B9C5CE','axes.edgecolor':'#334155','font.size':10})
    def save(fig,name,note,left=.1):
        fig.text(.07,.95,'NEXUS / TEMPORAL FORECAST VALIDATION',color='#00E0FF',fontsize=11)
        logo=fig.add_axes([.79,.90,.16,.07]);logo.imshow(plt.imread(ROOT/'branding/nexus_official_transparent.png'));logo.axis('off')
        fig.text(.07,.025,note,fontsize=9,color='#B9C5CE');fig.subplots_adjust(top=.82,bottom=.2,left=left,right=.95)
        fig.savefig(out/name,dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
    forecasts=tables['forecast_daily'];d=forecasts[(forecasts.phase=='evaluation')&(forecasts.method==SELECTOR)].tail(56)
    fig,ax=plt.subplots(figsize=(12,6));ax.fill_between(d.day,d.lower,d.upper,color='#6E55C6',alpha=.4,label='Past-block calibrated band')
    ax.plot(d.day,d.actual_orders,color='#EDF2F8',label='Observed placed orders',lw=1.5)
    ax.plot(d.day,d.prediction,color='#00E0FF',label='Past-only method selector',lw=1.5)
    ax.set(ylabel='Placed orders / calendar day',title='As-of seven-day forecasts | Last eight evaluated weeks')
    ax.legend(facecolor='#0B0F19',labelcolor='#EDF2F8',fontsize=9);fig.autofmt_xdate()
    save(fig,'forecast_temporal.png','All order statuses | Each seven-day forecast is frozen before its week | Rolling 90% reference, not guaranteed temporal coverage\nBands use only completed past blocks; unavailable real ingestion timestamps prevent a deployment claim')
    metrics=tables['forecast_metrics'];fig,ax=plt.subplots(figsize=(12,5))
    ax.barh(metrics.method,metrics.mae,color=['#8F9BFF','#8F9BFF','#8F9BFF','#00E0FF'])
    for i,r in enumerate(metrics.itertuples()):ax.text(r.mae+.3,i,f'{r.mae:.2f}',va='center')
    ax.margins(x=.2);ax.set(xlabel='Mean absolute error (orders / day; lower is better)',title='Same future dates, same target, four declared forecasting methods')
    save(fig,'forecast_benchmarks.png','No random-row split, future-status filter or test-set tuning | Selector uses only the previous 12 completed weeks\nA more complex model is not presumed superior; paired block uncertainty is reported separately',left=.25)
    m=metrics.set_index('method');primary=m.loc[SELECTOR];base=m.loc['seasonal_naive']
    u=tables['forecast_uncertainty'];main=u[u.block_weeks==plan['primary_bootstrap_block_weeks']].iloc[0]
    metric_rows='\n'.join(f'| {r.method} | {r.mae:.2f} | {r.rmse:.2f} | {r.wape:.2%} | {r.mase:.3f} | {r.week_coverage:.1%} | {r.interval_score:.2f} |' for r in metrics.itertuples())
    intervals='\n'.join(f'| {int(r.block_weeks)} | {r.mae_improvement:+.2f} | {r.ci_low:+.2f} to {r.ci_high:+.2f} |' for r in u.itertuples())
    report=f'''# Olist order-volume forecasting: temporal evaluation and uncertainty

## Question and readout

Can an analyst improve seven-day order-volume forecasts over repeating last week's daily counts **without using future observations to choose or calibrate a method**? This retrospective benchmark evaluates **{int(primary.evaluated_weeks)} non-overlapping weeks / {int(primary.evaluated_days)} days** from 2018, using a fixed [retrospective protocol](olist_forecast_protocol.json). The target counts **all placed orders**, including cancelled, undelivered and itemless orders. It differs from delivered GMV/order populations elsewhere in this project.

The declared past-only selector has MAE **{primary.mae:.2f} orders/day**, versus **{base.mae:.2f}** for seasonal naive. Paired mean improvement (baseline MAE minus selector MAE) is **{main.mae_improvement:+.2f} orders/day**; a four-week circular moving-block bootstrap pointwise 95% percentile interval is **{main.ci_low:+.2f} to {main.ci_high:+.2f}**. Positive values favor the selector. This is one prespecified retrospective comparison; the protocol was created after earlier Olist studies, so it is not prospective preregistration or a confirmatory test. Block-length sensitivity appears below; a limited historical period cannot establish future superiority.

| Method | MAE | RMSE | WAPE | MASE | Whole-week band coverage | Mean interval score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{metric_rows}

The selector's day-level band coverage is **{primary.day_coverage:.1%}**, whole-week coverage **{primary.week_coverage:.1%}**, and mean daily width **{primary.mean_width:.2f} orders**. The reference target is 90% **whole-week** coverage; day and whole-week coverage are different metrics. Neither is guaranteed for dependent, drifting data. Interval scores penalize width and misses, so broad bands are not automatically good forecasts. Model ranking by one retrospective number is not a deployment recommendation.

**Decision:** the primary selector comparison does not demonstrate an improvement over seasonal naive in this historical evaluation. Keep the seasonal baseline as a reference and assess new future periods before promoting a more complex method. The ridge candidate's lower observed MAE is exploratory; choosing it after inspecting this evaluation would require a fresh future validation period. High empirical coverage with very wide bands does not establish useful operational precision.

![Sequential forecasts](forecast_temporal.png)

![Same-date benchmark comparison](forecast_benchmarks.png)

## Target, chronology and leakage controls

The complete daily grid is [{plan['series_start']}, {plan['series_end_exclusive']}); zero-count days represent no records in this frozen extract, not verified marketplace downtime. A separate streaming CSV counter reconciles every date and the total; no order status, review, delivery date, item value or future customer outcome filters the target. Timestamps are used as stored, without inferred timezone conversion. Public extraction completeness and real ingestion/availability timestamps are unknown.

Monday origins start {plan['calibration_origin_start']}; each forecast covers the next seven calendar days, using history strictly before its origin. Pre-2018 origins initialize selection and calibration. Scored origins begin {plan['evaluation_start']}; the final incomplete week is excluded, leaving 30 July and 31 July 2018 unscored. Forecast weeks do not overlap. Once an evaluated week ends, its outcomes may inform **later** origins: this is sequential rolling-origin evaluation, not a fixed unchanging training set. Future-perturbation tests verify that later outcomes cannot change earlier predictions, selections or interval endpoints. Training-end and calibration-end dates are retained in every prediction row.

Declared methods: seasonal naive repeats the previous seven counts; weekday mean averages the last four corresponding weekdays; calendar ridge fits counts to an intercept, a linear time term scaled by 180 days and six weekday indicators using the last 180 days, penalty {plan['ridge_penalty']} on non-intercept coefficients, then clips point forecasts at zero. The selector chooses among these three using only mean MAE from at most the previous 12 completed forecast weeks; ties use the declared order, and the first origin defaults to seasonal naive. No hyperparameter, window or candidate is tuned on evaluation results.

## Calibration, metrics and uncertainty

For each method, each completed week supplies **one maximum absolute daily error**. Before the next origin, at most the last 12 such scores determine radius q at order-statistic rank ceil((n+1)×0.9), without interpolation. If that rank exceeds available scores, the interval is unavailable, rather than given an invented finite radius. Every scored evaluation week has mature calibration. Each day's band is [max(0, prediction−q), prediction+q]. The selector uses **its own historical errors**, not the errors of whichever candidate it currently selects. Applying these rolling scores does not restore exchangeability; the procedure is conformal-style calibration with empirical coverage assessment, not a finite-sample guarantee.

MAE/RMSE pool the identical held-out dates. WAPE = total absolute error / total actual count; it is not an average of daily percentage errors. MASE divides each week's MAE by that origin's **past-only** mean absolute seven-day seasonal difference, then averages weekly scaled errors; zero training scale remains unavailable. Interval score = width + (2/alpha)×distance below/above the interval when missed, alpha=0.1. The CSV also reports day coverage, complete-week coverage and width. These are different aspects of performance.

Paired inference uses baseline-minus-selector **weekly** MAE differences. Circular moving-block resampling retains adjacent weeks and the pairing of methods, with {plan['bootstrap_iterations']:,} fixed-seed replicates. One-, four- and eight-week blocks expose sensitivity to the dependence assumption; wraparound is an approximation and 30 scored weeks provide limited information. No p-values, best-of-many significance claim, or simultaneous confidence guarantee is produced.

| Resampling block (weeks) | Mean MAE improvement | Pointwise 95% interval (orders/day) |
| --- | ---: | ---: |
{intervals}

## Reproduce and use

Run `python -m scripts.olist_forecast --raw target/olist/raw --out target/olist/forecast`, or `python -m scripts.build_research --schemas` for all studies and native BI. Aggregates: `forecast_volume.csv`, `forecast_daily.csv`, `forecast_folds.csv`, `forecast_metrics.csv`, `forecast_uncertainty.csv`. The [daily SQL](daily_order_volume.sql), protocol, evidence fingerprints and two figures accompany the report. Raw order/customer identifiers remain local. The native forecasting page embeds evaluation-only selector daily values and fixed benchmark metrics; date selection does not refit models or recompute full-period benchmark cards. Native rendering, refresh and DAX execution remain unverified.

Use this as a forecasting-method and scientific-validation demonstration. Before staffing/inventory use, obtain real ingestion timestamps, a stable business calendar, a current series, repeated future evaluation, and intervention/capacity cost information. No revenue forecast, causal uplift, profit or live-service readiness is claimed. The project remains non-commercial with zero recurring infrastructure cost. Source: [official Olist public dataset]({SOURCE}); derived data, figures and the data-containing BI package retain [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

Method references: [Hyndman and Athanasopoulos, rolling-origin evaluation]({REFERENCES[0]}), [forecast accuracy definitions]({REFERENCES[1]}), and [Stankeviciute et al., Conformal Time-Series Forecasting]({REFERENCES[2]}). These motivate chronology, metrics and caution about temporal exchangeability; this benchmark does not implement that paper's algorithm or claim its guarantees. All numerical findings above are computed from the local official CSVs.
'''
    (out/'FORECAST_VALIDATION.md').write_text(report,encoding='utf-8')


def run(raw:Path,out:Path):
    raw,out=raw.resolve(),out.resolve()
    if raw==out or raw in out.parents or out in raw.parents:raise ValueError('Raw/output directories must be separate')
    plan=json.loads(PROTOCOL.read_text())
    if plan['models']!=list(MODELS) or plan['horizon_days']!=7 or plan['origin_step_days']!=7 or plan['ridge_days']!=180 or plan['primary_method']!=SELECTOR:
        raise ValueError('Unsupported protocol; update implementation and tests explicitly')
    con=duckdb.connect();con.execute('set threads=1')
    try:quality=load_fact(con,raw);series,daily=load_series(con,raw,plan)
    finally:con.close()
    tables=backtest(series,plan);tables['forecast_volume']=daily
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items():table.to_csv(out/(name+'.csv'),index=False,float_format='%.12g',lineterminator='\n')
    (out/'olist_forecast_protocol.json').write_bytes(PROTOCOL.read_bytes())
    (out/'daily_order_volume.sql').write_bytes((SQL/'daily_order_volume.sql').read_bytes())
    present(tables,plan,out)
    selected=tables['forecast_daily'].query('phase == "evaluation" and method == @SELECTOR')
    evidence={'source':SOURCE,'source_kind':'historical_public_olist_forecast','synthetic':False,'license':'CC-BY-NC-SA-4.0',
        'quality':quality,'protocol':plan,'protocol_sha256':sha256(PROTOCOL),'implementation_sha256':sha256(Path(__file__)),
        'query_sha256':sha256(SQL/'daily_order_volume.sql'),'order_fact_sql_sha256':sha256(SQL/'order_fact.sql'),
        'raw_daily_counts_reconciled':True,'series_days':len(series),'placed_orders':int(series.sum()),
        'evaluation_days':len(selected),'evaluation_weeks':int(selected.origin.nunique()),
        'unscored_tail_days':int((series.index>selected.day.max()).sum()),
        'metrics':tables['forecast_metrics'].to_dict('records'),'paired_uncertainty':tables['forecast_uncertainty'].to_dict('records'),
        'aggregate_sha256':{n+'.csv':sha256(out/(n+'.csv')) for n in tables},'method_sources':REFERENCES,
        'guaranteed_temporal_coverage':False,'real_ingestion_times_verified':False,'native_engine_executed':False}
    (out/'forecast_evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return {k:evidence[k] for k in ('series_days','placed_orders','evaluation_days','evaluation_weeks','metrics','paired_uncertainty')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,default=ROOT/'target/olist/raw')
    p.add_argument('--out',type=Path,default=ROOT/'target/olist/forecast');a=p.parse_args()
    print(json.dumps(run(a.raw,a.out),indent=2))
