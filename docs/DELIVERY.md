# Delivery evidence

Updated 28 October 2026. Non-commercial, English-language NEXUS analytics case study. No Playwright, browser control or PC-screen use in this development pass.

## Implemented

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
- Delivered six current NEXUS analytical figures and a separate seven-page portable Olist Power BI package, with original source attribution and CC BY-NC-SA 4.0 data/report terms.
- Added a 86,950-origin customer duration ledger, distinct-purchase-day Kaplan–Meier estimates, pointwise Greenwood intervals and mature-horizon checks. Curves and intervals independently agree with SciPy's right-censored ECDF implementation.
- Added product/category mix and within-portfolio concentration over 30,015 observed product IDs, with 1,504 missing-category lines retained and 17 untranslated-category lines flagged. Product keys and IDs remain local; published results contain only aggregates.

## Source and brand evidence

The official transparent PNG was compared byte-for-byte with the owner's mounted Google Drive `Logo/NEXUS_Identity_2_0/` asset on 27 October. SHA-256: `ebbdb363c523dcd88bcfa405be025e5b745419caaf57adb992b8ec1e85ed251e`.

[Historical BigQuery OIDC run](https://github.com/senanurcetin/nexus-commerce-intelligence/actions/runs/39071051381): successful authentication, eight pinned schemas and 62 required fields; E-Commerce US, Greenweez EU. This is metadata evidence, not a new data refresh. The previous source preflight preserved its byte cap: Greenweez passed the dry-run; E-Commerce raw events exceeded the 100 MB cap and no rows were downloaded. The cap was not raised.

The four-page commerce report and web demo use only synthetic fixtures. Their results, lineage and controls are in [analytical evidence](analysis/evidence.json) and [findings](analysis/REPORT.md). The independent [Olist research](advanced-analysis/REPORT.md) uses four content-addressed core CSVs plus two product/category CSVs for the [customer/portfolio extension](advanced-analysis/CUSTOMER_PORTFOLIO.md); only aggregate results are published. No private warehouse rows or credentials are published.

## Verification scope

- Python unit/contract tests, 11 headless Streamlit AppTests and 16 Node tests passed. Exact current counts and commands: [machine-readable verification](verification.json).
- Full local rebuild: 10 E-Commerce models plus 59 model-level tests passed; Greenweez completed with 113 passed build nodes, four documented warnings and no errors.
- All four analytical SQL templates execute against the local dbt marts; raw-to-mart revenue/order and funnel controls reconcile.
- Greenweez raw-sales revenue reconciles to daily finance; daily contribution identities reconcile.
- Four-page public Power BI JSON validates against Microsoft's published schemas. Microsoft TOM successfully deserializes the public four-table and private eight-table TMDL models. Seven-page source/binding integrity is independently checked.
- Generated analytical figures are file artifacts, not screenshots of a live UI or Power BI.
- Olist: all-extract raw item value reconciles to the order fact, and the analytical purchase window reconciles independently to raw lines/orders. Cohort observation/denominator, policy ties, future delivery exclusion, many-side fanout, Shapley symmetry/additivity, fixed-seed bootstrap, BH adjustment, aggregate reconciliation and public export tamper tests pass without Kaggle access in CI.
- The seven-page Olist report validates 54 Microsoft schema-bearing artifacts; Microsoft TOM parses its eleven-table semantic model. All six generated figures were inspected as local image files across the two development passes. This does not establish BI rendering.

## Limits

Power BI Desktop rendering, DAX execution/refresh, mobile/browser interaction and live BI publication are not verified. Current instructions prohibit screen/browser testing, so these remain explicitly unclaimed. No commercial launch, payment integration, hosted job or paid resource was created. No manually dispatched CI or cloud refresh was run.

Greenweez fixtures contain unmatched product/shipping records and ambiguous refund worksheet units. Reconciliation of arithmetic does not make their financial interpretation audited. The public E-Commerce fixture is too small for a channel winner or a chi-square conclusion.

## Cost

Local open-source processing plus static files. No recurring infrastructure, LLM calls, custom domain or billing dependency. Public demo page loads do not query the warehouse. Private refresh remains explicit and quota-bounded.
