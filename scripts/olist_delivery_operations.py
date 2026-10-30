"""Comparable-period delivery diagnostics and Kitagawa rate/mix decomposition.

No causal attribution, revenue-loss estimate, review-response filter or live query.
Only aggregated outputs are published; customer-cluster resampling stays local.
"""
from __future__ import annotations

import argparse
import calendar
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from scripts.advanced_olist import ROOT, SQL, SOURCE, cluster_risk_difference, load_fact, sha256


def decompose_rates(groups: pd.DataFrame, minimum: int=20) -> tuple[pd.DataFrame, dict]:
    """Symmetric Kitagawa identity on fixed common-support month/state strata.

    Within = average year-specific weights times rate change.
    Mix = average year-specific rates times weight change.
    Separately standardize with POOLED order-count weights, not the Kitagawa weights.
    """
    columns={'year','month','state','orders','late_orders'}
    if not columns.issubset(groups) or groups.empty or minimum<1:
        raise ValueError('Nonempty year/month/state counts and positive minimum required')
    values=groups[['orders','late_orders']].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<0).any() or (values%1).any() or (values[:,0]<=0).any() or (values[:,1]>values[:,0]).any():
        raise ValueError('Invalid order/late counts')
    if not groups.year.isin([2017,2018]).all() or not groups.month.isin(range(1,8)).all() or groups.state.isna().any():
        raise ValueError('Only matched January-July 2017/2018 strata accepted')
    if groups.duplicated(['year','month','state']).any():
        raise ValueError('Duplicate year/month/state stratum')
    common=groups[groups.year==2017].merge(groups[groups.year==2018],on=['month','state'],suffixes=('_2017','_2018'),validate='one_to_one')
    common=common[(common.orders_2017>=minimum)&(common.orders_2018>=minimum)].copy()
    if common.empty: raise ValueError('No shared strata with required support')
    totals={year:float(common[f'orders_{year}'].sum()) for year in (2017,2018)}
    for year in (2017,2018):
        common[f'weight_{year}']=common[f'orders_{year}']/totals[year]
        common[f'rate_{year}']=common[f'late_orders_{year}']/common[f'orders_{year}']
    common['pooled_weight']=(common.orders_2017+common.orders_2018)/sum(totals.values())
    common['within_contribution']=(common.weight_2017+common.weight_2018)/2*(common.rate_2018-common.rate_2017)
    common['mix_contribution']=(common.rate_2017+common.rate_2018)/2*(common.weight_2018-common.weight_2017)
    rates={year:float(common[f'late_orders_{year}'].sum()/totals[year]) for year in (2017,2018)}
    within=float(common.within_contribution.sum());mix=float(common.mix_contribution.sum())
    if not np.isclose(within+mix,rates[2018]-rates[2017],atol=1e-12,rtol=0):
        raise ValueError('Rate/mix decomposition failed reconciliation')
    summary={'common_strata':len(common),'minimum_orders_per_year_stratum':minimum,
             'common_rate_2017':rates[2017],'common_rate_2018':rates[2018],
             'common_rate_change':rates[2018]-rates[2017],
             'within_contribution':within,'mix_contribution':mix}
    for year in (2017,2018):
        all_orders=int(groups[groups.year==year].orders.sum())
        summary[f'common_orders_{year}']=int(totals[year])
        summary[f'common_coverage_{year}']=totals[year]/all_orders
        summary[f'pooled_standardized_rate_{year}']=float((common.pooled_weight*common[f'rate_{year}']).sum())
    return common.sort_values(['month','state']).reset_index(drop=True),summary


def analyze(con, *, iterations=1000):
    con.execute((SQL/'delivery_operations.sql').read_text())
    groups=con.execute('''select year,month,state,count(*) as orders,sum(late::int) as late_orders
        from operations_orders group by 1,2,3 order by 1,2,3''').df()
    strata,summary=decompose_rates(groups)
    month_contributions=strata.groupby('month',as_index=False)[['within_contribution','mix_contribution']].sum()
    dominant=month_contributions.loc[month_contributions.within_contribution.abs().idxmax()]
    summary['dominant_within_month']=int(dominant.month)
    summary['dominant_within_month_contribution']=float(dominant.within_contribution)
    monthly=con.execute('''select year,month,count(*) as orders,sum(late::int) as late_orders,
        avg(late::int) as late_rate,median(transit_days) as median_transit_days,
        quantile_cont(transit_days,.9) as p90_transit_days
        from operations_orders group by 1,2 order by 1,2''').df()
    states=con.execute('''select state,count(*) as orders,sum(late::int) as late_orders,
        avg(late::int) as late_rate,coalesce(sum(gmv) filter(where late),0) as delivered_late_gmv,
        quantile_cont(transit_days,.9) as p90_transit_days
        from operations_orders where year=2018 group by 1 order by late_orders desc,state''').df()
    states['late_order_share']=states.late_orders/states.late_orders.sum()
    states['review_priority_eligible']=states.orders>=100
    totals=con.execute('''select year,count(*) as orders,sum(late::int) as late_orders,avg(late::int) as late_rate
        from operations_orders group by 1 order by 1''').df()
    # Independent raw-order date/status calculation for the eligibility denominator.
    control=con.execute('''select count(*) from raw_orders o join raw_customers c using(customer_id)
        where o.order_status='delivered' and year(o.order_purchase_timestamp) in (2017,2018)
          and month(o.order_purchase_timestamp) between 1 and 7
          and o.order_delivered_customer_date>=o.order_purchase_timestamp
          and o.order_estimated_delivery_date>=o.order_purchase_timestamp::date
          and c.customer_unique_id is not null
          and exists(select 1 from raw_items i where i.order_id=o.order_id and i.price>0)''').fetchone()[0]
    if control!=int(totals.orders.sum()) or int(monthly.orders.sum())!=control or int(groups.orders.sum())!=control:
        raise ValueError('Operations denominators disagree with independent raw-order control')
    private=con.execute('''select sum((year=2018 and late)::int),sum((year=2018)::int),
        sum((year=2017 and late)::int),sum((year=2017)::int)
        from operations_orders group by customer_unique_id order by customer_unique_id''').fetchnumpy()
    bootstrap=cluster_risk_difference(np.column_stack(list(private.values())),iterations=iterations,seed=20261028)
    summary['full_rate_change']=bootstrap['risk_difference']
    summary['full_change_ci_low']=bootstrap['ci_low'];summary['full_change_ci_high']=bootstrap['ci_high']
    summary['bootstrap_customers']=bootstrap['customers'];summary['bootstrap_iterations']=iterations
    summary['bootstrap_valid_replicates']=bootstrap['valid_replicates'];summary['bootstrap_seed']=bootstrap['seed']
    summary['comparison']='January–July 2018 minus January–July 2017; frozen delivered status'
    for r in totals.itertuples():
        summary[f'orders_{r.year}']=int(r.orders);summary[f'late_orders_{r.year}']=int(r.late_orders)
        summary[f'full_rate_{r.year}']=float(r.late_rate)
    coverage=con.execute('''select count(*) as candidate_orders,
        count(*) filter(where delivered_at is null or estimated_at is null) as missing_dates,
        count(*) filter(where delivered_at<purchased_at or estimated_at<purchased_at::date) as invalid_dates,
        count(*) filter(where customer_unique_id is null) as missing_customer_identity
        from order_fact where order_status='delivered' and gmv>0
          and year(purchased_at) in (2017,2018) and month(purchased_at) between 1 and 7''').df().to_dict('records')[0]
    summary['coverage_overlapping_exclusions']=coverage
    priorities=states[states.review_priority_eligible].head(5)
    summary['priority_states']=priorities.state.tolist()
    summary['priority_late_order_share']=float(priorities.late_order_share.sum())
    return {'operations_monthly':monthly,'operations_states':states,'operations_strata':strata,'operations_month_contributions':month_contributions,
            'operations_summary':pd.DataFrame([{k:v for k,v in summary.items() if isinstance(v,(int,float))}])},summary


def present(tables,s,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.facecolor':'#0B0F19','axes.facecolor':'#0B0F19','text.color':'#EDF2F8',
        'axes.labelcolor':'#B9C5CE','xtick.color':'#B9C5CE','ytick.color':'#B9C5CE','axes.edgecolor':'#334155','font.size':10})
    def save(fig,name,note,left=.12):
        fig.text(.05,.96,'NEXUS / OLIST DELIVERY DIAGNOSTICS',color='#00E0FF',fontsize=11)
        ax=fig.add_axes([.79,.91,.16,.07]);ax.imshow(plt.imread(ROOT/'branding/nexus_official_transparent.png'));ax.axis('off')
        fig.text(.05,.025,note,color='#B9C5CE',fontsize=9)
        fig.subplots_adjust(top=.84,bottom=.18,left=left,right=.95)
        fig.savefig(out/name,dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,6))
    for year,color in ((2017,'#8F9BFF'),(2018,'#00E0FF')):
        d=tables['operations_monthly'].query('year == @year')
        ax.plot(d.month,d.late_rate*100,marker='o',color=color,label=str(year))
    ax.set(xticks=range(1,8),xticklabels=['Jan','Feb','Mar','Apr','May','Jun','Jul'],ylabel='Late delivered orders (%)',
           title='Delivery experience: compare the same seven purchase months')
    ax.legend(facecolor='#0B0F19',labelcolor='#EDF2F8')
    save(fig,'delivery_matched_months.png','Frozen delivered orders with valid dates | Calendar-date deadline | No review-response filter; undelivered orders excluded')
    fig,ax=plt.subplots(figsize=(12,5))
    values=np.array([s['within_contribution'],s['mix_contribution'],s['common_rate_change']])*100
    ax.barh(['Within month/state','Composition mix','Observed common-support change'],values,color=['#00E0FF','#8F9BFF','#6E55C6'])
    ax.axvline(0,color='#B9C5CE',lw=.8)
    for i,value in enumerate(values):ax.annotate(f'{value:+.2f} pp',(value,i),xytext=(8 if value>=0 else -8,0),textcoords='offset points',ha='left' if value>=0 else 'right',va='center')
    ax.margins(x=.3);ax.set(xlabel='2018 minus 2017 late-rate contribution (percentage points)',title='Rate change separates within-stratum movement from mix')
    save(fig,'delivery_rate_mix.png','Kitagawa symmetric identity | Common support only | Month/state do not remove all confounding; contributions are not causal',left=.30)
    report=f'''# Olist delivery: comparable periods, composition and review priorities

Decision: **where should an analyst begin a delivery root-cause review?** This historical diagnostic uses the [official Olist public extract]({SOURCE}), independently of E-Commerce/Greenweez and independently of review-response selection. Derived CSVs, figures and the data-containing Olist BI report retain [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). NEXUS authored the transformations; no endorsement is implied.

## Readout

- January–July 2017: **{s['late_orders_2017']:,}/{s['orders_2017']:,}** eligible delivered orders were late (**{s['full_rate_2017']:.2%}**). January–July 2018: **{s['late_orders_2018']:,}/{s['orders_2018']:,}** (**{s['full_rate_2018']:.2%}**). Full-sample change: **{s['full_rate_change']*100:+.2f} percentage points**, customer-cluster bootstrap pointwise 95% interval **{s['full_change_ci_low']*100:+.2f} to {s['full_change_ci_high']*100:+.2f} pp**, {s['bootstrap_iterations']:,} fixed-seed replicates. This is observed experience among delivered orders, not a causal treatment effect or a current service-level claim.
- Common support retains **{s['common_strata']} month/state strata**, each with >={s['minimum_orders_per_year_stratum']} orders in each year: **{s['common_coverage_2017']:.2%}** of 2017 eligible orders and **{s['common_coverage_2018']:.2%}** of 2018. Within this subset, the crude change is **{s['common_rate_change']*100:+.2f} pp**. Symmetric Kitagawa contributions are **{s['within_contribution']*100:+.2f} pp within strata** and **{s['mix_contribution']*100:+.2f} pp composition mix**; their sum reconciles exactly.
- With pooled-order weights fixed across those same strata, standardized rates are **{s['pooled_standardized_rate_2017']:.2%}** and **{s['pooled_standardized_rate_2018']:.2%}**. These are descriptive sensitivity estimates without an adjusted confidence interval. Their pooled weights differ from Kitagawa's average-of-year-weights convention; do not substitute one for the other.
- **{calendar.month_name[s['dominant_within_month']]}** has the largest absolute within-stratum contribution: **{s['dominant_within_month_contribution']*100:+.2f} pp**. Use the published monthly contribution ledger to focus the first record-level investigation. This arithmetic contribution is not evidence of a specific disruption, carrier failure or intervention effect.
- The five states with the largest **observed 2018 late-order burden** among states with >=100 eligible orders are **{', '.join(s['priority_states'])}**. They account for **{s['priority_late_order_share']:.2%}** of all eligible 2018 late orders. These are investigation priorities by volume, not a statistically established ranking of service quality. Large states can have high counts with moderate rates; all states and denominators remain in the CSV.

![Matched purchase months](delivery_matched_months.png)

![Exact descriptive rate/mix decomposition](delivery_rate_mix.png)

## Decision and next evidence

Start with the high-burden states and month/state cells contributing most to the observed change. Inspect carrier handoff, seller dispatch, promised lead times and route-level records before proposing an intervention. This extract does not identify a cause. A pilot would need a defined comparison group and contemporaneous dispatch/delivery data; do not assign revenue uplift or avoided losses to these descriptive differences.

Primary measurement: late delivered-order rate using the same calendar-date deadline. Guardrails: undelivered/cancelled order share, promised lead time, transit-time percentiles and missing-date coverage. The delivered-only rate could improve by lengthening promises or excluding non-deliveries, so it cannot be used alone as an optimization target. The output `delivered_late_gmv` is item GMV associated with already delivered late orders, **not lost revenue, profit or refund exposure**.

## Method and limits

One row per validated order. Eligibility: final status delivered; positive item GMV; purchase in January–July of 2017 or 2018; customer identity available; actual delivery >= purchase timestamp; estimated delivery date >= purchase calendar date. Late = actual delivery calendar date later than estimated calendar date. Source timestamps are used as stored, with no inferred timezone conversion. Review availability, score and answer timing are never eligibility criteria. This differs intentionally from the review-association sample in the [base study](REPORT.md).

Coverage counts and overlapping exclusions are in `operations_evidence.json`. A raw-order/customer/item-existence query independently reconciles the eligible denominator. Monthly and stratum counts reconcile to the full sample. Customer identities are resampled with all their eligible orders across both years ({s['bootstrap_customers']:,} clusters); the interval describes the **full eligible sample's crude rate change only**, not common-support, standardized or decomposition components. Bootstrap settings: seed {s['bootstrap_seed']}, {s['bootstrap_valid_replicates']:,} valid replicates. These sampling intervals do not correct selection, confounding or incomplete marketplace coverage.

Common-support selection is fixed before comparison using order counts, not late outcomes. Kitagawa identity: sum(mean year weights × year rate change) + sum(mean year rates × year weight change). Neither component is a causal effect; product, seller, carrier and route composition can still change inside month/state cells. Common-support coverage loss changes the analyzed population, so the full and restricted changes must be kept separate. Pooled standardization uses combined year-specific order counts as weights. States with low volumes remain visible but are excluded from the five-state review-priority list below the stated threshold. No selected state's rate is declared superior or significant.

Both calendar windows have seven purchase months. Frozen delivered status may reflect outcomes after purchase-window end; this is a retrospective comparison, not reconstructed as-of operations. Undelivered, cancelled and missing-date orders can have different experience and are outside this endpoint. The analysis is historical and observational; it cannot isolate an operational mechanism or forecast current performance.

## Reproduce

```powershell
python -m scripts.olist_delivery_operations --out target/olist/operations
python -m unittest discover -s tests -p test_olist_delivery_operations.py -v
python -m scripts.build_olist_powerbi --operations target/olist/operations
```

The four official base CSVs suffice. Raw identifiers remain under ignored `target/`; outputs are aggregated by period, state and month/state. The native BI package is editable source, with Desktop rendering, DAX execution and refresh unverified. No browser, Playwright, PC-screen control, paid resource or cloud query is used.
'''
    (out/'DELIVERY_OPERATIONS.md').write_text(report,encoding='utf-8')


def run(raw: Path,out: Path,*,iterations=1000):
    raw,out=raw.resolve(),out.resolve()
    if raw==out or raw in out.parents or out in raw.parents:raise ValueError('Raw/output directories must be separate')
    con=duckdb.connect();con.execute('set threads=1')
    try:
        quality=load_fact(con,raw);tables,summary=analyze(con,iterations=iterations)
    finally:con.close()
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items():table.to_csv(out/(name+'.csv'),index=False,float_format='%.12g',lineterminator='\n')
    evidence={'source':SOURCE,'source_kind':'historical_public_olist_operations','license':'CC-BY-NC-SA-4.0',
        'quality':quality,'summary':summary,'implementation_sha256':sha256(Path(__file__)),
        'query_sha256':sha256(SQL/'delivery_operations.sql'),'order_fact_sql_sha256':sha256(SQL/'order_fact.sql'),
        'aggregate_sha256':{name+'.csv':sha256(out/(name+'.csv')) for name in tables},
        'desktop_render_verified':False,'dax_engine_executed':False}
    present(tables,summary,out)
    (out/'operations_evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=ROOT/'target/olist/raw')
    parser.add_argument('--out',type=Path,default=ROOT/'target/olist/operations')
    args=parser.parse_args();print(json.dumps(run(args.raw,args.out),indent=2))
