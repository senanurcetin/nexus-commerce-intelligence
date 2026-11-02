# NEXUS: executive analytical readout

The portfolio demonstrates source reconciliation, uncertainty analysis and decision discipline. Its evidence supports targeted investigation and future validation. It does not establish current business performance, causal intervention benefits or deployable forecasts. Historical public Olist, private main-source observations and synthetic demo fixtures are separate populations; their orders, customers and totals must not be added.

## Decisions supported by the evidence

| Question | Recorded evidence | Decision now | Evidence required before a stronger decision |
| --- | --- | --- | --- |
| Can the main E-Commerce/Greenweez finance fields support a profit claim? | Private observation covers 180,450 item rows and 13,362 Greenweez orders; key/reconciliation checks pass, but origin, currency, refund meaning and transaction-time COGS remain unverified. | HOLD profit and refund-adjusted revenue claims. Retain source fields and complete-component coverage. | Authoritative field/unit definitions and historical cost/refund evidence; successful accounting reconciliation on the same population. |
| Does Olist support a recurring-customer revenue projection? | Weighted observed month-1 repeat is 0.48%; 90-day distinct-purchase-day KM repeat is 1.29% among 86,950 origins. These have different calendars and denominators. | Investigate repeat-purchase economics and follow-up feasibility; do not infer churn, CLV or customer intent. | A decision-specific acquisition/retention design, costs, complete follow-up and appropriate new data. No numeric ROI threshold can be inferred here. |
| Where should delivery investigation start? | Matched January–July delivered-order late rates are 3.63% in 2017 and 7.94% in 2018: +4.30 pp, cluster interval +3.94 to +4.67 pp. Common support retains 95.87%/94.60%. | Start record-level diagnosis in high-burden cells, retaining cancellation/non-delivery and geography guardrails. Burden is not a service-quality ranking. | Shipment/process timestamps and exposure denominators; prospective comparable evaluation before claiming an intervention effect. |
| Is the poor-rating contrast robust to unavailable ratings? | The 30-day available-case late-minus-on-time difference is +11.26 pp. Sharp hypothetical full-rating bounds are -5.44 to +69.44 pp across 68,448 mature orders. | The unrestricted missing-rating range includes zero; its direction is not identified under those assumptions. | Availability and timing evidence, justified missing-outcome assumptions and a causal design for intervention claims. Bounds are not confidence intervals. |
| Should the selected forecasting policy replace the baseline? | Over 30 held-out weeks, selector MAE is 41.19 versus 40.50 orders/day; paired four-week block improvement interval -4.67 to +3.06. Empirical week coverage is 93.33%, with mean band width 534.57 orders/day. | No demonstrated primary selector improvement. Retain the seasonal reference for future validation. Coverage alone is inadequate when bands are wide. | New future outcomes, reliable as-of availability and a predeclared operational loss/band-width budget. Do not select an apparent historical winner after inspecting all methods. |

The preceding decisions are proposed portfolio governance, not executed business actions. There is no measured incremental revenue, intervention ROI or business owner approval. All statistical results are retrospective and population-specific. Sampling intervals do not resolve missing-data identification, confounding or original-source authenticity.

## Acceptance sequence

1. Resolve core source provenance and finance semantics before interpreting margins as business profit. Unknown fields remain unknown; no refund subtraction or zero-cost imputation closes this gate.
2. Translate an actual decision into a declared loss, measurement population, observation schedule and acceptance budget before testing a new model or intervention. The historical extract cannot supply those business preferences.
3. Evaluate a frozen policy on genuinely new future data, with baseline, uncertainty, coverage and interval width together. Positive historical accuracy alone is insufficient.
4. Independently execute native BI refresh/DAX and presentation acceptance before claiming verified interactive delivery. Structural checks, TOM parsing and HTTP/MIME checks remain separate evidence.

No capital, paid resource, payment product or commercial launch is introduced. The project is an English-language analytical portfolio. Public Olist-derived findings retain CC BY-NC-SA 4.0 and [Olist attribution](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce); no endorsement is implied. Private source amounts are excluded.

## Evidence and maintenance

[Core-source acceptance](core-source/README.md) · [Base Olist study](advanced-analysis/REPORT.md) · [Repeat/portfolio study](advanced-analysis/CUSTOMER_PORTFOLIO.md) · [Delivery diagnosis](advanced-analysis/DELIVERY_OPERATIONS.md) · [Rating sensitivity](advanced-analysis/REVIEW_SELECTION.md) · [Forecast validation](advanced-analysis/FORECAST_VALIDATION.md) · [Reproduction](RESEARCH_REPRODUCIBILITY.md) · [Machine-readable decision evidence](executive_readout.json).

Regenerate with `python -m scripts.executive_readout`. This reads committed receipts only: it performs no cloud reads, inference service calls, browser actions or new statistical estimation. Canonical JSON input hashes make stale readouts detectable across Windows/Linux line endings and formatting; the implementation hash normalizes CRLF to LF. Unsupported source, duplicate primary windows, mixed Olist snapshots or changed financial acceptance policy are rejected.
