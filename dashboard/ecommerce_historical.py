"""Independent historical E-Commerce dbt mart views for unified NEXUS dashboard.

Historical order/session marts never join with NEXUS Commerce Lab's GA4 test
events or the Greenweez finance business source.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.nexus_theme import style_chart, COLORS

from scripts.ecommerce_marts_bridge import load_snapshot


def historical_ecommerce_tab(path: Path) -> None:
    st.subheader("E-Commerce · Historical Orders & Sessions")
    st.caption(
        "Source: this repository's own fct_order_marketing and "
        "fct_marketing_web_performance dbt marts. These historical "
        "records are NOT produced by NEXUS Commerce Lab or Greenweez."
    )
    try:
        snap = load_snapshot(path)
    except ValueError as exc:
        st.error(str(exc))
        return
    if snap is None:
        st.info(
            "No validated E-Commerce historical DuckDB mart export yet. "
            "Build the root dbt models first; the NEXUS dashboard will not "
            "invent purchases or sessions."
        )
        st.code(
            "python -m scripts.ecommerce_marts_bridge "
            "--db target/ci.duckdb --provenance synthetic_ci",
            language="bash",
        )
        return
    if snap["provenance"] == "synthetic_ci":
        st.warning(
            "**Synthetic CI model data.** The figures below demonstrate dbt "
            "logic, not verified real TheLook orders or customer behavior."
        )
    else:
        st.warning(
            "**External E-Commerce snapshot · UNVERIFIED.** "
            "Independently reconcile BigQuery source counts/lineage, currency "
            "and business period before presenting these as real results."
        )
    st.caption(
        f"Source: {snap['source_system']} · Imported: {snap['generated_at_utc']} · "
        f"DB SHA256: {snap['source_sha256'][:16]}… · "
        "Historical data kept separate from Lab/Greenweez"
    )
    orders = pd.DataFrame(snap["tables"]["orders"])
    sessions = pd.DataFrame(snap["tables"]["sessions"])
    orders["date"] = pd.to_datetime(orders["date"])
    sessions["date"] = pd.to_datetime(sessions["date"])

    st.markdown("#### Historical completed-order line revenue")
    c1, c2, c3 = st.columns(3)
    c1.metric("Completed order-days · daily distinct IDs", f"{orders['completed_orders'].sum():,}")
    c2.metric("Completed line revenue · source units", f"{orders['completed_revenue'].sum():,.2f}")
    c3.metric("Returned order-days · daily distinct IDs", f"{orders['returned_orders'].sum():,}")
    fig = px.line(
        orders, x="date", y="completed_revenue", markers=True,
        color_discrete_sequence=[COLORS["cyan"]],
        title="Historical completed-order revenue by calendar date",
    )
    style_chart(fig, str(fig.layout.title.text or ""))
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Historical session events · separate web-analytics mart")
    cols = st.columns(3)
    cols[0].metric("Sessions · dbt historical", f"{sessions['sessions'].sum():,}")
    cols[1].metric("Converted sessions · has purchase event", f"{sessions['converted_sessions'].sum():,}")
    cols[2].metric("Page-view events · dbt historical", f"{sessions['page_view_events'].sum():,}")
    fig = px.bar(
        sessions, x="date", y="sessions", color_discrete_sequence=[COLORS["purple"]],
        title="Historical sessions · session date",
    )
    style_chart(fig, str(fig.layout.title.text or ""))
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Orders are deduplicated by order ID only within each calendar date "
        "(distinct completed orders in the historical order-item fact). "
        "Converted sessions are session-level event indicators. No artificial "
        "join or reconciliation between these independent mart grains is made."
    )
    with st.expander("Source-qualified daily historical marts"):
        a, b = st.tabs(["Orders", "Sessions"])
        with a:
            st.dataframe(orders, hide_index=True, width="stretch")
        with b:
            st.dataframe(sessions, hide_index=True, width="stretch")
