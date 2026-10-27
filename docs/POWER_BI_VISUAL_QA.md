# Power BI verification boundaries

The portable four-page report is delivered as native PBIP/PBIR/TMDL. The separate private-source generator retains seven pages. Refer to [Power BI delivery](../powerbi/README.md) and [current evidence](DELIVERY.md).

## Verified in code

- Official NEXUS logo is bundled and registered.
- Microsoft schema-bearing report files validate against their published schemas.
- Microsoft TOM deserializes both the four-table public and eight-table private TMDL models.
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

The historical CAC Proxy in the legacy DAX reference is sessions per user, not monetary CAC. Returned-line value is not cash refunded, source units do not establish a currency, and Greenweez contribution with incomplete costs is not audited profit. Summed daily distinct orders are order-days, not period-distinct orders.
