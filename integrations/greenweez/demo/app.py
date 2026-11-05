"""Streamlit demo on top of the dbt marts (DuckDB).

Run `make demo` (builds the dbt project into target/demo.duckdb first), or:
    streamlit run demo/app.py
Set DEMO_DB to read a different DuckDB file (e.g. target/gsheet.duckdb for the fvt_gsheet mode) and
DEMO_DATA_LABEL to describe the data in the caption.
"""
import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(os.environ.get("DEMO_DB", Path(__file__).resolve().parent.parent / "target" / "demo.duckdb"))

DATA_LABEL = os.environ.get("DEMO_DATA_LABEL", "Synthetic demo data")

# Categorical slots 1-4 of the reference palette, assigned in fixed order.
BLUE, ORANGE, AQUA, YELLOW = "#80c2e5", "#edb16c", "#73d6ac", "#d9d58f"
SOURCE_COLORS = {"adwords": BLUE, "bing": ORANGE, "criteo": AQUA, "facebook": YELLOW}

st.set_page_config(page_title="Greenweez finance & campaigns", layout="wide")

# Purely visual presentation layer: calculations still read the real dbt marts.
# The demo mode defaults to synthetic input and is labeled on screen.
st.markdown(
    """
    <style>
      [data-testid="stApp"] {
        background:
          radial-gradient(circle at 90% 0%, rgba(58, 174, 119, .12), transparent 35%),
          linear-gradient(180deg, #0b2424, #0c1d23);
        color: #e9f8ee;
      }
      .block-container { max-width: 1400px; padding-top: 1.8rem; }
      [data-testid="stMetric"] {
        padding: 1.1rem;
        min-height: 128px;
        background: linear-gradient(145deg, #153a34, #122e31);
        border: 1px solid #366b5b;
        border-radius: 16px;
        box-shadow: 0 12px 27px rgba(3,20,22,.17);
      }
      [data-testid="stMetricLabel"] {
        color: #c3decf;
        font-size: .8rem;
        font-weight: 750;
        text-transform: uppercase;
        letter-spacing: .065em;
      }
      [data-testid="stMetricValue"] { color: #f0fff5; font-variant-numeric: tabular-nums; }
      [data-testid="stVegaLiteChart"], [data-testid="stDataFrame"] {
        border: 1px solid #315c55; border-radius: 15px; overflow: hidden;
      }
      [data-testid="stMarkdownContainer"] h1 {
        color: #f4fff6;
        letter-spacing: -.035em;
        font-size: clamp(2rem, 3.2vw, 3rem);
      }
      [data-testid="stMarkdownContainer"] h2,
      [data-testid="stMarkdownContainer"] h3 { color: #b9edce; }
      [data-testid="stAlert"] { border-radius: 13px; }
      .gw-eyebrow {
        display: inline-block;
        padding: 7px 13px;
        margin-bottom: .6rem;
        font-size: .73rem;
        letter-spacing: .13em;
        font-weight: 800;
        border-radius: 999px;
        background: #1d5142;
        border: 1px solid #4d9270;
        color: #c4f7d9;
      }
      @media(max-width:700px) {
        .block-container { padding-inline: .8rem; }
        [data-testid="stMetric"] { min-height: 110px; }
      }
    </style>
    """, unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load(sql: str, db_path: str, db_mtime: float) -> pd.DataFrame:
    # db_path and db_mtime are part of the cache key: a fresh `dbt build` or another database invalidates it.
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.sql(sql).df()
    finally:
        con.close()


def query(sql: str) -> pd.DataFrame:
    return load(sql, str(DB_PATH), DB_PATH.stat().st_mtime)


if not DB_PATH.exists():
    st.error(f"{DB_PATH} not found. Run `make build` first (dbt seed + build on the demo target).")
    st.stop()

daily = query("select * from analytics_finance.finance_campaigns_day order by date")
monthly = query("select * from analytics_finance.finance_campaigns_month order by datemonth")
marketing = query("select * from analytics_marketing.marketing_performance_month order by datemonth")

# The fvt_gsheet source mode has no per-source ads (no source, clicks or impressions), so the
# per-source models do not exist there. Detect that from the database instead of a flag.
existing = query("select table_schema, table_name from information_schema.tables")
existing_tables = set(zip(existing["table_schema"], existing["table_name"]))
has_sources = {("analytics", "int_campaigns"), ("analytics_marketing", "marketing_source_month")} <= existing_tables
has_refunds = ("analytics_finance", "finance_refunds_month") in existing_tables
if has_sources:
    spend = query(
        """
        select date_trunc('month', date_date)::date as datemonth, paid_source, sum(ads_cost) as ads_cost
        from analytics.int_campaigns group by 1, 2 order by 1, 2
        """
    )
    by_source = query("select * from analytics_marketing.marketing_source_month order by datemonth, paid_source")
daily["date"] = pd.to_datetime(daily["date"])

st.markdown('<span class="gw-eyebrow">FINANCE × CAMPAIGN INTELLIGENCE</span>', unsafe_allow_html=True)
st.title("Greenweez: finance and campaign profitability")
st.caption(
    f"{DATA_LABEL} served by the dbt marts `finance_campaigns_day` and `finance_campaigns_month`. "
    "Reporting logic, not marketing attribution."
)
if not has_sources:
    st.info(
        "Order-level Google Sheets export (`source_system: fvt_gsheet`): it has no per-source ads, clicks or "
        "impressions, so those sections are hidden. The sheet's `refund` column is shown separately below and "
        "is not subtracted from revenue or margins because its meaning is unverified."
    )

lo, hi = daily["date"].min().date(), daily["date"].max().date()
start, end = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
view = daily[(daily["date"].dt.date >= start) & (daily["date"].dt.date <= end)]

orders = int(view["transactions"].sum())
revenue = view["revenue"].sum()
op_margin = view["operational_margin"].sum()
ads_cost = view["ads_cost"].sum()
ads_margin = view["ads_margin"].sum()
cols = st.columns(5)
cols[0].metric("Revenue", f"{revenue:,.0f}")
cols[1].metric("Operational margin", f"{op_margin:,.0f}")
cols[2].metric("Ad spend", f"{ads_cost:,.0f}")
cols[3].metric("Margin after ads", f"{ads_margin:,.0f}")
cols[4].metric("Average basket", f"{revenue / orders:,.2f}" if orders else "n/a")


def line(df: pd.DataFrame, y: str, title: str, color: str, zero_rule: bool = False) -> alt.Chart:
    base = alt.Chart(df, title=title).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%b %d", tickCount=6)),
        y=alt.Y(f"{y}:Q", title=None),
        tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip(f"{y}:Q", format=",.2f", title=title)],
    )
    chart = base.mark_line(color=color, strokeWidth=2)
    if zero_rule:
        chart = chart + alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#8a8a86", strokeDash=[3, 3]).encode(y="y:Q")
    return chart.resolve_scale(x="shared").properties(height=220)


# One measure per chart: revenue and ad spend have different scales, so no dual axis.
left, right = st.columns(2)
left.altair_chart(line(view, "revenue", "Daily revenue", BLUE), width="stretch")
right.altair_chart(line(view, "ads_cost", "Daily ad spend", ORANGE), width="stretch")
st.altair_chart(
    line(view, "ads_margin", "Daily margin after ads (negative on days with spend but no orders)", AQUA, True),
    width="stretch",
)

st.subheader("Monthly margin waterfall")
month = st.selectbox("Month", monthly["datemonth"].tolist(), index=len(monthly) - 1, format_func=lambda d: f"{d:%B %Y}")
m = monthly[monthly["datemonth"] == month].iloc[0]
steps = [
    ("Revenue", m["revenue"], "Total"),
    ("Purchase cost", -m["purchase_cost"], "Cost"),
    ("Shipping fees", m["shipping_fee"], "Income"),
    ("Logistics cost", -m["log_cost"], "Cost"),
    ("Shipping cost", -m["ship_cost"], "Cost"),
    ("Ad spend", -m["ads_cost"], "Cost"),
    ("Margin after ads", m["ads_margin"], "Total"),
]
rows, running = [], 0.0
for label, value, kind in steps:
    if kind == "Total":
        rows.append({"step": label, "start": 0.0, "end": float(value), "kind": kind})
        running = float(value)
    else:
        rows.append({"step": label, "start": running, "end": running + float(value), "kind": kind})
        running += float(value)
wf = pd.DataFrame(rows)
wf["delta"] = wf["end"] - wf["start"]
wf["top"] = wf[["start", "end"]].max(axis=1)
order = [s[0] for s in steps]
kind_scale = alt.Scale(domain=["Total", "Cost", "Income"], range=[BLUE, ORANGE, AQUA])
bars = (
    alt.Chart(wf)
    .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=36)
    .encode(
        x=alt.X("step:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("start:Q", title=None),
        y2="end:Q",
        color=alt.Color("kind:N", scale=kind_scale, legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("step:N"), alt.Tooltip("delta:Q", format=",.0f", title="Change")],
    )
)
labels = (
    alt.Chart(wf)
    .mark_text(dy=-6, fontSize=11)
    .encode(x=alt.X("step:N", sort=order), y="top:Q", text=alt.Text("delta:Q", format=",.0f"))
)
st.altair_chart((bars + labels).properties(height=320), width="stretch")

if has_sources:
    st.subheader("Ad spend by source")
    spend["datemonth"] = pd.to_datetime(spend["datemonth"])
    spend_chart = (
        alt.Chart(spend)
        .mark_bar(stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("yearmonth(datemonth):O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("ads_cost:Q", title=None),
            color=alt.Color(
                "paid_source:N",
                scale=alt.Scale(domain=list(SOURCE_COLORS), range=list(SOURCE_COLORS.values())),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("yearmonth(datemonth):O", title="Month"),
                alt.Tooltip("paid_source:N", title="Source"),
                alt.Tooltip("ads_cost:Q", format=",.0f", title="Spend"),
            ],
        )
        .properties(height=260)
    )
    st.altair_chart(spend_chart, width="stretch")

st.subheader("Marketing efficiency")
if has_sources:
    st.caption(
        "ROAS is blended (all sources together): revenue is not attributed to a source or campaign, "
        "so CPC and CTR are the only per-source metrics."
    )
else:
    st.caption("ROAS is blended: revenue is not attributed to a source or campaign.")
marketing["datemonth"] = pd.to_datetime(marketing["datemonth"])
if has_sources:
    by_source["datemonth"] = pd.to_datetime(by_source["datemonth"])


def month_bars(df: pd.DataFrame, y: str, title: str, color: str, fmt: str) -> alt.Chart:
    return (
        alt.Chart(df, title=title)
        .mark_bar(color=color, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=36)
        .encode(
            x=alt.X("yearmonth(datemonth):O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{y}:Q", title=None),
            tooltip=[alt.Tooltip("yearmonth(datemonth):O", title="Month"), alt.Tooltip(f"{y}:Q", format=fmt, title=title)],
        )
        .properties(height=220)
    )


def source_lines(y: str, title: str, fmt: str) -> alt.Chart:
    return (
        alt.Chart(by_source, title=title)
        .mark_line(point=alt.OverlayMarkDef(size=60, stroke="white", strokeWidth=2), strokeWidth=2)
        .encode(
            x=alt.X("yearmonth(datemonth):O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{y}:Q", title=None, scale=alt.Scale(zero=False)),
            color=alt.Color(
                "paid_source:N",
                scale=alt.Scale(domain=list(SOURCE_COLORS), range=list(SOURCE_COLORS.values())),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("yearmonth(datemonth):O", title="Month"),
                alt.Tooltip("paid_source:N", title="Source"),
                alt.Tooltip(f"{y}:Q", format=fmt, title=title),
            ],
        )
        .properties(height=300)
    )


roas_col, margin_col = st.columns(2)
roas_col.altair_chart(month_bars(marketing, "roas", "Blended ROAS (revenue per 1 of ad spend)", BLUE, ",.2f"), width="stretch")
margin_col.altair_chart(month_bars(marketing, "margin_roas", "Operational margin per 1 of ad spend", AQUA, ",.2f"), width="stretch")
if has_sources:
    cpc_col, ctr_col = st.columns(2)
    cpc_col.altair_chart(source_lines("cpc", "Cost per click by source", ",.3f"), width="stretch")
    ctr_col.altair_chart(source_lines("ctr", "Click-through rate by source", ".2%"), width="stretch")

    with st.expander("Table view: marketing_source_month"):
        st.dataframe(by_source, width="stretch", hide_index=True)
else:
    st.caption("CPC and CTR need per-source clicks and impressions, which this data does not have.")

if has_refunds:
    refunds = query("select * from analytics_finance.finance_refunds_month order by datemonth")
    st.subheader("Refunds (unverified)")
    orders_total = int(refunds["orders"].sum())
    with_refund = int(refunds["orders_with_refund"].sum())
    above_revenue = int(refunds["orders_refund_above_revenue"].sum())
    refund_total = refunds["refund_amount_raw"].sum()
    refund_cols = st.columns(3)
    refund_cols[0].metric("Refund field total (as stored)", f"{refund_total:,.0f}")
    refund_cols[1].metric("Orders with positive refund field", f"{with_refund / orders_total:.0%}")
    refund_cols[2].metric("Orders where stored refund exceeds revenue", f"{above_revenue / orders_total:.0%}")
    st.warning("The refund field's meaning and unit are unverified. Net revenue after refunds is unavailable.")
    refunds = refunds.drop(columns=["refund_amount", "refund_to_revenue", "refund_unit_verified", "net_revenue_after_refunds"])
    with st.expander("Table view: finance_refunds_month"):
        st.dataframe(refunds, width="stretch", hide_index=True)

with st.expander("Table view: finance_campaigns_month"):
    st.dataframe(monthly, width="stretch", hide_index=True)
