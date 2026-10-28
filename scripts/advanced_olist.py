"""Reproducible, aggregate-only Olist analysis. No cloud queries or UI automation.

Download the four named official CSVs separately with Kaggle CLI. Raw data stays
under ignored target/. This module never exports identifiers or review text.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import scipy
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "analytics/olist"
SOURCE = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
FILES = {
    "orders": ("olist_orders_dataset.csv", "order_id, customer_id, order_status, order_purchase_timestamp, order_delivered_customer_date, order_estimated_delivery_date"),
    "customers": ("olist_customers_dataset.csv", "customer_id, customer_unique_id, customer_state"),
    "items": ("olist_order_items_dataset.csv", "order_id, order_item_id, price, freight_value"),
    "reviews": ("olist_order_reviews_dataset.csv", "review_id, order_id, review_score, review_creation_date, review_answer_timestamp"),
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def shapley_change(before, after) -> np.ndarray:
    """Exact three-factor additive decomposition, averaging all six orderings."""
    a, b = np.asarray(before, dtype=float), np.asarray(after, dtype=float)
    if a.shape != (3,) or b.shape != (3,) or not np.isfinite([a, b]).all() or (np.array([a,b]) < 0).any():
        raise ValueError("Three finite nonnegative factors required")
    effect = np.zeros(3)
    for permutation in itertools.permutations(range(3)):
        values = a.copy()
        for i in permutation:
            previous = np.prod(values)
            values[i] = b[i]
            effect[i] += np.prod(values) - previous
    return effect / 6


def benjamini_hochberg(p_values) -> np.ndarray:
    """BH adjusted p-values in original order; the whole reported family is used."""
    p = np.asarray(p_values, dtype=float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("p-values must be finite and in [0,1]")
    if not len(p):
        return p
    order = np.argsort(p)
    adjusted = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p)+1))[::-1])[::-1]
    result = np.empty(len(p))
    result[order] = np.minimum(adjusted, 1)
    return result


def cluster_risk_difference(counts, *, iterations=1000, seed=20261027) -> dict:
    """Resample customers, retaining all their late/on-time reviewed orders.

    Columns: late poor, late total, on-time poor, on-time total.
    Percentile intervals describe sampling stability, not marketplace coverage.
    """
    counts = np.asarray(counts, dtype=float)
    if counts.ndim != 2 or counts.shape[1] != 4 or not len(counts) or not np.isfinite(counts).all() or (counts < 0).any():
        raise ValueError("Nonnegative four-column customer counts required")
    if (counts[:,0] > counts[:,1]).any() or (counts[:,2] > counts[:,3]).any():
        raise ValueError("Poor counts exceed their denominators")
    if iterations < 100:
        raise ValueError("At least 100 bootstrap replicates required")
    total = counts.sum(axis=0)
    if total[1] == 0 or total[3] == 0:
        raise ValueError("Both delivery groups required")
    estimate = total[0]/total[1] - total[2]/total[3]
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(iterations):
        values = counts[rng.integers(0, len(counts), len(counts))].sum(axis=0)
        if values[1] and values[3]:
            samples.append(values[0]/values[1] - values[2]/values[3])
    if len(samples) < .95 * iterations:
        raise ValueError("Bootstrap has insufficient two-group support")
    low, high = np.quantile(samples, [.025, .975])
    return {"risk_difference": float(estimate), "ci_low": float(low), "ci_high": float(high),
            "customers": len(counts), "iterations": iterations, "valid_replicates": len(samples), "seed": seed,
            "late_poor": int(total[0]), "late_orders": int(total[1]),
            "on_time_poor": int(total[2]), "on_time_orders": int(total[3])}


def load_fact(con, raw: Path) -> dict:
    receipt = {}
    for table, (filename, columns) in FILES.items():
        path = raw / filename
        # Explicit projection: review text, city and zip codes never enter tables.
        con.execute(f"create table raw_{table} as select {columns} from read_csv_auto(?, sample_size=-1)", [str(path)])
        receipt[filename] = {"sha256": sha256(path), "bytes": path.stat().st_size,
                             "rows": con.execute(f"select count(*) from raw_{table}").fetchone()[0]}
    for table, key in (("orders", "order_id"), ("customers", "customer_id")):
        n, distinct, present = con.execute(f"select count(*), count(distinct {key}), count({key}) from raw_{table}").fetchone()
        if not n or n != distinct or n != present:
            raise ValueError(f"Invalid {table} primary key")
    if con.execute("select count(*) from (select order_id, order_item_id from raw_items group by 1,2 having count(*)>1)").fetchone()[0]:
        raise ValueError("Duplicate order-item keys")
    if con.execute("select count(*) from raw_items where price is null or price<=0 or freight_value is null or freight_value<0").fetchone()[0]:
        raise ValueError("Invalid item value")
    if con.execute("select count(*) from raw_reviews where review_score is null or review_score not between 1 and 5").fetchone()[0]:
        raise ValueError("Invalid review score")
    for child, parent, key in (("items","orders","order_id"), ("reviews","orders","order_id"), ("orders","customers","customer_id")):
        if con.execute(f"select count(*) from raw_{child} c anti join raw_{parent} p using ({key})").fetchone()[0]:
            raise ValueError(f"Orphan rows in {child}")
    con.execute((SQL / "order_fact.sql").read_text(encoding="utf-8"))
    orders, distinct = con.execute("select count(*),count(distinct order_id) from order_fact").fetchone()
    if orders != receipt[FILES["orders"][0]]["rows"] or orders != distinct:
        raise ValueError("Order fact fanout")
    raw_value = con.execute("select sum(price) from raw_items").fetchone()[0]
    fact_value = con.execute("select sum(gmv) from order_fact").fetchone()[0]
    if not np.isclose(raw_value, fact_value, atol=.005, rtol=0):
        raise ValueError("Raw item to order GMV reconciliation failed")
    return {"files": receipt, "order_fact_rows": orders,
            "raw_item_value": raw_value, "fact_item_value": fact_value,
            "extra_review_rows_collapsed": con.execute("select count(*)-count(distinct order_id) from raw_reviews").fetchone()[0],
            "orders_without_items": con.execute("select count(*) from order_fact where items is null").fetchone()[0],
            "orders_without_customer_identity": con.execute("select count(*) from order_fact where customer_unique_id is null").fetchone()[0]}


def analyze(con, cutoff: datetime, *, iterations=1000) -> tuple[dict, dict]:
    parameters = {"cutoff": cutoff, "cohort_start": datetime(2017,1,1), "periods": 19}
    cohorts = con.execute((SQL / "cohorts.sql").read_text(encoding="utf-8"), parameters).df()
    observed=cohorts[cohorts.observable]
    if (observed.active > observed.customers).any() or observed.active.isna().any() or cohorts[~cohorts.observable].active.notna().any():
        raise ValueError("Cohort denominator or observation contract failed")
    segments = con.execute((SQL / "rfm.sql").read_text(encoding="utf-8"), {"cutoff": cutoff}).df()
    monthly = con.execute("""
        select date_trunc('month',purchased_at)::date as month, count(*) as orders,
               sum(items) as items, sum(gmv) as gmv, sum(freight) as freight
        from order_fact where order_status='delivered' and purchased_at >= '2017-01-01'
          and purchased_at < ? and gmv>0 group by 1 order by 1
    """, [cutoff]).df()
    monthly["items_per_order"] = monthly["items"] / monthly["orders"]
    monthly["value_per_item"] = monthly["gmv"] / monthly["items"]
    independent_gmv=con.execute("""select sum(i.price) from raw_items i
        join raw_orders o using(order_id) where o.order_status='delivered'
        and o.order_purchase_timestamp >= '2017-01-01' and o.order_purchase_timestamp < ?""",[cutoff]).fetchone()[0]
    if not np.isclose(monthly.gmv.sum(),independent_gmv,atol=.005,rtol=0):
        raise ValueError("Monthly GMV does not reconcile to independent raw-line calculation")
    decomposition = []
    for previous, current in zip(monthly.to_dict("records"), monthly.to_dict("records")[1:]):
        if (current["month"].year-previous["month"].year)*12+current["month"].month-previous["month"].month != 1:
            continue
        effects = shapley_change([previous[k] for k in ("orders","items_per_order","value_per_item")],
                                 [current[k] for k in ("orders","items_per_order","value_per_item")])
        change = current["gmv"]-previous["gmv"]
        if not np.isclose(effects.sum(), change, rtol=0, atol=.00001):
            raise ValueError("Shapley reconciliation failed")
        decomposition.append({"month": current["month"], "gmv_change": change,
                              **dict(zip(("order_volume","basket_size","unit_value"), effects))})
    con.execute("""create or replace table delivery_base as
        select f.*,
            delivered_at::date > estimated_at::date as late,
            review_score <= 2 as poor, date_trunc('month',purchased_at)::date as month
        from order_fact f
        where f.order_status='delivered' and purchased_at >= '2017-01-01'
          and purchased_at < ? and delivered_at >= purchased_at
          and estimated_at >= purchased_at::date and review_score is not null
          and customer_unique_id is not null and gmv>0
    """, [cutoff])
    con.execute("""create or replace table delivery_sample as
        select * from delivery_base where review_answer_timestamp >= delivered_at""")
    all_timing=con.execute("""select sum((late and poor)::int),sum(late::int),
        sum((not late and poor)::int),sum((not late)::int) from delivery_base""").fetchone()
    timing_sensitivity=dict(zip(("late_poor","late_orders","on_time_poor","on_time_orders"),all_timing))
    timing_sensitivity["risk_difference"]=all_timing[0]/all_timing[1]-all_timing[2]/all_timing[3]
    grouped = con.execute("""select sum((late and poor)::int),sum(late::int),
        sum((not late and poor)::int),sum((not late)::int)
        from delivery_sample group by customer_unique_id order by customer_unique_id""").fetchnumpy()
    bootstrap = cluster_risk_difference(np.column_stack(list(grouped.values())), iterations=iterations)
    strata = con.execute("""select month, late, count(*) as orders, sum(poor::int) as poor
        from delivery_sample group by 1,2 order by 1,2""").df()
    common = []
    for month, rows in strata.groupby("month"):
        if len(rows) == 2 and rows.orders.min() >= 30:
            late = rows[rows.late].iloc[0]
            ontime = rows[~rows.late].iloc[0]
            common.append({"month": month, "orders": int(rows.orders.sum()),
                           "risk_difference": late.poor/late.orders-ontime.poor/ontime.orders})
    standardized = float(np.average([x["risk_difference"] for x in common], weights=[x["orders"] for x in common])) if common else None
    # Secondary exploratory family: all states with >=30 orders in EACH group.
    states = con.execute("""select customer_state as state,
        sum((late and poor)::int) as late_poor, sum(late::int) as late_orders,
        sum((not late and poor)::int) as on_time_poor, sum((not late)::int) as on_time_orders
        from delivery_sample group by 1 order by 1""").df()
    states = states[(states.late_orders>=30) & (states.on_time_orders>=30)].copy()
    states["risk_difference"] = states.late_poor/states.late_orders-states.on_time_poor/states.on_time_orders
    states["p_value"] = [fisher_exact([[r.late_poor,r.late_orders-r.late_poor],
                                      [r.on_time_poor,r.on_time_orders-r.on_time_poor]]).pvalue
                         for r in states.itertuples()]
    states["bh_q_value"] = benjamini_hochberg(states.p_value)
    # M1 includes only cohorts that actually had a following observed month.
    m1 = cohorts[(cohorts.period==1) & cohorts.observable]
    eligible = con.execute("""select count(*),count(distinct customer_unique_id),sum(gmv)
        from order_fact where order_status='delivered' and purchased_at >= '2017-01-01'
        and purchased_at < ? and gmv>0""", [cutoff]).fetchone()
    asof = con.execute("""select count(*) from order_fact where order_status='delivered'
        and purchased_at < ? and gmv>0 and (delivered_at is null or delivered_at >= ? or delivered_at < purchased_at)""",[cutoff,cutoff]).fetchone()[0]
    delivery_coverage=con.execute("""select count(*),
        count(*) filter(where review_score is null),
        count(*) filter(where delivered_at is null or estimated_at is null),
        count(*) filter(where delivered_at < purchased_at or estimated_at < purchased_at::date),
        count(*) filter(where review_score is not null and (review_answer_timestamp is null or review_answer_timestamp < delivered_at))
        from order_fact where order_status='delivered' and purchased_at >= '2017-01-01'
        and purchased_at < ? and gmv>0""",[cutoff]).fetchone()
    summary = {"purchase_window": "[2017-01-01, " + cutoff.date().isoformat() + ")",
               "cutoff": cutoff.date().isoformat(), "orders": eligible[0], "customers": eligible[1],
               "gmv_source_units": eligible[2], "m1_cohorts": len(m1),
               "m1_customers": int(m1.customers.sum()), "m1_active": int(m1.active.sum()),
               "weighted_m1_retention": float(m1.active.sum()/m1.customers.sum()),
               "asof_delivery_excluded_orders": asof,
               "delivery_coverage_overlapping_exclusions": dict(zip(("delivered_positive_gmv_orders","no_review","missing_delivery_dates","invalid_chronology","missing_or_pre_delivery_answer"),delivery_coverage)),
               "independent_raw_window_item_value": independent_gmv,
               "delivery_association": bootstrap, "month_standardized_risk_difference": standardized,
               "all_review_timing_sensitivity": timing_sensitivity,
               "common_support_months": len(common), "state_fdr_family_size": len(states)}
    return {"cohorts": cohorts, "segments": segments, "monthly": monthly,
            "decomposition": pd.DataFrame(decomposition), "delivery_months": strata,
            "delivery_states": states, "delivery_common_support": pd.DataFrame(common)}, summary


def figures(tables: dict, summary: dict, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor":"#0B0F19", "axes.facecolor":"#0B0F19",
        "text.color":"#EDF2F8", "axes.labelcolor":"#B9C5CE", "xtick.color":"#B9C5CE",
        "ytick.color":"#B9C5CE", "axes.edgecolor":"#334155", "font.size":10})
    logo = plt.imread(ROOT / "branding/nexus_official_transparent.png")
    def save(fig, name, note, *, left=.12):
        fig.text(.05,.96,"NEXUS  /  OLIST RESEARCH",color="#00E0FF",fontsize=11)
        axlogo = fig.add_axes([.79,.905,.16,.075]); axlogo.imshow(logo); axlogo.axis("off")
        fig.text(.05,.025,note,color="#B9C5CE",fontsize=9)
        fig.subplots_adjust(top=.83,bottom=.18,left=left,right=.95)
        fig.savefig(out/name,dpi=160,facecolor=fig.get_facecolor()); plt.close(fig)
    data=tables["cohorts"].pivot(index="cohort",columns="period",values="retention")
    fig,ax=plt.subplots(figsize=(12,7))
    values=data.iloc[:,1:].to_numpy(dtype=float)*100
    image=ax.imshow(values,aspect="auto",vmin=0,vmax=max(1,float(np.nanmax(values))*1.05),cmap="Blues")
    ax.set(yticks=range(len(data)),yticklabels=[str(x.date())[:7] for x in data.index],
           xticks=range(len(data.columns)-1),xticklabels=data.columns[1:],xlabel="Months after first observed delivered purchase",
           title="Repeat purchase is rare; future observation cells remain blank")
    fig.colorbar(image,ax=ax,label="Monthly active customers / original cohort (%)")
    save(fig,"cohort_retention.png","Olist public extract | M0 omitted | 2017–July 2018 cohorts | Retrospective status; no lifetime-acquisition claim")
    data=tables["decomposition"]
    fig,ax=plt.subplots(figsize=(12,6))
    x=np.arange(len(data)); pos=np.zeros(len(data)); neg=pos.copy()
    for key,color,label in (("order_volume","#00E0FF","Order volume"),("basket_size","#8F9BFF","Items per order"),("unit_value","#6E55C6","Value per item")):
        y=data[key].to_numpy(); ax.bar(x,y,bottom=np.where(y>=0,pos,neg),label=label,color=color)
        pos+=np.maximum(y,0); neg+=np.minimum(y,0)
    ax.axhline(0,color="#B9C5CE",lw=.6)
    ax.set(xticks=x,xticklabels=data.month.dt.strftime("%Y-%m"),ylabel="Change in item GMV (source price units)",title="Monthly GMV change: exact three-factor Shapley decomposition")
    ax.tick_params(axis="x",rotation=55); ax.legend(facecolor="#0B0F19",labelcolor="#EDF2F8")
    save(fig,"gmv_decomposition.png","Six factor orderings averaged | Contributions reconcile to observed change | Accounting identity, not causal effects")
    data=tables["segments"].sort_values("customers")
    fig,ax=plt.subplots(figsize=(12,6))
    ax.barh(data.segment,data.customers,color=["#00E0FF" if x.startswith("Repeat") else "#8F9BFF" for x in data.segment])
    for y,n in enumerate(data.customers): ax.text(n+600,y,f"{n:,}",va="center",color="#EDF2F8")
    ax.set(xlim=(0,float(data.customers.max())*1.16),xlabel="Observed customers",title="As-of customer policies: most observed histories contain one purchase")
    save(fig,"customer_policies.png","As of 2018-08-01 | Recent = <=90 days | Repeat = 2+ orders | Pre-extract history and other marketplaces unobserved",left=.20)
    d=summary["delivery_association"]; a=summary["all_review_timing_sensitivity"]
    fig,ax=plt.subplots(figsize=(12,5))
    estimate=d["risk_difference"]*100
    ax.errorbar(estimate,1,xerr=[[estimate-d["ci_low"]*100],[d["ci_high"]*100-estimate]],fmt="o",capsize=6,color="#00E0FF",markersize=9)
    ax.scatter([a["risk_difference"]*100],[0],color="#8F9BFF",s=80)
    ax.set(yticks=[0,1],yticklabels=["Any review-answer timing","Post-delivery answers"],ylim=(-.6,1.6),xlim=(0,65),
           xlabel="Late minus on-time poor-review rate (percentage points)",title="Review timing changes the selected-sample delivery contrast")
    ax.text(a["risk_difference"]*100+1,.05,f"{a['risk_difference']*100:.2f} pp",color="#8F9BFF")
    ax.text(estimate+3,1.15,f"{estimate:.2f} pp; 95% interval {d['ci_low']*100:.2f}–{d['ci_high']*100:.2f}",color="#00E0FF")
    save(fig,"delivery_sensitivity.png",f"Post-delivery interval: {d['iterations']:,} customer-cluster bootstrap replicates | Other point descriptive | Neither contrast is causal",left=.24)


def write_report(tables: dict, evidence: dict, out: Path) -> None:
    s=evidence["summary"]; d=s["delivery_association"]
    text=f"""# Olist: repeat purchase, value drivers and delivery experience

This independent historical study uses the [official Olist public dataset]({SOURCE}), licensed CC BY-NC-SA 4.0. It is a non-commercial NEXUS portfolio analysis. It is never combined with E-Commerce, Greenweez or GA4 populations.

Olist-derived aggregate CSVs, figures and the data-containing Olist BI package retain [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). NEXUS authored the analytical transformations; Olist does not endorse this study. Software code follows the repository's separate license.

## Results and decisions

- **{s['orders']:,} delivered orders**, {s['customers']:,} observed customer identities and **{s['gmv_source_units']:,.2f} item GMV in source price units** in {s['purchase_window']}. Item GMV excludes freight, cancelled orders, refunds, fees and tax accounting; it is not net revenue or profit. Currency conversion is not performed.
- Across {s['m1_cohorts']} fully observable cohorts, {s['m1_active']:,} of {s['m1_customers']:,} original customers purchased again in month 1: **{s['weighted_m1_retention']:.2%}** (cohort-size weighted). This replaces the unverified 3–5% month-1 narrative in the historical SQL notebook. Investigate repeat-purchase economics before projecting recurring customer value; do not infer churn from this marketplace extract.
- Within the **post-delivery review-answer sample**, late orders had **{d['risk_difference']*100:.2f} percentage points** more poor reviews than on-time orders (customer-cluster bootstrap percentile 95% interval **{d['ci_low']*100:.2f}–{d['ci_high']*100:.2f} pp**, {d['iterations']} fixed-seed replicates). Late: {d['late_poor']:,}/{d['late_orders']:,} poor; on-time: {d['on_time_poor']:,}/{d['on_time_orders']:,}. Investigate delivery reliability; this observational contrast does not estimate the effect of a delivery intervention.
- **Review-timing sensitivity:** including reviewed orders regardless of whether the answer preceded actual delivery gives a crude difference of **{s['all_review_timing_sensitivity']['risk_difference']*100:.2f} pp**. The contrast depends strongly on the response-time restriction: pre-delivery complaints and later answers represent different selected populations. Neither is an unbiased intervention effect.
- The common-month standardized difference is **{s['month_standardized_risk_difference']*100:.2f} pp** across {s['common_support_months']} months with at least 30 orders in each exposure group. This is a descriptive sensitivity check without an adjusted confidence interval, not confounding control sufficient for causal inference.

![Retention by observed cohort](cohort_retention.png)

![Exact monthly GMV decomposition](gmv_decomposition.png)

![As-of customer segmentation policies](customer_policies.png)

![Review-timing sensitivity and uncertainty](delivery_sensitivity.png)

## Definitions fixed before interpretation

The first excluded purchase date is **{s['cutoff']}**. July 2018 is the last included purchase month; August and the sparse September/October tail are excluded conservatively. This is a frozen retrospective extract, not a currently operating business or a reconstructed historical database snapshot.

**Cohorts:** first observed delivered-purchase month across all pre-cutoff history, including 2016. Display starts January 2017. The denominator remains the original customer cohort; within-month multiple orders count once. All observable cohort/period pairs are generated, including true zeros. Cells outside the purchase observation window are null, never zero. Month 0 is 100% by construction. Customer identity is `customer_unique_id`, not the per-order `customer_id`. Missing pre-extract or other-marketplace history prevents a lifetime acquisition or customer churn claim. Frozen delivered status may include deliveries after cutoff, so this panel is retrospective, not an as-of forecast.

**RFM:** purchases and actual deliveries must both precede cutoff; impossible delivery chronology is excluded. {s['asof_delivery_excluded_orders']:,} otherwise eligible historical orders fail this delivery-time gate. Frequency is exact order count; monetary is item GMV. Four policy segments combine frequency 1 versus 2+ and recency <=90 versus >90 days. The 90-day threshold is an explicit demonstration policy, not an optimized business recommendation. Equal histories receive equal segments; no NTILE splits ties. No predicted CLV or invented customer intent is assigned. Earlier observed history is included, making this population different from the 2017+ monthly totals.

**GMV decomposition:** delivered purchase months from January 2017. GMV = orders × items/order × GMV/item. Each factor's contribution averages all six replacement orders (Shapley). Components reconcile to each adjacent month's exact observed change. Freight is reported separately; returns are not available as a refund ledger. This is accounting attribution, not an explanation of marketing causality or a forecast.

**Delivery/reviews:** one deterministic latest review per order; actual delivery is later than the estimated calendar date for the late flag. Poor = score 1–2. Require actual/estimated dates with valid purchase chronology and a review answer timestamp at or after actual delivery. Delivery and review outcomes can occur after the purchase cutoff because this is retrospective. Excluding pre-delivery/missing reviews creates selection bias; nonrespondents and pre-delivery complaints are outside this estimand. Bootstrap resamples customer identities with all their orders; it does not fix confounding, nonresponse, marketplace selection or review deduplication bias. Month standardization weights common-support months by pooled eligible orders. State-specific Fisher tests are exploratory: >=30 orders per exposure, all {s['state_fdr_family_size']} eligible states form one Benjamini–Hochberg family. Fisher's order-independence assumption is imperfect for repeat customers, so these q-values are screening diagnostics, not confirmatory evidence. No single state is selected as a winner.

## Grain and reproducibility

Raw order and customer keys must be unique/non-null; item `(order_id, order_item_id)` keys must be unique. Relationships, positive item prices, nonnegative freight and review scores are checked. Item values aggregate before review/customer joins. Latest review selection sorts answer time, creation time, review ID and score; {evidence['quality']['extra_review_rows_collapsed']:,} extra review rows are collapsed. Exact duplicate answers are equivalent for all retained fields. Order fact has {evidence['quality']['order_fact_rows']:,} rows. Raw item value reconciles to the entire order fact within 0.005 source units. {evidence['quality']['orders_without_items']:,} orders have no item rows; positive-GMV analyses exclude them.

CSV tables beside this report are aggregates only. `evidence.json` records full source-file SHA-256 hashes, row counts, query hashes, eligibility and statistical settings. No customer IDs, order IDs, addresses or review text are exported. Source files remain in ignored `target/olist/raw/`.

```powershell
# Requires an authenticated free Kaggle CLI (`pip install kaggle`).
# Downloads only these four official tables, keeping existing CSVs:
# olist_orders_dataset.csv, olist_customers_dataset.csv,
# olist_order_items_dataset.csv, olist_order_reviews_dataset.csv
python -m scripts.fetch_olist
python -m scripts.advanced_olist --raw target/olist/raw --out target/olist/analysis
python -m unittest discover -s tests -p 'test_advanced_olist.py' -v
# For the seven-page native report, also build the independent extension:
python -m scripts.fetch_olist --products
python -m scripts.olist_customer_portfolio --out target/olist/extension
python -m scripts.build_olist_powerbi --source target/olist/analysis --extension target/olist/extension
```

Native Power BI consumes these aggregate outputs in an independent portable project. JSON schema and TMDL parsing do not establish Desktop rendering, refresh or DAX execution. Generated figures are analytical plots, not BI screenshots. No browser, Playwright, screen automation, paid service or cloud query is needed.
"""
    (out/"REPORT.md").write_text(text,encoding="utf-8")


def run(raw: Path, out: Path, *, cutoff="2018-08-01", iterations=1000) -> dict:
    date=datetime.strptime(cutoff,"%Y-%m-%d")
    if date != datetime(2018,8,1):
        raise ValueError("Published report requires the documented 2018-08-01 cutoff")
    # Public analytical outputs must not overwrite the private raw source directory.
    raw, out=raw.resolve(),out.resolve()
    if out == raw or raw in out.parents or out in raw.parents:
        raise ValueError("Raw inputs and aggregate outputs must be separate directories")
    con=duckdb.connect()
    con.execute("set threads=1")  # Stable aggregate order and fixed-seed resampling.
    try:
        quality=load_fact(con,raw)
        tables,summary=analyze(con,date,iterations=iterations)
    finally:
        con.close()
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items():
        table.to_csv(out/(name+".csv"),index=False,float_format="%.10g",lineterminator="\n")
    evidence={"source":SOURCE,"license":"CC-BY-NC-SA-4.0","source_kind":"historical_public_olist",
              "synthetic":False,"source_version_note":"Content-addressed official CSVs; Kaggle version number not returned by CLI metadata.",
              "quality":quality,"summary":summary,
              "sql_sha256":{name:sha256(SQL/name) for name in ('cohorts.sql','order_fact.sql','rfm.sql')},
              "implementation_sha256":sha256(Path(__file__)),
              "runtime_versions":{"duckdb":duckdb.__version__,"numpy":np.__version__,"pandas":pd.__version__,"scipy":scipy.__version__},
              "export_sha256":{name+'.csv':sha256(out/(name+'.csv')) for name in tables},
              "desktop_render_verified":False,"dax_engine_executed":False}
    figures(tables,summary,out)
    write_report(tables,evidence,out)
    (out/"evidence.json").write_text(json.dumps(evidence,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return evidence


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=ROOT/"target/olist/raw")
    parser.add_argument("--out",type=Path,default=ROOT/"target/olist/analysis")
    args=parser.parse_args()
    result=run(args.raw,args.out)
    print(json.dumps(result["summary"],indent=2))
