"""Execute and reconcile the four analytical SQL queries on synthetic dbt marts.

Produces aggregate CSVs, methodology, findings and NEXUS charts. No network,
browser, screen automation or cloud credentials. All results are synthetic.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import duckdb
from jinja2 import Environment, StrictUndefined

from scripts.ecommerce_marts_bridge import load_snapshot
from scripts.greenweez_bridge import load_snapshot as load_greenweez

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ("channel_performance", "conversion_funnel", "top_products", "channel_conversion_significance")


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def wilson(successes: int, trials: int) -> tuple[float, float] | None:
    """Descriptive 95% binomial interval, not a causal or independence claim."""
    if trials <= 0:
        return None
    z = 1.959963984540054
    p = successes / trials
    scale = 1 + z*z/trials
    center = (p + z*z/(2*trials)) / scale
    radius = z*math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials)) / scale
    return max(0., center-radius), min(1., center+radius)


def execute_analysis(con, path: Path) -> list[dict]:
    # These SELECT-only analysis templates use ref() and dbt.type_float().
    # Models themselves are built by dbt, not this lightweight query runner.
    known = {"fct_order_marketing", "fct_marketing_web_performance", "int_events_enriched"}
    def ref(name):
        if name not in known:
            raise ValueError("Unexpected analytical source reference")
        return '"analytics"."' + name + '"'
    template = Environment(undefined=StrictUndefined).from_string(path.read_text(encoding="utf-8-sig"))
    sql = template.render(ref=ref, dbt={"type_float": lambda: "double"})
    cursor = con.execute(sql)
    fields = [field[0] for field in cursor.description]
    values = cursor.fetchmany(10001)
    if len(values) > 10000:
        raise ValueError("Analysis exceeds aggregate output cap")
    return [dict(zip(fields, row)) for row in values]


def _json(value):
    if isinstance(value, (datetime,date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def greenweez_analysis(root: Path) -> tuple[list[dict], dict]:
    db=root/"integrations/greenweez/target/ci.duckdb"
    snapshot=load_greenweez(root/"target/greenweez_bridge/snapshot.json")
    if (not snapshot or snapshot["provenance"]!="synthetic_demo"
            or snapshot["source_sha256"]!=fingerprint(db)):
        raise ValueError("Re-export the current Greenweez synthetic database before analysis")
    with duckdb.connect(str(db),read_only=True) as con:
        cursor=con.execute("select date, transactions, revenue, operational_margin, ads_cost, ads_margin from analytics_finance.finance_campaigns_day order by date")
        fields=[field[0] for field in cursor.description]
        rows=[dict(zip(fields,row)) for row in cursor.fetchall()]
        raw=float(con.execute("select sum(revenue) from analytics.raw_gz_sales").fetchone()[0])
        missing_ship=con.execute("select count(*) from analytics.int_orders_operational where not has_ship_record").fetchone()[0]
        missing_product=con.execute("select count(*) from analytics.stg_raw__sales s left join analytics.stg_raw__product p on s.products_id=p.products_id where p.products_id is null").fetchone()[0]
    if not math.isclose(raw,sum(float(row["revenue"]) for row in rows),abs_tol=.1):
        raise ValueError("Greenweez raw-sales revenue does not reconcile to daily finance")
    if any(not math.isclose(float(row["ads_margin"]),float(row["operational_margin"])-float(row["ads_cost"]),abs_tol=.02) for row in rows):
        raise ValueError("Greenweez after-advertising margin identity failed")
    return rows,{"provenance":"synthetic_demo","source_sha256":snapshot["source_sha256"],
                 "daily_rows":len(rows),"revenue":round(raw,2),
                 "ads_cost":round(sum(float(row["ads_cost"]) for row in rows),2),
                 "margin_after_ads":round(sum(float(row["ads_margin"]) for row in rows),2),
                 "orders_missing_shipping":missing_ship,"sales_lines_missing_product":missing_product,
                 "raw_to_daily_revenue_reconciled":True,"margin_identity_reconciled":True}


def run(root: Path = ROOT, out: Path | None = None, *, charts: bool = True) -> dict:
    root = root.resolve()
    out = (out or root / "target/analysis").resolve()
    db = root / "target/ci.duckdb"
    snapshot = load_snapshot(root / "target/ecommerce_bridge/snapshot.json")
    if (not snapshot or snapshot["provenance"] != "synthetic_ci"
            or snapshot["source_sha256"] != fingerprint(db)):
        raise ValueError("Re-export the current synthetic dbt database before analysis")
    with duckdb.connect(str(db), read_only=True) as con:
        results = {name: execute_analysis(con, root / "analyses" / (name+".sql")) for name in QUERIES}
        # Independent controls use raw synthetic seeds, not the bridge helpers.
        raw = con.execute("select round(sum(case when lower(status)='complete' then sale_price else 0 end),2), count(distinct case when lower(status)='complete' then order_id end) from analytics.order_items").fetchone()
        fact = con.execute("select round(sum(revenue),2),count(distinct case when is_completed_order=1 then order_id end) from analytics.fct_order_marketing").fetchone()
        session_total = con.execute("select count(*), sum(is_converted) from analytics.fct_marketing_web_performance").fetchone()
        profile = {"order_lines": con.execute("select count(*) from analytics.order_items").fetchone()[0],
                   "events": con.execute("select count(*) from analytics.events").fetchone()[0],
                   "sessions": session_total[0], "converted_sessions": session_total[1],
                   "completed_orders_period_distinct": fact[1],
                   "completed_revenue": float(fact[0]),
                   "order_period": [str(v) for v in con.execute("select min(order_date),max(order_date) from analytics.fct_order_marketing").fetchone()]}
    if not math.isclose(float(raw[0]),float(fact[0]),abs_tol=.001) or raw[1] != fact[1]:
        raise ValueError("Raw seed to mart revenue/order reconciliation failed")
    channel_revenue = sum(float(row["net_revenue"]) for row in results["channel_performance"])
    if not math.isclose(channel_revenue,float(fact[0]),abs_tol=.01):
        raise ValueError("Channel result does not reconcile to source revenue")
    funnel = results["conversion_funnel"]
    if (sum(row["total_sessions"] for row in funnel) != session_total[0]
            or any(not 0<=row["purchase_sessions"]<=row["cart_sessions"]<=row["page_view_sessions"]<=row["total_sessions"] for row in funnel)):
        raise ValueError("Ordered funnel violates session conservation")
    stats = results["channel_conversion_significance"]
    for row in stats:
        interval = wilson(row["conversions"],row["sessions"])
        row["wilson_95_lower_pct"] = round(interval[0]*100,2) if interval else None
        row["wilson_95_upper_pct"] = round(interval[1]*100,2) if interval else None
    results["greenweez_finance"], greenweez = greenweez_analysis(root)
    supported = bool(stats) and all(row["chi_square_approximation_supported"] for row in stats)
    out.mkdir(parents=True,exist_ok=True)
    for name,rows in results.items():
        with (out/(name+".csv")).open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]) if rows else [])
            writer.writeheader();writer.writerows(rows)
    evidence={"schema_version":1,"generated_at_utc":datetime.now(timezone.utc).isoformat(),
              "provenance":"synthetic_ci","source_sha256":snapshot["source_sha256"],
              "profile":profile,"reconciliation":{"raw_to_mart_revenue":True,"raw_to_mart_orders":True,
              "channel_revenue":True,"funnel_sessions_and_ordering":True},
              "chi_square_approximation_supported":supported,
              "greenweez":greenweez,
              "queries":{name:{"sql":"analyses/"+name+".sql","rows":len(rows),
                       "sha256":hashlib.sha256((root/"analyses"/(name+".sql")).read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()} for name,rows in results.items() if name in QUERIES}}
    (out/"evidence.json").write_text(json.dumps(evidence,indent=2,default=_json)+"\n",encoding="utf-8")
    views=sum(row["page_view_sessions"] for row in funnel)
    carts=sum(row["cart_sessions"] for row in funnel)
    purchases=sum(row["purchase_sessions"] for row in funnel)
    cv=100*session_total[1]/session_total[0] if session_total[0] else 0
    report=f"""# NEXUS Commerce — analytical findings

**Scope:** reproducible synthetic dbt fixtures; demonstration of method, not actual business performance.
**Order window:** {profile['order_period'][0]} to {profile['order_period'][1]}.

## Questions and findings

1. **Does reported revenue reconcile?** {profile['completed_revenue']:,.2f} source units of completed-line revenue reconcile independently from raw order-item seeds to the order mart and channel result. There are {profile['completed_orders_period_distinct']} period-distinct completed orders. Returned item value is separate; no second subtraction is applied.
2. **Where does the measured journey narrow?** Of {profile['sessions']} session/user pairs, {views} contain a page view, {carts} proceed to a cart, and {purchases} subsequently purchase within the same session. Session IDs shared by different users stay separate; repeated events count once.
3. **Can we rank channel conversion confidently?** The session mart reports {cv:.2f}% event conversion. The chi-square expected-cell condition is {'satisfied' if supported else 'NOT satisfied'}. {'Evaluate the statistic and its assumptions before interpreting a difference.' if supported else 'Do not report a chi-square p-value or declare a winning channel from this tiny fixture.'} Descriptive Wilson intervals accompany each channel; repeated users may violate independent-trial assumptions.
4. **Which products warrant investigation?** Product revenue and eligible returned-item share are exported in `top_products.csv`. Small denominators preclude product-quality or causal claims; a return is not evidence of a defect.

## Greenweez finance — independent domain

Across {greenweez['daily_rows']} synthetic daily observations, {greenweez['revenue']:,.2f} source units of revenue reconcile from raw sales to the daily finance mart. Advertising cost is {greenweez['ads_cost']:,.2f}; reported contribution after advertising is {greenweez['margin_after_ads']:,.2f}. The identity `operational_margin - ads_cost = ads_margin` reconciles by day. These amounts are never added to E-Commerce revenue.

**Quality limits:** {greenweez['orders_missing_shipping']} orders lack a shipping record and {greenweez['sales_lines_missing_product']} sales lines lack a matching product. Missing components follow the existing model's zero/exclusion policies. The resulting contribution is a model output, not audited net profit; recover missing costs before a real profitability decision. `greenweez_finance.csv` exposes all daily aggregates. Refund worksheet units remain unverified and are not subtracted from this raw-sales branch.

## Visual exhibits

![Ordered same-session funnel](funnel.png)
![Channel conversion with descriptive Wilson intervals](channel-conversion.png)
![Completed product revenue](product-revenue.png)
![Greenweez daily contribution](greenweez-contribution.png)

These are generated analytical figures, not screenshots of Power BI or a live dashboard.

## Decision implications

Use this fixture to validate the pipeline and investigate counting assumptions. Do not reallocate a real marketing budget from these numbers. A real decision needs a source-qualified extract, sufficient independent observations, comparable periods and separately verified spend attribution. Greenweez finance, Olist notebooks and GA4 lab events represent separate populations.

## Reproduction and controls

`python -m scripts.run_analysis` executes the committed SELECT templates against the read-only DuckDB dbt marts. `evidence.json` records query hashes, the database fingerprint and independent reconciliation controls. The four CSVs expose the full aggregate results. No credentials, customer identifiers or raw event exports enter this report.

**Limits:** synthetic samples; current-status order facts; UTC-like DuckDB fixture dates versus Europe/Istanbul production mart dates; same-session closed funnel excludes cross-session journeys; first-touch attribution is descriptive; no causal marketing uplift, audited profit, cash refunds or real-time freshness is claimed.
"""
    (out/"REPORT.md").write_text(report,encoding="utf-8")
    if charts:
        draw(results,out)
    return evidence


def draw(results: dict, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"text.color":"#EDF2F8",
        "axes.labelcolor":"#B9C5CE","xtick.color":"#B9C5CE","ytick.color":"#B9C5CE",
        "axes.edgecolor":"#293449","figure.facecolor":"#0B0F19","axes.facecolor":"#0B0F19",
        "savefig.facecolor":"#0B0F19","axes.spines.top":False,"axes.spines.right":False})
    logo = Image.open(ROOT/"branding/nexus_official_transparent.png")
    def canvas(title,subtitle):
        fig,ax=plt.subplots(figsize=(12,6.5),dpi=170)
        fig.subplots_adjust(left=.12,right=.95,bottom=.21,top=.72)
        fig.text(.12,.85,title,fontsize=22,fontweight="bold")
        fig.text(.12,.79,subtitle,fontsize=10,color="#B9C5CE")
        brand=fig.add_axes([.76,.88,.19,.10]);brand.imshow(logo);brand.axis("off")
        fig.text(.12,.065,"SYNTHETIC dbt DEMONSTRATION  /  Not trading results",fontsize=9,color="#8F9BFF")
        return fig,ax
    funnel=results["conversion_funnel"]
    counts=[sum(row[key] for row in funnel) for key in ("page_view_sessions","cart_sessions","purchase_sessions")]
    fig,ax=canvas("The measured journey, in order.","Closed same-session funnel · distinct (session_id, user_id) pairs")
    bars=ax.barh(["Page view","Then cart","Then purchase"],counts,color=["#00E0FF","#4EA8FF","#8F9BFF"],height=.5)
    ax.invert_yaxis();ax.set_xlim(0,max(counts+[1])*1.2);ax.set_xlabel("Sessions")
    for bar,value in zip(bars,counts): ax.text(value+.15,bar.get_y()+bar.get_height()/2,str(value),va="center")
    fig.savefig(out/"funnel.png");plt.close(fig)
    rows=results["channel_conversion_significance"]
    fig,ax=canvas("Conversion differences need context.","Descriptive 95% Wilson intervals · small synthetic samples · not an experiment")
    for i,row in enumerate(rows):
        rate=100*row["conversions"]/row["sessions"]
        ax.errorbar(rate,i,xerr=[[rate-row["wilson_95_lower_pct"]],[row["wilson_95_upper_pct"]-rate]],fmt="o",color="#00E0FF",ecolor="#536D97",capsize=5)
    ax.set_yticks(range(len(rows)),[f"{r['traffic_source']} (n={r['sessions']})" for r in rows]);ax.invert_yaxis();ax.set_xlim(-2,102);ax.set_xticks([0,20,40,60,80,100]);ax.set_xlabel("Session conversion (%)");ax.grid(axis="x",alpha=.12)
    fig.savefig(out/"channel-conversion.png");plt.close(fig)
    rows=results["top_products"][:6]
    fig,ax=canvas("Where completed revenue concentrates.","Completed-line revenue only · source units · returned lines excluded")
    fig.subplots_adjust(left=.28)
    ax.barh([r["product_name"] for r in rows],[float(r["net_revenue"]) for r in rows],color="#4EA8FF",height=.55);ax.invert_yaxis();ax.set_xlabel("Source units");ax.grid(axis="x",alpha=.12)
    fig.savefig(out/"product-revenue.png");plt.close(fig)
    rows=results["greenweez_finance"]
    fig,ax=canvas("Contribution after advertising.","Greenweez only · modelled source units · incomplete cost coverage")
    dates=[row["date"] for row in rows]
    ax.plot(dates,[float(row["operational_margin"]) for row in rows],color="#4EA8FF",linewidth=1.6,label="Operational margin")
    ax.plot(dates,[float(row["ads_margin"]) for row in rows],color="#8F9BFF",linewidth=1.6,label="After advertising")
    ax.axhline(0,color="#536D97",linewidth=.7);ax.set_ylabel("Source units");ax.grid(axis="y",alpha=.12)
    ax.legend(facecolor="#0B0F19",edgecolor="#293449",labelcolor="#B9C5CE",fontsize=9)
    fig.autofmt_xdate(rotation=0);fig.savefig(out/"greenweez-contribution.png");plt.close(fig)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--no-charts",action="store_true")
    args=parser.parse_args()
    receipt=run(out=args.out,charts=not args.no_charts)
    print(json.dumps({"profile":receipt["profile"],"reconciliation":receipt["reconciliation"],
                      "chi_square_approximation_supported":receipt["chi_square_approximation_supported"]},indent=2))
