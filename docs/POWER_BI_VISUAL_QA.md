# Power BI visual design and verification contract

The portable four-page synthetic and nine-page Olist reports are delivered as native PBIP/PBIR/TMDL. The separate private-source generator retains seven pages. Refer to [Power BI delivery](../powerbi/README.md), [artifact readiness](RELEASE_READINESS.md) and [current evidence](DELIVERY.md).

## Native design delivered on 2026-11-03

Both distributed reports retain the official transparent NEXUS logo, midnight surfaces and cyan/lavender accents. Their 1280×720 canvases reserve separate rows for the title/source context, native slicers and scope note, KPI cards, charts, and analytical qualifications. Fourteen research slicers and four synthetic-report slicers are editable native objects. Generated `visual_design.json` receipts document every page and keep native runtime verification false.

| Research page | Authored filter scope | Analytical protection |
| --- | --- | --- |
| Value and volume | Purchase month → charts and three cards | Delivered item GMV excludes freight; original source units |
| Observed cohorts | Cohort and age → matrix | Original cohort denominators; unobserved future cells and mixed-age totals blank |
| As-of policies | Policy → cards, ranking and lookup | Demonstration policies, not predicted CLV |
| GMV decomposition | Month → three-component native stack and exact lookup | Descriptive Shapley contributions; no causal interpretation |
| Delivery/reviews | Month and delivery group → rate lines and denominator table | Overall association and customer-cluster limits remain fixed; cards in percentage points |
| Repeat timing | Observation day → pooled step curve only | Dotted pointwise limits, at-risk tooltip; mature-horizon table retains different denominators |
| Product concentration | Category → GMV bars; quarter → concentration trend | Full-window cards stay fixed; category-order incidences are not additive orders |
| Comparable delivery | Month → year comparison; state → burden | Full-window rates/change stay fixed; uncertainty caption; burden is a count |
| Temporal forecasting | Day → plot; method → plot and full-evaluation cards | Four benchmark bars retained; 210-day metric window unchanged; no model refit or promotion |

The forecast table embeds 840 method/day evaluation rows. Observed orders use `MAX` at one-day grain rather than summing the four copies. Method-specific prediction and reference limits use `TREATAS` from the disconnected method selector. Reference bounds are dotted lavender; observations are solid light and the selected forecast is dashed cyan. The band has no guaranteed temporal coverage.

The synthetic report's Source Assurance page filters its source registry; each of the three analytical pages has its own native date slicer. No relationships join synthetic commerce to historical Olist or private sources. Chart selections are explicitly prevented from changing unrelated grains and filter controls. These are authored interaction contracts; actual Desktop behavior remains unverified.

## Reproducible checks

`tests/test_powerbi_visual_design.py` checks default method selection, distinct date/method targets, protected fixed intervals, number formats, step/bound styles, native decomposition bindings, all four methods, non-additive actuals, absence of relationships and byte-identical repeated generation. Microsoft JSON schema validation and TOM model parsing supplement these tests; neither executes DAX nor renders report visuals.

## Verified in code

- Official NEXUS logo is bundled and registered.
- Microsoft schema-bearing report files validate against their published schemas.
- Microsoft TOM deserializes both the four-table public and eight-table private TMDL models.
- Microsoft TOM also deserializes the sixteen-table Olist model. The actual distributed archives pass `scripts.release_audit`; the acceptance preflight recognizes their embedded editable PBIP projects.
- Field references resolve to known source-scoped columns/measures.
- Public source snapshots are synthetic; external source exports are rejected.
- Public Power Query embeds aggregates without machine-specific paths.
- Visual positions remain within the page and do not overlap.
- Completed revenue, returned value and session denominators retain distinct definitions.

## Outstanding rendered acceptance

No browser, Playwright or PC-screen automation is permitted in this pass. Therefore Desktop rendering, DAX engine results, refresh, responsive layout, slicer behavior and service publication remain unverified. Old screenshots were removed; the analytical figures in `docs/analysis/` are not substituted as BI screenshots.

When Desktop verification is separately performed, confirm all pages open, refresh the embedded data, compare measures to `docs/analysis/` under the same filters, inspect clipping/contrast and capture only genuine current report images.

## Attribution and financial semantics

`dim_user.signup_traffic_source` describes signup acquisition. `fct_marketing_web_performance.traffic_source` describes session first touch. Order attribution is a separate descriptive rule. Keep all three distinct.

The misleading historical CAC Proxy label was removed from the DAX reference: sessions per user do not measure monetary CAC. Returned-line value is not cash refunded, source units do not establish a currency, and Greenweez contribution with incomplete costs is not audited profit. Summed daily distinct orders are order-days, not period-distinct orders.
