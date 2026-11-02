"""Review availability, sharp binary-outcome bounds and pattern-mixture sensitivity.

Retrospective plan, not prospective preregistration. No causal identification,
automatic imputation, cloud reads, browser use or publication of row identifiers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from scripts.advanced_olist import ROOT, SQL, SOURCE, load_fact, sha256

PROTOCOL = ROOT/'contracts/olist_review_protocol.json'
METHOD_SOURCE = 'https://www.ncbi.nlm.nih.gov/books/NBK209895/'


def validate_counts(counts) -> np.ndarray:
    """Rows: late, on time. Columns: observed poor, observed rating, eligible order."""
    c=np.asarray(counts,dtype=float)
    if c.shape!=(2,3) or not np.isfinite(c).all() or (c<0).any() or (c%1).any():
        raise ValueError('Two delivery groups with three finite nonnegative integer counts required')
    if (c[:,0]>c[:,1]).any() or (c[:,1]>c[:,2]).any() or (c[:,2]<=0).any():
        raise ValueError('Poor <= observed <= eligible and positive eligible groups required')
    return c


def contrast(counts) -> dict:
    c=validate_counts(counts);poor,observed,total=c.T
    missing=total-observed
    lower=poor/total;upper=(poor+missing)/total
    available=poor/observed if (observed>0).all() else None
    return {'complete_case_difference':float(available[0]-available[1]) if available is not None else None,
            'bound_low':float(lower[0]-upper[1]),'bound_high':float(upper[0]-lower[1]),
            'late_response_rate':float(observed[0]/total[0]),
            'on_time_response_rate':float(observed[1]/total[1])}


def scenario(counts,q_late,q_on_time):
    """Pattern-mixture identity: q is an ASSUMED poor probability among unavailable ratings."""
    c=validate_counts(counts)
    q=np.asarray([q_late,q_on_time],dtype=float)
    if not np.isfinite(q).all() or ((q<0)|(q>1)).any():raise ValueError('Assumed probabilities must lie in [0,1]')
    rates=(c[:,0]+(c[:,2]-c[:,1])*q)/c[:,2]
    return float(rates[0]-rates[1])


def tipping_frontier(counts,q_late):
    """q_on_time giving a zero contrast; None if no on-time outcomes are missing.

    Values outside [0,1] are kept: they explicitly indicate an infeasible tipping point.
    """
    c=validate_counts(counts)
    if not np.isfinite(q_late) or not 0<=q_late<=1:raise ValueError('Invalid late probability')
    missing=c[:,2]-c[:,1]
    if not missing[1]:return None
    return float((c[0,0]/c[0,2]-c[1,0]/c[1,2]+missing[0]/c[0,2]*q_late)/(missing[1]/c[1,2]))


def cluster_intervals(counts,*,iterations=1000,seed=20261029):
    """Resample customer clusters, with all orders and windows kept together.

    Each window has six counts: late poor/observed/total, on-time poor/observed/total.
    Endpoint intervals are pointwise percentile sampling intervals, NOT a confidence
    region covering the entire partially identified set.
    """
    values=np.asarray(counts,dtype=float)
    if values.ndim!=3 or values.shape[2]!=6 or not len(values) or iterations<100:
        raise ValueError('Nonempty customer/window/six-count array and >=100 replicates required')
    if not np.isfinite(values).all() or (values<0).any() or (values%1).any():raise ValueError('Invalid cluster counts')
    if (values[:,:,0]>values[:,:,1]).any() or (values[:,:,1]>values[:,:,2]).any() or (values[:,:,3]>values[:,:,4]).any() or (values[:,:,4]>values[:,:,5]).any():
        raise ValueError('Invalid within-cluster counts')
    totals=values.sum(axis=0)
    for c in totals:validate_counts(c.reshape(2,3))
    # Exact empirical cluster bootstrap via sufficient count patterns. Resampling
    # identical customer ledgers individually or their multinomial frequencies has
    # the same distribution, without repeatedly allocating a full customer array.
    patterns,frequencies=np.unique(values.reshape(len(values),-1),axis=0,return_counts=True)
    rng=np.random.default_rng(seed)
    draws=rng.multinomial(len(values),frequencies/len(values),size=iterations)
    totals=(draws@patterns).reshape(iterations,values.shape[1],6)
    valid=(totals[:,:,[1,2,4,5]]>0).all(axis=(1,2))
    t=totals[valid];lp,lr,ln,op,orr,on=np.moveaxis(t,2,0)
    samples=np.stack([lp/lr-op/orr,lp/ln-(op+on-orr)/on,(lp+ln-lr)/ln-op/on],axis=2)
    if len(samples)<.95*iterations:raise ValueError('Insufficient two-group respondent support in bootstrap')
    limits=np.quantile(samples,[.025,.975],axis=0)
    return limits,{'customers':len(values),'iterations':iterations,'valid_replicates':len(samples),'seed':seed,'unique_cluster_patterns':len(patterns),'resampling':'exact multinomial frequencies of identical customer ledgers'}


def raw_control(con,plan):
    """Independent raw-table/pandas reconciliation; no order_fact or study SQL helpers."""
    orders=con.execute('select * from raw_orders').df()
    customers=con.execute('select customer_id,customer_unique_id from raw_customers').df()
    items=con.execute('select distinct order_id from raw_items where price>0').df()
    rows=orders.merge(customers,on='customer_id',validate='many_to_one').merge(items,on='order_id',validate='one_to_one')
    start=pd.Timestamp(plan['purchase_start']);cutoff=pd.Timestamp(plan['observation_cutoff_exclusive'])
    p=rows.order_purchase_timestamp;d=rows.order_delivered_customer_date;e=rows.order_estimated_delivery_date
    rows=rows[(rows.order_status=='delivered')&rows.customer_unique_id.notna()&(p>=start)&(p<cutoff)&
              (d>=p)&(e>=p.dt.normalize())&(d+pd.Timedelta(days=max(plan['windows_days']))<cutoff)].copy()
    rows['late']=rows.order_delivered_customer_date.dt.normalize()>rows.order_estimated_delivery_date.dt.normalize()
    reviews=con.execute('select * from raw_reviews').df().merge(
        rows[['order_id','order_delivered_customer_date']],on='order_id',validate='many_to_one')
    a=reviews.review_answer_timestamp;d=reviews.order_delivered_customer_date
    reviews=reviews[(a>=d)&(a<cutoff)].sort_values(
        ['review_answer_timestamp','review_creation_date','review_id','review_score'],na_position='last',kind='stable')
    output=[]
    for window in plan['windows_days']:
        selected=reviews[reviews.review_answer_timestamp<=reviews.order_delivered_customer_date+pd.Timedelta(days=window)].drop_duplicates('order_id')
        joined=rows[['order_id','late']].merge(selected[['order_id','review_score']],how='left',on='order_id',validate='one_to_one')
        output.append([[int(((g.review_score<=plan['poor_score_max'])&g.review_score.notna()).sum()),int(g.review_score.notna().sum()),len(g)]
                       for flag in (True,False) for g in [joined[joined.late==flag]]])
    return np.asarray(output),len(rows),int(rows.customer_unique_id.nunique())


def analyze(con,plan):
    # DuckDB accepts multiple statements but binds parameters to the last one only.
    statements=(SQL/'review_selection.sql').read_text(encoding='utf-8').split(';')
    con.execute(statements[0],{'start':plan['purchase_start'],'cutoff':plan['observation_cutoff_exclusive'],'maximum_window':max(plan['windows_days'])})
    con.execute(';'.join(statements[1:]),{'windows':plan['windows_days'],'cutoff':plan['observation_cutoff_exclusive'],'poor_max':plan['poor_score_max']})
    groups=con.execute('''select window_days,late,count(*) as eligible_orders,
        sum(responded::int) as observed_ratings,sum(poor::int) as poor_ratings
        from review_observations group by 1,2 order by 1,2 desc''').df()
    availability=con.execute('''with history as (
        select c.order_id,count(r.review_answer_timestamp) as answers,
            min(r.review_answer_timestamp) filter(where r.review_answer_timestamp>=c.delivered_at) as first_post
        from review_cohort c left join raw_reviews r on r.order_id=c.order_id
            and r.review_answer_timestamp < $cutoff group by c.order_id
    ) select o.window_days,o.late,
        case when o.responded then 'observed_within_window'
             when h.answers=0 then 'no_dated_answer_before_cutoff'
             when h.first_post is null then 'pre_delivery_answers_only'
             else 'post_delivery_answer_after_window' end as availability_reason,
        count(*) as orders
    from review_observations o join history h using(order_id)
    group by 1,2,3 order by 1,2 desc,3''',{'cutoff':plan['observation_cutoff_exclusive']}).df()
    counts=np.array([groups[groups.window_days==w][['poor_ratings','observed_ratings','eligible_orders']].to_numpy() for w in plan['windows_days']])
    independent,n,customers=raw_control(con,plan)
    if not np.array_equal(counts,independent):raise ValueError('Review cohort or first-answer outcomes disagree with independent raw control')
    if con.execute('select count(*)-count(distinct (order_id,window_days)) from review_observations').fetchone()[0]:
        raise ValueError('Review joins expanded the order/window grain')
    private=con.execute('''select customer_unique_id,window_days,
        sum((late and poor)::int) lp,sum((late and responded)::int) lr,sum(late::int) ln,
        sum((not late and poor)::int) op,sum((not late and responded)::int) rr,sum((not late)::int) nn
        from review_observations group by 1,2 order by 1,2''').df()
    array=private[['lp','lr','ln','op','rr','nn']].to_numpy().reshape(customers,len(plan['windows_days']),6)
    if not np.array_equal(array.sum(axis=0),counts.reshape(len(counts),6)):raise ValueError('Cluster ledger does not reconcile')
    limits,bootstrap=cluster_intervals(array,iterations=plan['bootstrap_iterations'],seed=plan['bootstrap_seed'])
    summaries=[]
    for i,(window,c) in enumerate(zip(plan['windows_days'],counts)):
        s={'window_days':window,'eligible_orders':n,**contrast(c)}
        for j,key in enumerate(('complete_case','lower_bound_endpoint','upper_bound_endpoint')):
            s[key+'_ci_low']=float(limits[0,i,j]);s[key+'_ci_high']=float(limits[1,i,j])
        summaries.append(s)
    primary=counts[plan['windows_days'].index(plan['primary_window_days'])]
    grid=np.linspace(0,1,round(1/plan['sensitivity_grid_step'])+1)
    sensitivity=pd.DataFrame([{'q_late_missing':float(l),'q_on_time_missing':float(o),'risk_difference':scenario(primary,l,o)} for l in grid for o in grid])
    frontier=pd.DataFrame([{'q_late_missing':float(q),'q_on_time_zero_difference':tipping_frontier(primary,float(q))} for q in grid])
    groups['unavailable_ratings']=groups.eligible_orders-groups.observed_ratings
    groups['response_rate']=groups.observed_ratings/groups.eligible_orders
    groups['observed_poor_rate']=groups.poor_ratings/groups.observed_ratings.replace(0,np.nan)
    if availability.orders.sum()!=n*len(plan['windows_days']):raise ValueError('Availability reason ledger lost orders')
    return {'review_groups':groups,'review_summary':pd.DataFrame(summaries),'review_sensitivity':sensitivity,
            'review_tipping':frontier,'review_availability':availability},bootstrap


def present(tables,plan,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.facecolor':'#0B0F19','axes.facecolor':'#0B0F19','text.color':'#EDF2F8',
        'axes.labelcolor':'#B9C5CE','xtick.color':'#B9C5CE','ytick.color':'#B9C5CE','axes.edgecolor':'#334155','font.size':11})
    def save(fig,name,note):
        fig.text(.07,.95,'NEXUS / REVIEW SELECTION SENSITIVITY',color='#00E0FF',fontsize=11)
        logo=fig.add_axes([.79,.90,.16,.07]);logo.imshow(plt.imread(ROOT/'branding/nexus_official_transparent.png'));logo.axis('off')
        fig.text(.07,.025,note,fontsize=9,color='#B9C5CE')
        fig.subplots_adjust(top=.83,bottom=.18,left=.22 if name=='review_bounds.png' else .12,right=.88)
        fig.savefig(out/name,dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
    summary=tables['review_summary'];primary=summary[summary.window_days==plan['primary_window_days']].iloc[0]
    fig,ax=plt.subplots(figsize=(12,6))
    for i,r in enumerate(summary.itertuples()):
        ax.plot([r.bound_low*100,r.bound_high*100],[i,i],lw=9,color='#6E55C6',alpha=.75)
        ax.errorbar(r.complete_case_difference*100,i,xerr=[[100*(r.complete_case_difference-r.complete_case_ci_low)],[100*(r.complete_case_ci_high-r.complete_case_difference)]],fmt='o',color='#00E0FF',capsize=5)
    ax.axvline(0,color='#B9C5CE',lw=1);ax.set(yticks=range(len(summary)),yticklabels=[f'{w}-day window' for w in summary.window_days],xlabel='Late minus on-time poor-rating difference (percentage points)',title='Observed association versus missing-rating bounds')
    save(fig,'review_bounds.png','Purple: sharp binary-outcome range (not a CI) | Cyan: available-case contrast + pointwise 95% cluster interval\nSame mature delivered-order cohort in every window; full-rating outcome is hypothetical; no causal interpretation')
    grid=tables['review_sensitivity'].pivot(index='q_on_time_missing',columns='q_late_missing',values='risk_difference')
    fig,ax=plt.subplots(figsize=(10,7));x=grid.columns.to_numpy()*100;y=grid.index.to_numpy()*100;z=grid.to_numpy()*100
    limit=max(abs(z.min()),abs(z.max()));mesh=ax.pcolormesh(x,y,z,cmap='coolwarm',vmin=-limit,vmax=limit,shading='nearest')
    if z.min()<0<z.max():ax.contour(x,y,z,levels=[0],colors=['white'],linewidths=2)
    fig.colorbar(mesh,ax=ax,label='Assumed full-rating difference (pp)')
    ax.set(xlabel='Assumed poor ratings among unavailable LATE ratings (%)',ylabel='Assumed poor ratings among unavailable ON-TIME ratings (%)',title=f"{plan['primary_window_days']}-day pattern-mixture sensitivity")
    save(fig,'review_sensitivity_grid.png','Assumptions, not fitted predictions | White line, when present: zero contrast | Every [0,1] missing-rating probability allowed\nNo missing-at-random claim; review behavior and unmeasured confounding remain unresolved')
    g=tables['review_groups'];g=g[g.window_days==plan['primary_window_days']]
    late=g[g.late].iloc[0];on=g[~g.late].iloc[0]
    reasons=tables['review_availability'];reasons=reasons[reasons.window_days==plan['primary_window_days']]
    reason_rows='\n'.join(f'| {"Late" if r.late else "On time"} | {r.availability_reason} | {r.orders:,} |' for r in reasons.itertuples())
    direction='stays above zero' if primary.bound_low>0 else ('stays below zero' if primary.bound_high<0 else 'includes zero')
    report=f'''# Olist review selection: missing outcomes and scientific sensitivity

## Research question and answer

How sensitive is the descriptive late-versus-on-time poor-rating contrast to unavailable post-delivery ratings? On the fixed mature cohort of **{int(primary.eligible_orders):,} delivered orders**, the primary 30-day available-case difference is **{primary.complete_case_difference*100:+.2f} percentage points** (customer-cluster pointwise 95% percentile interval **{primary.complete_case_ci_low*100:+.2f} to {primary.complete_case_ci_high*100:+.2f} pp**). Allowing every unavailable rating to be either poor or not poor yields the sharp range **{primary.bound_low*100:+.2f} to {primary.bound_high*100:+.2f} pp**, which **{direction}**. This is a missing-outcome robustness statement within this selected historical delivered cohort, not a causal delivery effect or proof that missing ratings resemble observed ones.

Thirty-day response coverage is **{int(late.observed_ratings):,}/{int(late.eligible_orders):,} ({late.response_rate:.2%})** for late orders and **{int(on.observed_ratings):,}/{int(on.eligible_orders):,} ({on.response_rate:.2%})** for on-time orders. Responses before delivery, after a window endpoint or on/after the cutoff are unavailable for that window. Unavailable ratings are not scored as good. The hypothetical target is the poor-rating proportion if every eligible order supplied a rating within the window; whether such a rating is well defined for every nonrespondent is itself a limitation.

**Availability is not the same as nonresponse.** In particular, pre-delivery-only answers are existing reviews excluded by the temporal definition. Delivery timing and review timing jointly determine selection. The reason ledger distinguishes that mechanism from absent dated answers and late answers; none is diagnosed as a capture failure from this extract alone.

| Delivery group | Primary-window availability | Orders |
| --- | --- | ---: |
{reason_rows}

![Observed contrast and identification ranges](review_bounds.png)

![Assumption sensitivity](review_sensitivity_grid.png)

## Locked retrospective protocol

The machine-readable [analysis plan](olist_review_protocol.json) fixes eligibility, primary 30-day window, 7/90-day sensitivity windows, score threshold, review policy and resampling seed. It was written for this extension **after earlier related Olist analyses**; it is not prospective preregistration or an independent confirmatory replication. No window or subgroup is selected by its significance; no p-value search or group ranking is used.

Purchases start {plan['purchase_start']}; observation ends strictly before {plan['observation_cutoff_exclusive']}. All windows use the **same** cohort: final delivered status; positive item GMV; known customer identity; actual delivery at/after purchase; promised calendar date at/after purchase date; delivery plus 90 days strictly before cutoff. This maturity restriction prevents unequal administrative follow-up across windows, at the cost of excluding later deliveries. It does not verify that the public extract captured every review. Late means actual delivery **calendar date** exceeds promised calendar date. Timestamps are used as stored; no timezone conversion is inferred.

Within each window choose the **first** raw review answer at/after delivery and at/before its endpoint, with answer strictly before cutoff. Ties use creation timestamp, review ID and score ascending, nulls last. The base study's latest-review policy is deliberately not reused: a later answer must not hide an eligible earlier answer. Poor = score 1–2; the threshold is not tuned. Existing earlier-study estimates use different populations and cannot be substituted for this result.

## Estimands and derivation

For group g let N_g be eligible orders, R_g observed ratings, P_g observed poor ratings and M_g=N_g−R_g. Available-case poor rate = P_g/R_g. Without a distributional assumption on unavailable binary ratings, the hypothetical full-rating rate lies in **[P_g/N_g, (P_g+M_g)/N_g]**. The late-minus-on-time range is **[P_L/N_L − (P_O+M_O)/N_O, (P_L+M_L)/N_L − P_O/N_O]**. These endpoints are attained by assigning every unavailable late/on-time rating opposite outcomes. They describe identification uncertainty conditional on the observed counts, **not a confidence interval** and not a bound on a causal effect.

For assumed unavailable-rating probabilities q_L and q_O, the pattern-mixture identity is **D(q_L,q_O)=(P_L+M_L q_L)/N_L − (P_O+M_O q_O)/N_O**. The full [0,1]×[0,1] grid explores assumptions rather than imputing truth. Setting each q to its group's observed poor rate reproduces the available-case contrast; that equality is algebra, not evidence of exchangeability. `review_tipping.csv` solves D=0 for q_O at each q_L. Thresholds outside [0,1] are deliberately retained as infeasible; missing q_O thresholds mean the on-time group has no unavailable ratings. The corner scenarios independently reproduce both sharp endpoints.

## Validation and uncertainty

An independent raw-order/customer/item pandas calculation reconstructs cohort membership and first-review selection; every group/window poor count, response count and denominator must equal the SQL output. One order/window row and an independently reconciled customer-cluster ledger prevent join fanout. Resampling retains all eligible orders and all three windows for each customer. Identical customer count ledgers are grouped and their frequencies drawn from a multinomial distribution: this has exactly the empirical customer-bootstrap distribution while reducing memory and computation. The fixed-seed {plan['bootstrap_iterations']:,}-replicate bootstrap reports **pointwise** intervals for the available-case contrast and, separately, each bound endpoint. Endpoint intervals in `review_summary.csv` are **not** a simultaneous confidence region for the partially identified set. Shared-cohort 7/30/90-day comparisons are sensitivity analyses, not independent experiments. No multiplicity-adjusted confirmation is asserted.

The data are an observational marketplace extract, not a probability sample. Bootstrap sampling stability cannot establish representativeness, capture completeness, missing-at-random, removal of confounding, or causal effects. Selection on delivered status and early enough deliveries changes the population. Customer expectations, seller behavior, product mix and delivery severity can affect both response and ratings. The outcome-definition assumption for nonrespondents remains untestable.

## Reproduction, sources and outputs

Run `python -m scripts.olist_review_selection --raw target/olist/raw --out target/olist/review-selection`, or build the complete bundle with `python -m scripts.build_research --schemas`. Raw inputs stay local; exports contain only aggregate counts, ranges, assumptions and checksums. Files: `review_groups.csv`, `review_summary.csv`, `review_sensitivity.csv`, `review_tipping.csv`, `review_availability.csv`, `review_selection_evidence.json`, this report and two figures. The bundle also includes the retrospective protocol and [query](review_selection.sql) so its links remain usable.

Source: [official Olist public extract]({SOURCE}); NEXUS transformations and data-derived artifacts retain [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The approach follows the principle of varying unverifiable missing-outcome assumptions explicitly; see [National Research Council, Principles and Methods of Sensitivity Analyses]({METHOD_SOURCE}) and [Sterne et al., 2009](https://pubmed.ncbi.nlm.nih.gov/19564179/). Those works motivate sensitivity analysis; this report derives its own binary-outcome arithmetic and makes no clinical-trial analogy to randomization. No external source supplies the numerical results above.

Decision: retain response coverage and missing-outcome sensitivity beside the observed association. Investigate review invitation/capture logs and non-delivery outcomes before intervention design. No profit, avoided-loss or revenue-uplift estimate is supported. This remains a non-commercial research portfolio with no recurring paid infrastructure. Native Power BI rendering, refresh and DAX execution remain unverified.
'''
    (out/'REVIEW_SELECTION.md').write_text(report,encoding='utf-8')


def run(raw:Path,out:Path):
    raw,out=raw.resolve(),out.resolve()
    if raw==out or raw in out.parents or out in raw.parents:raise ValueError('Raw/output directories must be separate')
    plan=json.loads(PROTOCOL.read_text(encoding='utf-8'))
    if plan['windows_days']!=[7,30,90] or plan['primary_window_days']!=30 or plan['poor_score_max']!=2:
        raise ValueError('Unsupported protocol; update implementation and tests explicitly')
    con=duckdb.connect();con.execute('set threads=1')
    try:quality=load_fact(con,raw);tables,bootstrap=analyze(con,plan)
    finally:con.close()
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items():table.to_csv(out/(name+'.csv'),index=False,float_format='%.12g',lineterminator='\n')
    (out/'olist_review_protocol.json').write_bytes(PROTOCOL.read_bytes())
    (out/'review_selection.sql').write_bytes((SQL/'review_selection.sql').read_bytes())
    present(tables,plan,out)
    evidence={'source':SOURCE,'source_kind':'historical_public_olist_review_selection','synthetic':False,
        'license':'CC-BY-NC-SA-4.0','quality':quality,'protocol':plan,'protocol_sha256':sha256(PROTOCOL),
        'implementation_sha256':sha256(Path(__file__)),'query_sha256':sha256(SQL/'review_selection.sql'),
        'order_fact_sql_sha256':sha256(SQL/'order_fact.sql'),'bootstrap':bootstrap,
        'summary':tables['review_summary'].to_dict('records'),'independent_raw_counts_reconciled':True,
        'aggregate_sha256':{name+'.csv':sha256(out/(name+'.csv')) for name in tables},
        'method_sources':[METHOD_SOURCE,'https://pubmed.ncbi.nlm.nih.gov/19564179/'],
        'causal_effect_identified':False,'missing_at_random_verified':False,'prospectively_preregistered':False}
    (out/'review_selection_evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return evidence['summary']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,default=ROOT/'target/olist/raw')
    p.add_argument('--out',type=Path,default=ROOT/'target/olist/review-selection')
    a=p.parse_args();print(json.dumps(run(a.raw,a.out),indent=2))
