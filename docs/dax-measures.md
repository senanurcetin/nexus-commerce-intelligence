# Historical row-level DAX reference

This page documents intended measures for the historical row-level E-Commerce star schema. It is separate from the generated portable aggregate reports, whose actual TMDL measures live in `scripts/build_powerbi.py` and `scripts/build_olist_powerbi.py`. Editable PBIP projects are available; Desktop rendering, refresh and DAX engine execution remain unverified.

The [KPI catalog](KPI_CATALOG.md) controls metric meaning. Required relationships for these reference formulas are a tested one-to-many `dim_products[product_id]` to `fct_order_marketing[product_id]`, with the appropriate date dimension/filter context. These relationships are not asserted to exist in the independent aggregate models.

## Counts and completed value

```dax
Completed Item Value = SUM(fct_order_marketing[revenue])

Period-Distinct Completed Orders =
CALCULATE(
    DISTINCTCOUNT(fct_order_marketing[order_id]),
    fct_order_marketing[is_completed_order] = 1
)

Completed Value per Completed Order =
DIVIDE([Completed Item Value], [Period-Distinct Completed Orders])

Revenue per Completed Purchasing User =
DIVIDE(
    [Completed Item Value],
    CALCULATE(
        DISTINCTCOUNT(fct_order_marketing[user_id]),
        fct_order_marketing[is_completed_order] = 1
    )
)
```

Completed value reflects current complete item status, not recognized accounting revenue. Mixed completed/returned orders remain eligible when they have a completed item. Period-distinct counts must be recomputed over the selected rows: neither daily order-days nor channel-order incidences can be added as a distinct-order denominator. Revenue per completed purchasing user is not ARPU across all active or registered users.

## Returns

```dax
Returned Item Value = SUM(fct_order_marketing[returned_revenue])

Returned Item Share =
DIVIDE(
    SUM(fct_order_marketing[is_returned_order]),
    SUM(fct_order_marketing[is_returned_order]) +
    SUM(fct_order_marketing[is_completed_order])
)
```

Format the share as a percentage. These are current returned item rows and item values, not settled refund cash or product defect probabilities. Never subtract returned item value again from completed item value.

## Product contribution with matched cost coverage

```dax
Known-Cost Completed Item Value =
IF(
    ISBLANK([Completed Item Value]), BLANK(),
    COALESCE(
        SUMX(
            FILTER(
                fct_order_marketing,
                fct_order_marketing[is_completed_order] = 1 &&
                NOT ISBLANK(RELATED(dim_products[cost])) &&
                RELATED(dim_products[cost]) >= 0
            ),
            fct_order_marketing[revenue]
        ), 0
    )
)

Known-Cost Product Contribution =
SUMX(
    FILTER(
        fct_order_marketing,
        fct_order_marketing[is_completed_order] = 1 &&
        NOT ISBLANK(RELATED(dim_products[cost])) &&
        RELATED(dim_products[cost]) >= 0
    ),
    fct_order_marketing[revenue] - RELATED(dim_products[cost])
)

Known-Cost Product Margin Rate =
DIVIDE([Known-Cost Product Contribution], [Known-Cost Completed Item Value])

Completed-Value Cost Coverage =
DIVIDE([Known-Cost Completed Item Value], [Completed Item Value])
```

The margin numerator and denominator use exactly the same eligible completed items. All-unpriced selections return no estimable contribution; a missing cost is not free inventory. Coverage can be zero when observed completed value exists without any eligible costs. The lookup uses the observed product catalog cost; transaction-time cost history is not established. Contribution excludes shipping, logistics and advertising and must not be presented as net profit. The portable synthetic report does not expose these row-level formulas; inspect [executable SQL](../analyses/completed_product_contribution.sql) and [cost coverage results](analysis/REPORT.md).

## Session metrics

```dax
Historical Sessions = COUNTROWS(fct_marketing_web_performance)

Historical Event Session Conversion =
DIVIDE(
    SUM(fct_marketing_web_performance[is_converted]),
    [Historical Sessions]
)
```

The session grain is `(session_id, user_id)`, not session ID alone. Event purchase conversion does not establish completed order settlement. Sessions per user do not measure customer acquisition cost, and revenue divided by sessions from an independently attributed fact is not verified session-level revenue attribution. Arbitrary composite performance scores are not part of the controlled KPI catalog.
