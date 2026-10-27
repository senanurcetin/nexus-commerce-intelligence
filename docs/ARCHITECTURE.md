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

- Channel performance: source-scoped aggregations; missing session denominator is null.
- Ordered funnel: chronological page view, then cart, then purchase in one session/user pair; tie-break by timestamp, sequence and event ID.
- Conversion diagnostics: expected converted/non-converted counts, chi-square applicability flag, descriptive 95% Wilson intervals. Non-significance does not establish equivalence.
- Products: completed-line revenue and eligible returned-item share. Tiny denominators do not justify a product-quality conclusion.

The local analysis runner executes the SELECT templates against read-only dbt marts. Independent controls recompute revenue and period-distinct completed orders from the synthetic raw seeds and reconcile channel totals and funnel populations.

## Presentation and portability

The independent Olist pipeline in `analytics/olist/` and `scripts/advanced_olist.py` validates source keys and relationships, aggregates item/review many-sides before joins and reconciles both whole-extract and purchase-window item value. Raw files and identifiers remain under ignored `target/`; committed exports are aggregates with source/SQL fingerprints. Statistical settings and overlapping coverage exclusions are recorded in evidence. Cohort right-censoring, as-of delivered-purchase policies, exact six-ordering Shapley contributions, customer-cluster resampling and review-time sensitivity have explicit estimands and caveats in the [research report](advanced-analysis/REPORT.md).

Its five-page, six-table Power BI project is generated independently by `scripts.build_olist_powerbi` using reusable builder definitions. Aggregate file hashes are checked before embedding. Tables are disconnected intentionally: a selected month must not silently filter the fixed full-sample bootstrap interval. Retention blanks multi-period totals. This report carries the source's CC BY-NC-SA 4.0 attribution; it is separate from the four-page synthetic commerce package.

The public exporter accepts only `synthetic_ci` and `synthetic_demo` snapshots. It never publishes private account measurements. The static website performs filters and weighted ratios locally and makes no cloud query. Its daily order counts are order-days; arbitrary-window distinct orders require the analytical fact query.

The four-page PBIP embeds aggregate data in Power Query `#table` expressions. The private-source generator retains seven pages and local CSV inputs. Public packages visibly identify synthetic data on every page. Static field, geometry and Microsoft schema checks remain separate from Desktop/DAX/render acceptance.

## Brand

Official asset: `branding/nexus_official_transparent.png`, 1200 × 360. On 27 October 2026 its SHA-256 matched the owner's Drive `Logo/NEXUS_Identity_2_0/NEXUS_Official_Transparent_Logo.png`: `ebbdb363c523dcd88bcfa405be025e5b745419caaf57adb992b8ec1e85ed251e`.

NEXUS 2.0 palette: midnight `#0B0F19`, deep blue `#061524`, cyan `#00E0FF`, blue `#4EA8FF`, lavender `#8F9BFF`, violet `#6E55C6`, neutral `#B9C5CE`. Existing dashboard shades stay within the same visual family. No replacement logo is synthesized.

## Cost and scale

No recurring paid service, LLM dependency, billing or custom domain is introduced. Local analysis and static demonstration files can be reproduced offline after dependencies are installed. BigQuery is not queried by public page loads. Live warehouse refreshes remain explicit with row/byte limits and source-region handling. If traffic grows, inspect static-host bandwidth; if refresh grows, inspect actual warehouse quota before increasing frequency. No automated paid scaling is configured.
