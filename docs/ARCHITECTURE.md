# Architecture and analytical contracts

## Independent source domains

| Domain | Raw grain | Presentation grain | Boundary |
| --- | --- | --- | --- |
| E-Commerce | Event, order item, product, user | Daily order-day and session aggregates | Current-status completed revenue; returns separate |
| Greenweez | Sales line or finance order; campaign/day | Daily/monthly finance and platform spend | Independent population, no inferred cross-merchant currency or attribution |
| Commerce Lab | Consented custom test event | Event/day | Test actions, never financial orders |
| GA4 / GSC / Lighthouse | Provider-specific | Property/site/device-specific | No inferred join to historical transactions |
| Olist | Public orders, order items, per-order customer mapping, reviews | Order fact → cohort/month, customer-policy segment, monthly value and delivery aggregates | Separate historical population; never unioned with dbt business sources |

## Historical model

`events → stg_events → int_events_enriched → fct_marketing_web_performance` creates one row per `(session_id, user_id)`. Session first-touch uses a deterministic ordering and keeps signup attribution separate.

`order_items → stg_order_items → int_orders_enriched → fct_order_marketing` retains order-item grain. The fact is rebuilt because source status can change without a trustworthy update timestamp. `revenue` includes complete lines only; `returned_revenue` is returned line value, not verified cash refunded.

The order mart and session mart are aggregated independently before comparison. Neither is joined to the other at raw grain for KPI calculation.

## Analytical layer

`contracts/metrics.json` is the machine-validated metric registry. Each entry names its source domain, grain, unit, denominator, null policy, implementation and limitations. `scripts.metric_contracts` rejects duplicate/incomplete entries and cross-domain/escaped implementation paths, then renders the KPI catalog and source coverage from explicit aggregate receipts. Cloud integrations remain unverified rather than being represented as zero rows or a fresh live extract.

- Channel performance: source-scoped aggregations; missing session denominator is null.
- Ordered funnel: chronological page view, then cart, then purchase in one session/user pair; tie-break by timestamp, sequence and event ID.
- Conversion diagnostics: expected converted/non-converted counts, chi-square applicability flag, descriptive 95% Wilson intervals. Non-significance does not establish equivalence.
- Products: completed-line revenue and eligible returned-item share. Tiny denominators do not justify a product-quality conclusion.

The local analysis runner executes the SELECT templates against read-only dbt marts. Independent controls recompute revenue and period-distinct completed orders from the synthetic raw seeds and reconcile channel totals and funnel populations.

The completed-product contribution query joins the item fact to the tested intermediate item key for cost coverage. Raw item/product controls detect join expansion and reconcile the known-cost revenue and contribution subset. Its margin denominator uses the same eligible rows as its numerator. The Greenweez raw-branch coverage query first aggregates sales lines into order/date records, then joins operational/shipping coverage. Order, line and revenue controls independently reconcile to raw seeds. Missing line margins and zero-policy operational components remain explicit; complete-component subtotals are selected populations, not financial bounds. The query is disabled for the Google Sheets source branch.

## Presentation and portability

The independent Olist pipeline in `analytics/olist/` and `scripts/advanced_olist.py` validates source keys and relationships, aggregates item/review many-sides before joins and reconciles both whole-extract and purchase-window item value. Raw files and identifiers remain under ignored `target/`; committed exports are aggregates with source/SQL fingerprints. Statistical settings and overlapping coverage exclusions are recorded in evidence. Cohort right-censoring, as-of delivered-purchase policies, exact six-ordering Shapley contributions, customer-cluster resampling and review-time sensitivity have explicit estimands and caveats in the [research report](advanced-analysis/REPORT.md).

Its nine-page, sixteen-table Power BI project is generated independently by `scripts.build_olist_powerbi` using reusable builder definitions. Aggregate file hashes and base/extension raw-file equality are checked before embedding. Tables are disconnected intentionally: a selected month must not silently filter the fixed full-sample bootstrap interval or portfolio totals. Retention and repeat probabilities blank multi-period totals. This report carries the source's CC BY-NC-SA 4.0 attribution; it is separate from the four-page synthetic commerce package.

`scripts.olist_customer_portfolio` reuses the validated order fact and adds an aggregate duration/event/administrative-follow-up ledger. Its endpoint is another distinct purchase day. It handles day-zero censoring, tied event/censor removal and risk-set exhaustion explicitly, then compares Kaplan–Meier estimates with mature-window direct rates. Two additional official product/category inputs have uniqueness checks; item-key/value equality and whole-window value reconciliation prevent dimension fanout. Unknown categories remain visible. Product concentration is descriptive within the extract; complete-quarter comparisons exclude the partial July quarter.

`scripts.olist_delivery_operations` compares the same seven purchase months in both years, without review-response filtering. An independent raw-order denominator check precedes customer-cluster uncertainty estimation. Month/state common support is selected by counts, and its coverage is published before symmetric Kitagawa rate/mix decomposition. Pooled standardization remains a distinct descriptive estimate with different weights. Priority states are selected by observed late-order burden and a minimum-volume policy, not significance or service-quality ranking.

`python -m scripts.build_research` executes all five analytical modules into one output folder, then builds a source-matched native package with reports, aggregate CSVs and figures. A failed stage removes any previous success receipt and prevents export. Input/output ancestor checks prevent overwriting the raw source directory. The command never downloads raw data, dispatches a cloud workflow or executes DAX. Optional official JSON schema validation is separate from native engine acceptance.

The public exporter accepts only `synthetic_ci` and `synthetic_demo` snapshots. It never publishes private account measurements. The static website performs filters and weighted ratios locally and makes no cloud query. Its daily order counts are order-days; arbitrary-window distinct orders require the analytical fact query.

The four-page PBIP embeds aggregate data in Power Query `#table` expressions. The private-source generator retains seven pages and local CSV inputs. Public packages visibly identify synthetic data on every page. Static field, geometry and Microsoft schema checks remain separate from Desktop/DAX/render acceptance.

## Brand

Official asset: `branding/nexus_official_transparent.png`, 1200 × 360. On 27 October 2026 its SHA-256 matched the owner's Drive `Logo/NEXUS_Identity_2_0/NEXUS_Official_Transparent_Logo.png`: `ebbdb363c523dcd88bcfa405be025e5b745419caaf57adb992b8ec1e85ed251e`.

NEXUS 2.0 palette: midnight `#0B0F19`, deep blue `#061524`, cyan `#00E0FF`, blue `#4EA8FF`, lavender `#8F9BFF`, violet `#6E55C6`, neutral `#B9C5CE`. Existing dashboard shades stay within the same visual family. No replacement logo is synthesized.

## Cost and scale

No recurring paid service, LLM dependency, billing or custom domain is introduced. Local analysis and static demonstration files can be reproduced offline after dependencies are installed. BigQuery is not queried by public page loads. Live warehouse refreshes remain explicit with row/byte limits and source-region handling. If traffic grows, inspect static-host bandwidth; if refresh grows, inspect actual warehouse quota before increasing frequency. No automated paid scaling is configured.

`contracts/olist_review_protocol.json` fixes the retrospective review-selection analysis. `scripts.olist_review_selection` rebuilds a common mature delivered cohort for 7/30/90-day windows, selects the first eligible raw review, and independently checks counts through pandas on raw tables. Binary-outcome sharp ranges and a pattern-mixture grid expose assumptions about unavailable ratings. Pointwise customer-cluster sampling intervals remain separate from identification ranges. Exact multinomial resampling of identical customer ledgers reduces computation without splitting customer histories. The fourth report, its protocol, query, five CSVs and two figures accompany the nine-page BI project; no additional native page or causal identification is claimed.

`contracts/olist_forecast_protocol.json` fixes the temporal benchmark before its evaluation. `scripts.olist_forecast` reconstructs all placed orders on a complete daily grid, independently reconciles a streaming raw CSV counter, then creates non-overlapping seven-day forecasts. Model selection, seasonal scaling and rolling maximum-error calibration use only completed prior data. Candidate ridge coefficients independently match augmented least squares; future-outcome poisoning tests leave earlier choices, predictions and bands unchanged. Paired moving-block inference evaluates the declared selector comparison without test-set tuning. ForecastDaily contains only evaluation dates for the selector, while ForecastMetrics holds fixed method-level results; neither table is related to delivered-value facts.
