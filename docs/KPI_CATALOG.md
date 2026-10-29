# Source-scoped KPI catalog

Authoritative definitions: [`contracts/metrics.json`](../contracts/metrics.json). Regenerate with `python -m scripts.metric_contracts`.

The registry documents implemented calculations and their interpretation. It does not certify source freshness, accounting recognition or DAX engine acceptance. Legacy SQL fields named `net_revenue` mean current completed item value in this project; their compatibility names do not establish net revenue.

Values, periods and denominators must never be added across E-Commerce, Greenweez, Olist or optional Google account measurements. Percentages require recomputed weighted numerators/denominators rather than averages of subgroup percentages.

## E-Commerce

### Completed item value

`ec_completed_value` · Unit: **source price units** · Grain: **order item**

SUM(revenue), with revenue populated only for current complete items.

Denominator: none. Null policy: Missing source amount is invalid input; returned items contribute zero.

Limit: Current status, not recognized book revenue, cash receipts or net sales. [Implementation](../models/marts/fct_order_marketing.sql).

### Period-distinct completed orders

`ec_completed_orders` · Unit: **orders** · Grain: **order within selected period**

COUNT(DISTINCT order_id) where at least one selected item is complete.

Denominator: none. Null policy: Zero only when an observed period contains no eligible orders.

Limit: Mixed completed/returned orders remain eligible; daily order-day totals are not period-distinct orders. [Implementation](../scripts/run_analysis.py).

### Completed order incidences by attributed channel

`ec_channel_order_incidence` · Unit: **order-channel incidences** · Grain: **order within each item-attributed channel**

Distinct completed order IDs separately within each channel/source group.

Denominator: none. Null policy: Zero only within an observed source scope with no eligible orders.

Limit: A multi-item order can appear in several attributed channels; channel counts must not be summed as period-distinct orders. [Implementation](../analyses/channel_performance.sql).

### Completed item value per completed order

`ec_completed_aov` · Unit: **source price units per order** · Grain: **selected order period**

Completed item value divided by period-distinct completed orders.

Denominator: Orders with at least one completed item in the same selected period. Null policy: Null when denominator is zero.

Limit: Do not use summed daily distinct orders or average item price as this denominator. [Implementation](../scripts/run_analysis.py).

### Returned item share

`ec_returned_share` · Unit: **percent of eligible item rows** · Grain: **order item**

100 * returned item count / (completed item count + returned item count).

Denominator: Only current complete or returned item rows. Null policy: Null without eligible item rows.

Limit: Not order return probability, cash refunded, product defect rate or a causal product-quality conclusion. [Implementation](../analyses/top_products.sql).

### Returned item value

`ec_returned_value` · Unit: **source price units** · Grain: **order item**

SUM(returned_revenue) for current returned rows.

Denominator: none. Null policy: Zero when no observed rows are returned.

Limit: Never subtract again from completed item value; refund settlement is unavailable. [Implementation](../models/marts/fct_order_marketing.sql).

### Known-cost completed product contribution

`ec_known_contribution` · Unit: **source price units** · Grain: **completed order item**

SUM(revenue - cost) on completed items with a non-null nonnegative unit cost.

Denominator: none. Null policy: Null if no completed item has an eligible cost.

Limit: Excludes unpriced rows, shipping, logistics and advertising; not net profit; observed catalog cost is not verified transaction-time COGS. [Implementation](../analyses/completed_product_contribution.sql).

### Known-cost product margin rate

`ec_known_margin_rate` · Unit: **percent of matched eligible value** · Grain: **known-cost completed item subset**

100 * known-cost product contribution / known-cost completed item value.

Denominator: Completed revenue from exactly the same known-cost item rows. Null policy: Null when matched revenue is zero.

Limit: Incomplete-cost rows cannot enter the denominator; display coverage alongside the rate. [Implementation](../analyses/completed_product_contribution.sql).

### Completed-value cost coverage

`ec_cost_coverage` · Unit: **percent of completed item value** · Grain: **completed order item**

100 * completed item value with eligible unit cost / all completed item value.

Denominator: All completed item value in the same selection. Null policy: Null without completed item value.

Limit: Coverage is not an estimate of missing costs or an uncertainty interval. [Implementation](../analyses/completed_product_contribution.sql).

### Historical sessions

`ec_sessions` · Unit: **session/user pairs** · Grain: **session_id plus user_id**

COUNT(*) from the tested session-grain mart.

Denominator: none. Null policy: Absence of a source is not zero traffic.

Limit: A session_id alone can belong to different users; separate from GA4 sessions. [Implementation](../models/marts/fct_marketing_web_performance.sql).

### Event session conversion

`ec_session_conversion` · Unit: **percent of session/user pairs** · Grain: **historical session/user pair**

100 * converted session rows / all eligible session rows.

Denominator: All observed session/user pairs in the same source and period. Null policy: Null without sessions.

Limit: Purchase events do not establish completed order settlement or causal marketing uplift. [Implementation](../analyses/channel_performance.sql).

## Greenweez

### Raw-branch sales value

`gw_revenue` · Unit: **source price units** · Grain: **sales line then order/day**

SUM(revenue) from raw-branch sales, reconciled to finance day.

Denominator: none. Null policy: Missing source amounts must remain a coverage issue.

Limit: Not combined with E-Commerce; no verified currency conversion or refund ledger adjustment. [Implementation](../integrations/greenweez/models/mart/finance/finance_days.sql).

### Model product contribution

`gw_product_contribution` · Unit: **source price units** · Grain: **priced sales line then order/day**

SUM(revenue - quantity * purchase_price); NULL line margins are excluded by SUM.

Denominator: none. Null policy: Missing line costs do not become verified zero costs.

Limit: Sales revenue includes unpriced lines even when their margin is omitted; coverage must be disclosed; observed product purchase prices are not verified historical COGS. [Implementation](../integrations/greenweez/models/intermediate/int_sales_margin.sql).

### Model operational contribution

`gw_operational_contribution` · Unit: **source price units** · Grain: **order then day**

Model product margin + shipping fee - logistics cost - shipping cost, using the existing zero policies for missing components.

Denominator: none. Null policy: Model-imputed zeros are flagged separately from complete source components.

Limit: Not audited operating profit; missing product/shipping components affect interpretation. [Implementation](../integrations/greenweez/models/intermediate/int_orders_operational.sql).

### Model contribution after advertising

`gw_after_ads` · Unit: **source price units** · Grain: **day including spend-only days**

Operational contribution minus advertising spend on the same date.

Denominator: none. Null policy: Full outer join preserves spend without orders.

Limit: Descriptive accounting identity, not advertising incrementality or net profit. [Implementation](../integrations/greenweez/models/mart/finance/finance_campaigns_day.sql).

### Complete-component order contribution subtotal

`gw_complete_components` · Unit: **source price units** · Grain: **eligible order records**

Operational contribution only for fully priced sales lines and complete nonnegative shipping components.

Denominator: none. Null policy: Null if no order satisfies both coverage conditions.

Limit: A selected-population subtotal, not a lower bound or a whole-business margin estimate; advertising is not allocated to this subset. [Implementation](../integrations/greenweez/analyses/cost_coverage.sql).

## Olist

### Delivered item GMV

`olist_gmv` · Unit: **source price units** · Grain: **public historical order item**

SUM(item price) on documented delivered positive-GMV purchase-window orders.

Denominator: none. Null policy: Orders without items are excluded and counted.

Limit: Independent public population; excludes freight and is not recognized net revenue. [Implementation](../scripts/advanced_olist.py).

### Observed monthly repeat-purchase retention

`olist_retention` · Unit: **fraction of original customer cohort** · Grain: **cohort month and age month**

Distinct active customer identities / original first-observed cohort size.

Denominator: Original cohort, constant across observed ages. Null policy: Observed inactivity is zero; future cells are null.

Limit: Retrospective delivered status and first-observed history; not lifetime acquisition or churn. [Implementation](../analytics/olist/cohorts.sql).

### Probability of another purchase day

`olist_repeat_day` · Unit: **fraction by elapsed day** · Grain: **first observed customer purchase day**

One minus Kaplan-Meier survival to a second distinct purchase day.

Denominator: Observed risk set accounting for administrative censoring. Null policy: No estimate after risk-set exhaustion; boundary confidence intervals are null.

Limit: Independent censoring is unverified; pointwise intervals are not simultaneous bands or churn forecasts. [Implementation](../scripts/olist_customer_portfolio.py).

### Comparable delivered-order late rate

`olist_delivery_rate` · Unit: **fraction of eligible delivered orders** · Grain: **matched January-July year/month/state**

Actual delivery calendar date later than promised calendar date / eligible delivered orders.

Denominator: Valid-date positive-GMV delivered orders in matched seven-month windows. Null policy: Missing/invalid dates are excluded and counted; no review-response filter.

Limit: Delivered-only retrospective endpoint; standardization and rate/mix components are not causal effects. [Implementation](../analytics/olist/delivery_operations.sql).
