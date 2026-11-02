"""Independent Olist repeat-day survival and product concentration extension.

Only aggregate ledgers leave DuckDB. Retrospective delivered status is preserved;
neither future customer behavior nor a market-wide concentration claim is inferred.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm

from scripts.advanced_olist import ROOT, SQL, SOURCE, load_fact, sha256


def kaplan_meier(ledger: pd.DataFrame, horizon: int=180) -> pd.DataFrame:
    """Grouped product-limit estimate; tied events precede tied censor removals.

    Greenwood log-log 95% limits are undefined at S=0/1 and emitted as null.
    No interval is invented beyond the final observed risk set.
    """
    required={'duration','event','customers'}
    if not required.issubset(ledger) or ledger.empty or horizon<0:
        raise ValueError('Nonempty duration/event/count ledger required')
    durations=ledger.duration.to_numpy(dtype=float)
    counts=ledger.customers.to_numpy(dtype=float)
    events=ledger.event.to_numpy()
    if not np.isfinite(durations).all() or (durations<0).any() or (durations%1).any() or not np.isfinite(counts).all() or (counts<=0).any() or (counts%1).any():
        raise ValueError('Durations and positive customer counts must be integers')
    if not np.isin(events,[True,False]).all():
        raise ValueError('Event indicator must be boolean')
    risk=int(counts.sum()); total=risk; survival=1.; greenwood=0.; rows=[]
    z=norm.ppf(.975)
    for day in range(horizon+1):
        d=int(counts[(durations==day)&events.astype(bool)].sum())
        c=int(counts[(durations==day)&~events.astype(bool)].sum())
        if risk==0:
            rows.append(dict(day=day,at_risk=0,events=0,censored=0,repeat_probability=None,ci_low=None,ci_high=None,risk_share=0.))
            continue
        survival*=1-d/risk
        if d and d<risk: greenwood+=d/(risk*(risk-d))
        low=high=None
        if 0<survival<1:
            loglog=np.log(-np.log(survival)); se=np.sqrt(greenwood)/abs(np.log(survival))
            low=1-np.exp(-np.exp(loglog-z*se))
            high=1-np.exp(-np.exp(loglog+z*se))
        rows.append(dict(day=day,at_risk=risk,events=d,censored=c,
                         repeat_probability=1-survival,ci_low=low,ci_high=high,risk_share=risk/total))
        risk-=d+c
    return pd.DataFrame(rows)


def repeat_analysis(con) -> tuple[dict,dict]:
    ledger=con.execute((SQL/'customer_lifetimes.sql').read_text(),{'cutoff':datetime(2018,8,1)}).df()
    if (ledger.duration>ledger.available_days).any():
        raise ValueError('Event follows administrative observation boundary')
    curve=kaplan_meier(ledger)
    horizons=[]
    for day in (30,60,90,180):
        mature=ledger[ledger.available_days>=day]
        denominator=int(mature.customers.sum())
        numerator=int(mature[mature.event & (mature.duration<=day)].customers.sum())
        row=curve[curve.day==day].iloc[0]
        horizons.append(dict(day=day,mature_customers=denominator,mature_repeats=numerator,
                             mature_repeat_rate=numerator/denominator if denominator else None,
                             km_repeat_probability=row.repeat_probability,at_risk=int(row.at_risk),
                             ci_low=row.ci_low,ci_high=row.ci_high))
    summary={'origins':int(ledger.customers.sum()),'observed_second_purchase_days':int(ledger[ledger.event].customers.sum()),
             'origin_start':'2017-01-01','last_observed_day':'2018-07-31',
             'horizon_days':180,'confidence_method':'Greenwood log-log pointwise 95%; null at survival boundaries',
             'censoring_assumption_verified':False,'repeat_day_90':horizons[2]}
    return {'repeat_ledger':ledger,'repeat_curve':curve,'repeat_horizons':pd.DataFrame(horizons)},summary


def product_analysis(con,raw: Path) -> tuple[dict,dict]:
    inputs={
        'details':('olist_order_items_dataset.csv','order_id, order_item_id, product_id, price'),
        'products':('olist_products_dataset.csv','product_id, product_category_name'),
        'translation':('product_category_name_translation.csv','product_category_name, product_category_name_english'),
    }
    receipts={}
    for table,(filename,columns) in inputs.items():
        path=raw/filename
        con.execute(f'create table product_{table} as select {columns} from read_csv_auto(?,sample_size=-1)',[str(path)])
        receipts[filename]={'sha256':sha256(path),'rows':con.execute(f'select count(*) from product_{table}').fetchone()[0]}
    for table,key in (('products','product_id'),('translation','product_category_name')):
        n,d,p=con.execute(f'select count(*),count(distinct {key}),count({key}) from product_{table}').fetchone()
        if n!=d or n!=p or not n: raise ValueError('Nonunique/null product dimension key: '+table)
    # Details must represent exactly the validated raw item keys and prices.
    mismatch=con.execute('''select count(*) from raw_items r full join product_details d using(order_id,order_item_id)
        where r.order_id is null or d.order_id is null or r.price is distinct from d.price''').fetchone()[0]
    if mismatch or con.execute('select count(*)-count(distinct (order_id,order_item_id)) from product_details').fetchone()[0]:
        raise ValueError('Product details do not match validated raw items')
    con.execute('''create table portfolio_lines as
        select d.order_id,d.product_id,d.price,f.purchased_at,
            coalesce(t.product_category_name_english,p.product_category_name,'Unknown category') as category,
            p.product_id is null as missing_product,
            p.product_category_name is null as missing_category,
            p.product_category_name is not null and t.product_category_name is null as untranslated_category
        from product_details d join order_fact f using(order_id)
        left join product_products p using(product_id)
        left join product_translation t using(product_category_name)
        where f.order_status='delivered' and f.purchased_at >= '2017-01-01'
          and f.purchased_at < '2018-08-01' and f.gmv>0''')
    total=con.execute('select sum(price),count(*) from portfolio_lines').fetchone()
    control=con.execute("select sum(gmv) from order_fact where order_status='delivered' and purchased_at >= '2017-01-01' and purchased_at < '2018-08-01' and gmv>0").fetchone()[0]
    if not np.isclose(total[0],control,atol=.005,rtol=0): raise ValueError('Product portfolio expanded or lost GMV')
    categories=con.execute('''select category,count(*) as item_lines,count(distinct order_id) as category_order_incidences,
        count(distinct product_id) as observed_products,sum(price) as gmv
        from portfolio_lines group by 1 order by gmv desc,category''').df()
    categories['gmv_share']=categories.gmv/total[0]
    categories['cumulative_share']=categories.gmv_share.cumsum()
    def concentration(frame):
        shares=frame.gmv.to_numpy()/frame.gmv.sum(); hhi=float(np.sum(shares**2))
        return {'observed_products':len(shares),'gmv':float(frame.gmv.sum()),'top_1_share':float(shares[:1].sum()),
                'top_10_share':float(shares[:10].sum()),'top_100_share':float(shares[:100].sum()),
                'hhi':hhi,'effective_product_count':1/hhi}
    products=con.execute('select product_id,sum(price) as gmv from portfolio_lines group by 1 order by gmv desc,product_id').df()
    if products.product_id.isna().any(): raise ValueError('Missing product identity prevents concentration calculation')
    overall=concentration(products)
    quarters=[]
    for quarter in con.execute("select distinct date_trunc('quarter',purchased_at)::date from portfolio_lines where purchased_at < '2018-07-01' order by 1").fetchall():
        frame=con.execute("select product_id,sum(price) as gmv from portfolio_lines where date_trunc('quarter',purchased_at)::date=? group by 1 order by gmv desc,product_id",[quarter[0]]).df()
        quarters.append({'quarter':str(quarter[0]),**concentration(frame)})
    coverage=dict(zip(('item_lines','missing_product_lines','missing_category_lines','untranslated_category_lines'),con.execute('select count(*),sum(missing_product::int),sum(missing_category::int),sum(untranslated_category::int) from portfolio_lines').fetchone()))
    return {'category_portfolio':categories,'product_concentration':pd.DataFrame([overall]),'quarter_concentration':pd.DataFrame(quarters)}, {'files':receipts,'coverage':coverage,**overall}


def present(tables,summary,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.facecolor':'#0B0F19','axes.facecolor':'#0B0F19','text.color':'#EDF2F8',
        'axes.labelcolor':'#B9C5CE','xtick.color':'#B9C5CE','ytick.color':'#B9C5CE','axes.edgecolor':'#334155','font.size':10})
    def save(fig,name,note,left=.12):
        fig.text(.05,.96,'NEXUS / OLIST CUSTOMER & PORTFOLIO',color='#00E0FF',fontsize=11)
        logo=fig.add_axes([.79,.91,.16,.07]);logo.imshow(plt.imread(ROOT/'branding/nexus_official_transparent.png'));logo.axis('off')
        fig.text(.05,.025,note,color='#B9C5CE',fontsize=9)
        fig.subplots_adjust(top=.84,bottom=.18,left=left,right=.95)
        fig.savefig(out/name,dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
    c=tables['repeat_curve'];h=tables['repeat_horizons']
    fig,ax=plt.subplots(figsize=(12,6))
    ax.step(c.day,c.repeat_probability*100,where='post',color='#00E0FF',label='Pooled Kaplan–Meier')
    ax.fill_between(c.day,c.ci_low*100,c.ci_high*100,step='post',alpha=.22,color='#00E0FF',label='Pointwise 95% interval')
    ax.scatter(h.day,h.mature_repeat_rate*100,color='#8F9BFF',s=45,label='Fully observed customers at each horizon')
    ax.set(xlabel='Days after first observed delivered-purchase day',ylabel='Second distinct purchase day (%)',title='Time to another purchase day: censoring and mature-cohort checks')
    ax.legend(facecolor='#0B0F19',labelcolor='#EDF2F8')
    save(fig,'repeat_purchase_survival.png','2017+ first-observed origins | Last observed day 2018-07-31 | Calendar populations differ; independent censoring unverified')
    c=tables['category_portfolio'].head(10).iloc[::-1]
    fig,ax=plt.subplots(figsize=(12,6));ax.barh(c.category,c.gmv_share*100,color='#8F9BFF')
    ax.set(xlabel='Share of delivered item GMV (%)',title='Category portfolio: ten largest GMV contributors')
    save(fig,'category_portfolio.png','January 2017–July 2018 | Source price units; freight excluded | Category-order incidences are not additive orders',left=.28)
    r=summary['repeat']['repeat_day_90'];p=summary['portfolio']
    report=f'''# Olist: repeat-purchase timing and portfolio concentration

Independent extension of the [controlled Olist study](REPORT.md), using the same delivered positive-item-GMV purchase window. Source: [Olist public data]({SOURCE}). All derived CSVs, figures and the data-containing Olist BI package retain [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). NEXUS authored the transformations; no endorsement by Olist is implied. E-Commerce and Greenweez populations remain separate.

## Findings and implications

- **{summary['repeat']['origins']:,} observed customer origins**, beginning January 2017. Pooled Kaplan–Meier probability of another distinct purchase day by day 90 is **{r['km_repeat_probability']:.2%}**, with pointwise Greenwood log-log 95% interval **{r['ci_low']:.2%}–{r['ci_high']:.2%}**. There are {r['at_risk']:,} customers at risk immediately before day 90. This is a historical descriptive estimate, not a forecast or churn probability.
- Among **{r['mature_customers']:,} customers with a full 90-day observation window**, {r['mature_repeats']:,} returned on another day within 90 days: **{r['mature_repeat_rate']:.2%}**. This maturity check describes an older calendar-origin population; differences from pooled KM do not by themselves establish bias or a trend.
- Across **{p['observed_products']:,} observed product IDs**, the top 10 contribute **{p['top_10_share']:.2%}** of item GMV and the top 100 contribute **{p['top_100_share']:.2%}**. Within-portfolio HHI is **{p['hhi']:.6f}**, equivalent to **{p['effective_product_count']:,.1f} equally weighted products**. This measures SKU value concentration within this extract, not market power or competition between firms.

Use repeat timing to frame follow-up experiments rather than assigning customer intent. Use category/value concentration to prioritize catalog investigation; the extract lacks stock availability, reliable cost, margin and demand exposure, so it does not justify delisting products or optimizing profit.

![Repeat-day timing with uncertainty](repeat_purchase_survival.png)

![Category value mix](category_portfolio.png)

## Method and observation contract

**Endpoint:** first purchase on a different calendar day after the customer's first observed delivered positive-GMV purchase. Multiple orders on one day count as one purchase day; the endpoint is not identical to second order, active-in-month retention or customer churn. Determine first observed purchase using the entire pre-cutoff extract, including 2016, then restrict origins to 2017+. Customer identity is `customer_unique_id`. Pre-extract and other-marketplace history are unobserved. Frozen delivered status makes this retrospective; it is not a historical as-of status reconstruction.

**Censoring:** last included purchase day is 2018-07-31; a customer originating that day has zero complete days of follow-up. Non-repeat durations end on that day, not on the excluded 2018-08-01 boundary. Tied events are counted before same-day censor removals. Kaplan–Meier uses the full grouped duration ledger when computing risk sets; published daily curves stop at 180 days. Greenwood log-log intervals are pointwise, not a simultaneous band. Intervals at survival 0/1 are undefined and remain null. Independent censoring and homogeneous calendar behavior are not established; administrative follow-up length depends on origin date. Rates among mature customers at 30/60/90/180 days are published as separate descriptive checks, each with its own eligible denominator. They are not interchangeable calendar cohorts.

**Portfolio:** product item values join to validated one-row-per-order facts; product and category-translation keys must be unique and non-null. Missing categories remain in an explicit unknown bucket, and untranslated labels retain the source language. Coverage counts are recorded. Whole-window item GMV must reconcile independently to the order fact within 0.005 source units. Category orders are incidences: an order containing two categories contributes to both, so category counts must not be summed as unique orders. Product IDs are used only inside local memory; public tables contain categories and concentration aggregates. Top-k is based on descending product GMV, with stable identity tie-breaks. HHI uses GMV shares squared; effective product count is its reciprocal. Quarterly comparisons include only complete quarters January 2017–June 2018; July's partial quarter is excluded.

## Reproduce

The four base files remain unchanged. Two further official CSVs are required: `olist_products_dataset.csv` and `product_category_name_translation.csv`; fetch with `python -m scripts.fetch_olist --products`. Inputs remain under ignored `target/olist/raw/`.

```powershell
python -m scripts.olist_customer_portfolio --out target/olist/extension
python -m unittest discover -s tests -p test_olist_customer_portfolio.py -v
python -m scripts.build_olist_powerbi --extension target/olist/extension
```

`extension_evidence.json` records source, query, implementation and aggregate hashes. Public outputs contain no customer, order or product identifiers. Native BI source/schema validation does not establish Desktop rendering, refresh or DAX execution. No browser, screen automation, paid resource or cloud query is needed.
'''
    (out/'CUSTOMER_PORTFOLIO.md').write_text(report,encoding='utf-8')


def run(raw: Path,out: Path):
    raw,out=raw.resolve(),out.resolve()
    if raw==out or raw in out.parents or out in raw.parents: raise ValueError('Raw/output directories must be separate')
    con=duckdb.connect();con.execute('set threads=1')
    try:
        quality=load_fact(con,raw)
        repeat,r=repeat_analysis(con)
        portfolio,p=product_analysis(con,raw)
    finally: con.close()
    tables={**repeat,**portfolio};summary={'repeat':r,'portfolio':p}
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items(): table.to_csv(out/(name+'.csv'),index=False,float_format='%.12g',lineterminator='\n')
    evidence={'source':SOURCE,'source_kind':'historical_public_olist_extension','license':'CC-BY-NC-SA-4.0',
        'quality':quality,'summary':summary,'implementation_sha256':sha256(Path(__file__)),
        'query_sha256':sha256(SQL/'customer_lifetimes.sql'),
        'order_fact_sql_sha256':sha256(SQL/'order_fact.sql'),
        'aggregate_sha256':{name+'.csv':sha256(out/(name+'.csv')) for name in tables},
        'desktop_render_verified':False,'dax_engine_executed':False}
    present(tables,summary,out)
    (out/'extension_evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=ROOT/'target/olist/raw')
    parser.add_argument('--out',type=Path,default=ROOT/'target/olist/extension')
    args=parser.parse_args();print(json.dumps(run(args.raw,args.out),indent=2))
