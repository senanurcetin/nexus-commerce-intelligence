# Project level and development assessment

Assessment date: 28 October 2026. Scope: repository, local dbt artifacts, executable analysis, reporting and source contracts. No browser, Playwright or PC-screen access.

## Level

The core commerce KPI registry now connects definitions to executable source-scoped implementations. Cost coverage is part of margin interpretation, with raw reconciliation and adversarial missing-cost/fanout fixtures. Live BigQuery row coverage remains an explicit open gate; synthetic examples are not promoted into real-business results.

**Advanced analytical methods implemented within a reproducible portfolio project; intermediate-to-advanced analytics engineering.** This is a qualitative assessment based on executable evidence, not a certification or an invented numeric score. Production operation, current business validity and native BI rendering remain separate acceptance boundaries.

| Dimension | Evidence | Remaining gap |
| --- | --- | --- |
| Data engineering | Two independently executable dbt projects, staging/intermediate/marts, adapter branches | Live source refresh and business reconciliation are separate acceptance steps |
| Data quality | Uniqueness, relationships, status/revenue tests and source-isolated adapters | Greenweez warning cases remain visible; they cannot be silently promoted to verified finance |
| Analytical correctness | Actual Olist order-grain reconstruction, censored cohort grid, as-of RFM, exact Shapley identity, customer-cluster bootstrap, timing sensitivity and exploratory FDR | Historical observational data cannot identify causal effects, current performance or population-wide churn |
| Reproducibility | Local dbt build; public Olist CSV checksums, executable SQL/statistics, independent raw reconciliation and aggregate results | Download official Olist inputs separately; CI tests methods on bounded adversarial fixtures and builds BI from committed aggregates |
| Communication | Questions → methods → findings → implications → limitations | No new live BI publication or UI screenshot evidence is claimed |
| Design | Official NEXUS logo; midnight, cyan, blue and lavender palette | Browser and Desktop render verification intentionally not performed |

The customer/portfolio extension adds an independently cross-checked survival estimator, explicit administrative observation boundaries, mature-window comparisons and within-portfolio concentration. This extends the analytical evidence; it does not turn historical purchase records into a validated churn or CLV prediction model. Product availability, unit costs and market-wide coverage remain unavailable.

The delivery readout demonstrates an analyst's decision workflow: choose comparable calendar windows, test denominator/grain controls, distinguish mix from within-group movement, publish common-support loss and uncertainty, prioritize record-level investigation and define guardrails. A Simpson-reversal fixture verifies that a worse aggregate rate can coexist with improvement inside every stratum. The single-command research build makes the analysis and report handoff reproducible.

The review-selection extension adds a recorded retrospective protocol, common follow-up across three windows, explicit rating-availability reasons, sharp partial-identification ranges, a pattern-mixture assumption grid and customer-cluster uncertainty. Exhaustive binary-outcome assignments independently verify the bound endpoints. This improves scientific transparency: neither a large sample nor a narrow available-case interval resolves selection or establishes a causal effect. The protocol is not prospective preregistration.

## Defects addressed

- Funnel referenced a channel column absent from its source model and collapsed sessions across different users. The corrected SQL takes session attribution from the session mart and requires chronological steps within `(session_id, user_id)`.
- Channel analysis treated an absent session denominator as a zero conversion rate. It now returns null.
- Historical chi-square figures appeared as current conclusions in SQL comments. Current-snapshot expected-cell checks and descriptive confidence intervals replace those claims.
- Summed daily distinct orders were labelled as period-unique orders/AOV. Public aggregates now use order-day terminology; the report computes true period-distinct orders from the fact.
- Power BI charts overlapped KPI cards, and local CSV paths were unsuitable for portable distribution. Layout coordinates were corrected and the public project embeds aggregate data.
- A Unix-specific GA4 authentication test failed on Windows. Both OS branches are now tested explicitly without changing permissions or requesting credentials.
- The historical SQL notebook's unsupported 3–5% month-1 retention narrative is superseded by a controlled 0.48% calculation across fully observable cohorts. Future periods remain null; repeated orders within a cohort month count once.
- Olist one-to-many items/reviews aggregate before joining. Native reporting embeds independent public aggregates without mixing them into E-Commerce or Greenweez totals.
- Review-timing selection changes the late-delivery contrast substantially. Both populations are reported, preventing a selected-sample contrast from becoming an unsupported intervention claim.

## Completion standard

A professional portfolio release needs inspectable results, tested grain and denominator definitions, transparent source limitations, concise navigation, approved branding and a reproducible native BI artifact. Code/schema acceptance does not establish Desktop rendering, financial audit or source freshness.

Final artifact acceptance is executable with `python -m scripts.release_audit`: the three distributed archives pass pinned integrity and content checks. This marks the offline portfolio artifacts as ready for delivery, while native Power BI refresh/render/DAX acceptance remains HOLD. A private live refresh is not a release prerequisite for the explicitly synthetic and historical portfolio; it is necessary only before making new live-business claims. Repository review/merge remains independent.

The forecasting extension demonstrates prediction with temporal discipline: an all-status placed-order target, genuine future-date evaluation, chronological method selection, past-only calibration, independently checked ridge arithmetic, leakage falsification tests and paired block uncertainty. It reports a negative primary result rather than tuning until a model wins. Coverage and interval sharpness are evaluated together; neither historical accuracy nor conformal-style calibration certifies deployment readiness.
