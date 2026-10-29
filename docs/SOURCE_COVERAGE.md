# Source coverage and analytical readiness

This table describes the recorded inputs of the public portfolio build. It does **not** check current cloud access or perform a new live refresh. Regenerate from explicit local evidence with `python -m scripts.metric_contracts`.

| Domain | Evidence and population | Current analytical boundary |
| --- | --- | --- |
| E-Commerce fixture | 15 synthetic item rows; 9 session/user pairs; 9 period-distinct completed orders; 2022-11-01 through 2022-11-15 | Reconciled pipeline demonstration. Too small for channel winners, causal uplift or business forecasts. |
| Greenweez raw-branch fixture | 3,110 synthetic sales lines; 1,226 order records; 90 finance dates | 55 order records have incomplete product/shipping components under the diagnostic policy; 1,546.84 source units of sales value lack eligible line costs. Arithmetic reconciliation is not an accounting audit. |
| Olist public history | 99,441 source orders; 89,860 delivered orders in [2017-01-01, 2018-08-01) | Separate non-commercial historical study. Source-file hashes and selection/observation limits are recorded; no current commerce performance claim. |
| Existing BigQuery integration | Repository configuration and historical keyless metadata evidence; no cloud rows read by this build | Current live row coverage/freshness is unverified here. Preserve existing byte caps and source-region separation; do not promote historical authentication evidence into a fresh extraction. |
| GA4 / GSC / Lighthouse / Commerce Lab | Independent optional collectors and consented test-event workflows | Not imported into this analytical denominator. Account measurements and lab events are not historical completed orders or sales. |

## Cost coverage acceptance

E-Commerce completed-value coverage is 100.00% in the current synthetic fixture. The product contribution rate uses only revenue paired with eligible costs. Unknown costs are never treated as free inventory.

Greenweez's current finance model retains all sales revenue while `SUM` excludes missing product-line margins; missing operational components follow its existing zero policies. The coverage diagnostic exposes those policies without changing them. A complete-component subtotal describes selected order records, not a whole-business margin estimate, lower bound or advertising-adjusted result. Google Sheets refund units remain a separately unverified contract.

## Gates before a real business conclusion

1. Confirm source population, extract freshness, period, currency and refund/cost interpretation.
2. Reconcile raw eligible rows, item/order grain and joins before aggregating metrics.
3. Publish missing-component coverage and use the same eligible rows for numerator and denominator.
4. Distinguish observational attribution/accounting identities from causal effects.
5. Apply a quota-bounded authorized source refresh before replacing synthetic labels with real-business labels.

Evidence: [commerce results](analysis/REPORT.md), [commerce receipt](analysis/evidence.json), [Olist study](advanced-analysis/REPORT.md), [BigQuery connection contract](GITHUB_ACTIONS_BIGQUERY_OIDC.md), [Google measurement contract](GOOGLE_MEASUREMENT_INTEGRATION.md). [KPI definitions](KPI_CATALOG.md).
