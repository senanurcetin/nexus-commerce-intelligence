# Delivery evidence

Updated 30 October 2026. Non-commercial, English-language NEXUS analytics case study. No Playwright, browser control or PC-screen use in this development pass.

## Implemented

- Added a validated 22-metric registry, generated KPI catalog and source coverage table for the core commerce and independent Olist domains. Source definitions include eligibility, grain, denominator, units, null policies and implementation links.
- Added known-cost completed product contribution with a matched revenue denominator and Greenweez product/shipping coverage. The synthetic fixture has 23 unpriced sales lines and 55 incomplete-component order records; source order/line/value controls reconcile without changing the finance models.
- Replaced obsolete row-level DAX examples with explicitly scoped reference measures. The static acceptance gate now checks a matched cost denominator rather than requiring a misleading acquisition-cost proxy name; Desktop/DAX acceptance remains separate.

- Corrected the closed chronological session/user funnel and missing channel reference.
- Preserved null conversion rates when the session denominator is absent.
- Removed historical significance claims; added expected-cell checks and descriptive Wilson intervals.
- Added executable analytical findings, aggregate CSVs, query/source fingerprints and independent reconciliation.
- Added independent Greenweez daily finance analysis and explicit missing-cost coverage.
- Built the NEXUS static presentation with domain/date controls and aggregate CSV export.
- Delivered a portable four-page Power BI source project with embedded synthetic data and provenance on every page.
- Fixed native report overlaps and machine-specific data-path dependence in public output.
- Corrected order-day labels across the public demo, native report and historical Streamlit tab.
- Consolidated obsolete plans, removed historical UI images and replaced documentation visuals with current generated analytical figures.
- Reconstructed the official 99,441-order Olist extract independently, with one order per fact row and source-file fingerprints. The principal purchase window contains 89,860 delivered orders.
- Added observation-aware repeat-purchase cohorts, tie-preserving as-of customer policies, exact Shapley GMV decomposition, 1,000-replicate customer-cluster bootstrap, month-standardization and a full exploratory state FDR family.
- Published review-timing sensitivity instead of presenting a selected-sample association as an intervention effect. Corrected the historical SQL notebook's unverified retention narrative; its code was not rerun.
- Delivered twelve current NEXUS analytical figures and a separate nine-page portable Olist Power BI package, with original source attribution and CC BY-NC-SA 4.0 data/report terms.
- Added a 86,950-origin customer duration ledger, distinct-purchase-day Kaplan–Meier estimates, pointwise Greenwood intervals and mature-horizon checks. Curves and intervals independently agree with SciPy's right-censored ECDF implementation.
- Added product/category mix and within-portfolio concentration over 30,015 observed product IDs, with 1,504 missing-category lines retained and 17 untranslated-category lines flagged. Product keys and IDs remain local; published results contain only aggregates.
- Added a delivery decision readout over 64,230 eligible orders in matched January–July windows, with independent raw denominator reconciliation, cluster uncertainty, common-support coverage and exact rate/mix decomposition. State burden priorities are paired with guardrails and a record-level investigation plan; no causal effect or revenue-loss claim is made.
- Added a single local `scripts.build_research` command for all five real-data studies, report assets and native BI. It was executed end to end with 72 official schema checks; failure fixtures reject raw/output overlap and stale success receipts. The archive contains the five reports and their aggregate evidence.

- Added the review-selection study over 68,448 mature delivered orders with a fixed retrospective protocol, first eligible raw-review policy, independent raw/pandas reconciliation, availability-reason ledger, 441 missing-rating scenarios and pointwise customer-cluster intervals. Thirty-day available-case difference is +11.26 pp; the sharp hypothetical full-rating range is −5.44 to +69.44 pp. The range includes zero and is not a causal effect or confidence interval. The fourth report and its protocol/query accompany the unchanged nine-page native BI project.

- Added a final audit of the actual three distributed ZIPs: pinned bytes/SHA-256, archive paths, native project/model bindings, page/table counts, logo bytes, report links, research source/aggregate/protocol consistency and current synthetic website sources. All three archives pass; the result is [portable artifact readiness](RELEASE_READINESS.md), not Desktop acceptance. Corruption, stale reports, unsupported native claims and source leakage are rejected by regression fixtures. Native-required mode returns a failure exit code while the independent engine/visual gates remain open.
- Corrected the Power BI acceptance preflight to recognize validated editable PBIP projects inside the delivered archives; it previously searched only expanded report files. No actual render, refresh or financial audit gate was promoted.

- Added the temporal forecasting study over 92,580 placed orders / 577 calendar days, independently reconciled from the raw order CSV. Thirty non-overlapping evaluation weeks compare three fixed candidates and a past-only selector. Future-outcome poisoning tests, independent ridge arithmetic, past-block interval calibration, MAE/RMSE/WAPE/MASE and paired moving-block uncertainty make prediction quality inspectable. The primary selector comparison does not demonstrate superiority. The new native forecasting page adds two disconnected tables; the research package now contains five reports, twelve figures, nine pages and sixteen tables.

## Source and brand evidence

The official transparent PNG was compared byte-for-byte with the owner's mounted Google Drive `Logo/NEXUS_Identity_2_0/` asset on 27 October. SHA-256: `ebbdb363c523dcd88bcfa405be025e5b745419caaf57adb992b8ec1e85ed251e`.

[Historical BigQuery OIDC run](https://github.com/senanurcetin/nexus-commerce-intelligence/actions/runs/39071051381): successful authentication, eight pinned schemas and 62 required fields; E-Commerce US, Greenweez EU. This is metadata evidence, not a new data refresh. The previous source preflight preserved its byte cap: Greenweez passed the dry-run; E-Commerce raw events exceeded the 100 MB cap and no rows were downloaded. The cap was not raised.

The four-page commerce report and web demo use only synthetic fixtures. Their results, lineage and controls are in [analytical evidence](analysis/evidence.json) and [findings](analysis/REPORT.md). The independent [Olist research](advanced-analysis/REPORT.md) uses four content-addressed core CSVs plus two product/category CSVs for the [customer/portfolio extension](advanced-analysis/CUSTOMER_PORTFOLIO.md); only aggregate results are published. No private warehouse rows or credentials are published.

## Verification scope

- Python unit/contract tests, 11 headless Streamlit AppTests and 16 Node tests passed. Exact current counts and commands: [machine-readable verification](verification.json).
- Full local rebuild: 10 E-Commerce models plus 59 model-level tests passed; Greenweez completed with 113 passed build nodes, four documented warnings and no errors.
- Five E-Commerce analytical SQL templates and the independent Greenweez raw-branch coverage query execute locally. Raw-to-mart value/order, funnel and known-cost population controls reconcile. Both dbt projects compile the new analysis within their own source scope.
- Greenweez raw-sales revenue reconciles to daily finance; daily contribution identities reconcile.
- Four-page public Power BI JSON validates against Microsoft's published schemas. Microsoft TOM successfully deserializes the public four-table and private eight-table TMDL models. Seven-page source/binding integrity is independently checked.
- Generated analytical figures are file artifacts, not screenshots of a live UI or Power BI.
- Olist: all-extract raw item value reconciles to the order fact, and the analytical purchase window reconciles independently to raw lines/orders. Cohort observation/denominator, policy ties, future delivery exclusion, many-side fanout, Shapley symmetry/additivity, fixed-seed bootstrap, BH adjustment, aggregate reconciliation and public export tamper tests pass without Kaggle access in CI.
- The nine-page Olist report validates 72 Microsoft schema-bearing artifacts; Microsoft TOM parses its sixteen-table semantic model. All twelve generated figures were inspected as local image files across the development passes. This does not establish BI rendering.

## Limits

Power BI Desktop rendering, DAX execution/refresh, mobile/browser interaction and live BI publication are not verified. Current instructions prohibit screen/browser testing, so these remain explicitly unclaimed. No commercial launch, payment integration, hosted job or paid resource was created. No manually dispatched CI or cloud refresh was run.

Greenweez fixtures contain unmatched product/shipping records and ambiguous refund worksheet units. Reconciliation of arithmetic does not make their financial interpretation audited. The public E-Commerce fixture is too small for a channel winner or a chi-square conclusion.

## Cost

Local open-source processing plus static files. No recurring infrastructure, LLM calls, custom domain or billing dependency. Public demo page loads do not query the warehouse. Private refresh remains explicit and quota-bounded.
