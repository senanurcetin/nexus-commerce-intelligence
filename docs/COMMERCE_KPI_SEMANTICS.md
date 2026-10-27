# Commerce KPI Semantics — Current-Status Ledger

**Status:** analytical SQL and source-scoped report definitions are executable locally. A portable PBIP is available; Desktop rendering and refresh remain unverified. [Delivery evidence](DELIVERY.md).

**Daily aggregates:** summing `completed_orders` or `returned_orders` from the daily bridge yields order-days. Do not label those sums period-distinct orders or use them for a true period AOV. `scripts.run_analysis` recomputes period-distinct counts from the item fact.

## Why a revision is required

The source mart `fct_order_marketing` is at **order-item grain** and is fully rebuilt to reflect mutable statuses. Each item has a current state such as `complete` or `returned`. It does not expose a full payment/refund transaction ledger. Thus:

- `revenue` = item sale price **only** if the current item status is `complete`; otherwise 0.
- `returned_revenue` = item sale price **only** if its current status is `returned`; otherwise 0. It represents **returned item value**, not verified cash refunded.
- Current-state **recognized revenue** = `SUM(revenue)`.
- Current-state **completed + returned item value** = `SUM(revenue) + SUM(returned_revenue)`, a descriptive gross proxy (not verified booked historical gross receipts).
- **Never** describe `SUM(revenue) - SUM(returned_revenue)` as net revenue. The source already removed returned items from `revenue`, so this would subtract them twice.
- These are current-status measures, not audited net sales, book revenue, net-of-discounts, tax-inclusive gross merchandise value, or a historical refund ledger.

## KPI contracts

| Metric | Grain | Definition | Explicit limitation |
| --- | --- | --- | --- |
| Orders | Unique order | `DISTINCTCOUNT(order_id)` | Includes any present order item/status |
| Completed orders | Unique order | `DISTINCTCOUNT(order_id)` where at least one item is `complete` | Orders with mixed completed/returned lines remain eligible |
| Recognized revenue | Item | `SUM(revenue)` | Current status only; no ledger accounting |
| AOV (completed orders) | Completed order | Recognized revenue / distinct orders with completed items | Not mean item selling price |
| Returned item share | Eligible item | count returned items / count completed-or-returned items | Not refunded-order rate or financial return ratio |
| Returned item value | Item | `SUM(returned_revenue)` | Not verified refund cash |
| Gross product contribution | Completed item | sum of (item recognized revenue - known unit product cost) | No shipping, advertising, logistics; missing cost excluded; not Greenweez margin |
| Sessions | Session key | `COUNT(*)` from session-grain `fct_marketing_web_performance` | `session_id` can be shared by different users |
| Conversion | Session key | converted sessions / total sessions | Event purchase flag; not necessarily completed order settlement |

The DAX documentation at `docs/dax-measures.md` now reflects these definitions. `ARPU` as currently authored is actually revenue per purchasing user, because the denominator is `DISTINCTCOUNT(user_id)` from the order fact; do not label it revenue per all active customers without deriving an eligible-user denominator.

## Analytical query changes

- `analyses/channel_performance.sql`: `net_revenue` now directly sums the current recognized `revenue` field; sessions count all session-grain rows instead of distinct `session_id`.
- `analyses/top_products.sql`: `gross_revenue` represents completed plus returned item value (descriptive only), while `net_revenue` represents current recognized revenue. Product returned-item share excludes statuses other than `complete` or `returned`.

## Acceptance before external claims

1. Compile all dbt analysis SQL in the CI pipeline and keep existing dbt tests passing.
2. Independently calculate completed revenue, returned item value, distinct orders and AOV from authorized BigQuery data and compare each reported metric.
3. Update the actual Power BI DAX measures in the **original editable report**. Check date slicers, fact relationships, conditional formatting, source labels and filter context.
4. Capture genuine current BI images only after a separately permitted Desktop refresh and numerical reconciliation.
5. Preserve segmentation: E-Commerce session/order metrics must not be joined to Olist, Greenweez or GA4 Search Console records based solely on date/channel labels.

These historical E-Commerce semantic corrections do not modify the isolated Greenweez dbt project under `integrations/greenweez/` or the Google measurement marts.
