# NEXUS Commerce — Power BI delivery

Run `python -m scripts.release_audit` to validate the actual distributed Power BI and website ZIPs. [Artifact readiness](../docs/RELEASE_READINESS.md) is separate from Desktop refresh/render and DAX execution. `--require-native` deliberately returns a failing exit code while those native gates remain unverified. `scripts.powerbi_acceptance` recognizes validated editable projects inside the shipped archives without upgrading native acceptance.

## Independent Olist research report

[NEXUS_Olist_Research.zip](NEXUS_Olist_Research.zip) contains `NEXUS_Olist_Research.pbip` and eight native pages: Value and Order Volume, Observed Cohorts (matrix), As-of Customer Policies, GMV Decomposition, Delivery/Reviews, Time to Another Purchase Day, Product Value Concentration and Comparable Delivery Experience. The official NEXUS logo and source qualifications appear on every page. All four inspectable reports, their aggregate CSVs and figures accompany the project.

Fourteen disconnected aggregate tables embed the [public Olist research](../docs/advanced-analysis/REPORT.md) and [customer/portfolio extension](../docs/advanced-analysis/CUSTOMER_PORTFOLIO.md). They intentionally do not relate to the synthetic commerce model. Retention uses original cohort denominators and is blank when multiple period ages share a context. The delivery confidence cards describe the fixed overall post-delivery-answer sample; selecting a month does not recompute its bootstrap interval. Page context states this explicitly. GMV is in original price units, excluding freight; it is not net revenue or profit.

Repeat timing plots the estimate and both pointwise Greenwood limits. Multiple day contexts return blank instead of adding probabilities. Mature-horizon comparisons use different eligible populations. Product cards show fixed full-window portfolio totals; selecting a quarter does not recompute those totals. Quarter comparisons omit July's partial quarter. Category order counts are incidences and must not be added as distinct orders. Base and extension raw-file fingerprints must match before report generation.

The operations page compares January–July 2017 and 2018 independently of review response. Its fixed cards are full-window rates and an absolute change in percentage points, while the month chart shows both years on the same seven-month axis. State bars show observed late-order burden, not a service-quality league table. The bundled `DELIVERY_OPERATIONS.md` provides the full-sample bootstrap interval, common-support coverage, standardized rates, exact rate/mix reconciliation, investigation priorities and guardrails. Month/state selections do not recalculate the fixed overall cards. The operations raw snapshot and order-fact SQL fingerprint must match the base study.

The fourth companion report, [`REVIEW_SELECTION.md`](../docs/advanced-analysis/REVIEW_SELECTION.md), comes with its retrospective protocol, query, five aggregate CSVs and two figures. It is not a new native page. It uses a different mature delivered-order cohort; its missing-rating ranges must not be interpreted as confidence intervals for the existing Delivery/Reviews page or as causal effects. The exporter rejects mismatched source snapshots and changed protocol/query or aggregate hashes.

```powershell
python -m scripts.build_olist_powerbi
python -m scripts.validate_powerbi_schema --project target/powerbi-olist/project
dotnet run --project scripts/powerbi-model-check/PowerBiModelCheck.csproj -- target/powerbi-olist/project/NEXUS_Olist_Research.SemanticModel/definition
```

For a complete rebuild from six local source CSVs: `python -m scripts.build_research --schemas`. This writes all analytical reports, CSVs, figures, a success receipt and native BI under `target/research/`.

The source-export hashes are checked before native generation. Raw identifiers, review text, cloud credentials and local CSV paths are excluded. Package provenance is in [olist-package-manifest.json](olist-package-manifest.json). Desktop rendering, refresh and DAX engine execution remain unverified.

## Synthetic portable portfolio report

Download [NEXUS_Commerce_Demo.zip](NEXUS_Commerce_Demo.zip), extract the complete folder and open `NEXUS_Commerce.pbip` in a current Power BI Desktop installation with PBIP/PBIR support. The report has four pages:

1. Source Assurance
2. Historical E-Commerce
3. E-Commerce Sessions
4. Greenweez Finance

The TMDL semantic model embeds source-scoped synthetic aggregates as Power Query `#table` expressions. No cloud sign-in, absolute CSV path, service credential or paid workspace is needed to supply its data. Every page identifies the data as synthetic demonstration data. Daily distinct order counts are labelled order-days.

Official NEXUS imagery is bundled under `StaticResources/RegisteredResources`. The theme uses midnight surfaces and cyan/lavender accents. Charts and KPI cards occupy separate non-overlapping rectangles.

## Rebuild

```powershell
python -m scripts.build_demo --deps
python -m scripts.build_public_powerbi
python -m scripts.validate_powerbi_schema
```

Output: `target/powerbi-public/project/`. Copy that entire directory when moving the project. The public builder rejects external/unverified snapshots before export and excludes GA4, source import audits and unrelated private data.

For an additional native parser check (.NET 9 SDK required):

```powershell
dotnet run --project scripts/powerbi-model-check/PowerBiModelCheck.csproj -- target/powerbi-public/project/NEXUS_Commerce.SemanticModel/definition
```

This uses Microsoft's pinned Analysis Services NuGet package and does not open Desktop or execute DAX.

## Private-source report

`python -m scripts.build_powerbi` generates the separate seven-page workspace report under `target/powerbi/`. It uses source-qualified local CSV inputs and preserves missing/invalid source states. See [PBIP pipeline](PBIP_PIPELINE.md) for its operational contract.

## Acceptance boundary

Microsoft's published JSON schemas validate the public report files. Microsoft TOM also deserializes both TMDL semantic models successfully. Local tests check field bindings, source separation, portability, visible provenance, page bounds and absence of overlapping visual rectangles.

**Not verified:** Power BI Desktop rendering, DAX engine execution, refresh, mobile layout or service publication. Neither screenshots nor a published Power BI URL are fabricated. No Playwright, browser session or PC screen is used in this pass. [Visual QA](../docs/POWER_BI_VISUAL_QA.md) remains a separate future acceptance step.

The [analytical figures](../docs/analysis/REPORT.md) in the README are generated directly from the SQL results and are not Power BI screenshots.
