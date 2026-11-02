# NEXUS Commerce Intelligence Dashboard

## Official NEXUS logo and visual identity

The dashboard hero now renders the **exact owner-approved**
`branding/nexus_official_transparent.png` downloaded from the user's
Google Drive (`NEXUS_Official_Transparent_Logo.png`).
No synthesized/dummy logo, third-party remote asset or external font is used.
The existing source-first midnight/cyan/purple theme remains shared across tabs.

The logo is included in the repository so it works offline, on Windows, and
in local Streamlit AppTest. Verified Power BI report branding is separate:
see [PBIP Pipeline](../powerbi/PBIP_PIPELINE.md).

Status: **implemented as a local web application** with a source-verification gate and an **explicit user-triggered PageSpeed Insights API call**. It is **not deployed** and does not automatically poll Google, and does not represent historical E-Commerce/Olist/Greenweez sales as Google-measured events. No demo or synthetic business metrics are substituted for absent accounts.

## Original Greenweez source worksheets

A separate **Greenweez · Source Sheets** tab displays date-level observations
from the owner-authorized Google Sheets order and campaign workbooks. This is
not the Greenweez dbt finance mart and **never** certifies original turnover
as paid sales/revenue or cost as audited spend; no currency or attributed ROAS
is inferred. The schema rejects raw order IDs and campaign names.

Source and validation contract:
[Greenweez original Sheets evidence](../docs/GREENWEEZ_SOURCE_SHEETS_EVIDENCE.md).

## Unified evidence overview and source controls

The **Overview · Sources** page shows a source audit of all seven independent
data groups. It never treats a missing source as zero trading activity,
combines separate merchant revenue, or elevates a local synthetic/externally
unverified snapshot to certified financial data. The previously large
PageSpeed onboarding form starts collapsed so actual source coverage is
visible without scrolling.

Read-only verification:

~~~cmd
python -m scripts.nexus_workspace status
python -m scripts.nexus_workspace status --json
~~~

The source-safe importer can stage an E-Commerce dbt source and a Greenweez
dbt source in a single invocation; it validates both before publishing
either snapshot. See [workspace source audit and import](../docs/NEXUS_WORKSPACE_SOURCE_AUDIT.md).

## E-Commerce historical marts in the same dashboard

The dedicated **E-Commerce · Historical** tab reads the root E-Commerce project's
source-qualified DuckDB marts via an independent
[historical mart adapter](../docs/NEXUS_HISTORICAL_MART_BRIDGE.md). When no
snapshot exists it is blank with setup instructions, not fabricated business
KPI values. The root CI data are labelled synthetic; verified production
BigQuery marts and Power BI files still require reconciliation.

## One NEXUS workspace — E-Commerce and Greenweez

The original Google Measurement dashboard entrypoint is now the **unified** local NEXUS Commerce Intelligence interface. All original GA4, GSC, Lighthouse and owned Commerce Lab tabs remain independent, and new **Overview · Sources** / **Greenweez · Finance** tabs live in this same app. The finance bridge intentionally NEVER equates Greenweez customers, refunds or business revenue with TheLook or NEXUS test checkout events.

To import known Greenweez finance marts into E-Commerce on Windows, first build the embedded Greenweez dbt subproject's DuckDB outputs. Then run:

~~~cmd
cd /d C:\Users\MONSTER\E-commerce
python -m scripts.greenweez_bridge --db "C:\Users\MONSTER\E-commerce\integrations\greenweez\target\demo.duckdb" --provenance synthetic_demo
~~~

Use the optional flag `--provenance external_unverified` only for external snapshots, e.g., source-authored Greenweez BigQuery exports, which remain **unverified until an independent reconciliation**. No option can self-certify a file as actual business finance. Refresh the Streamlit page after importing. Source snapshot defaults to the gitignored `target/greenweez_bridge/snapshot.json`.

Full technical / presentation release conditions: [unified source plan](../docs/NEXUS_UNIFIED_COMMERCE_PLAN.md).

## Windows CMD · first real site audit (Python 3.11+)

The old screen's missing-manifest warning means there is no validated Google snapshot yet. It does **not** mean the app or GitHub installation failed. The dashboard now keeps all tabs accessible and includes a one-click **public PageSpeed audit**.

From a local checkout of this repo, update and launch:

~~~cmd
cd /d %USERPROFILE%\E-commerce
git pull origin main
python -m pip install -r dashboard\requirements.txt
python -m streamlit run dashboard\google_marketing_app.py
~~~

Open http://localhost:8501 . Under **GET STARTED · Run your first real PageSpeed audit**, the **Measurement target** menu now defaults to our controlled **NEXUS Commerce Lab** at `https://nexus-commerce-lab.vercel.app/`. You can instead select **Tricentis Demo Web Shop** or **nopCommerce Demo Store** for unrelated external benchmarks, or enter a custom HTTPS URL. Choose Mobile or Desktop and click **Run real PageSpeed audit**. The selector never triggers a network request until you submit. The URL is submitted to Google's PageSpeed Insights service on your explicit request only. The API may apply a quota or require an optional `GOOGLE_PAGESPEED_API_KEY`; no synthetic results are shown if Google denies the request.

The target selection itself makes **no API request**. Click the audit button to request actual Lighthouse metrics from Google; no third-party performance numbers are substituted if the PageSpeed API fails. The independent [FlawPilot health report](https://flawpilot.com/report/X88JSW) cannot be used as a Google Lighthouse report.

The app automatically writes a time-stamped JSON snapshot under gitignored `target/google_measurement/`, then produces a validated `marts/manifest.json` and source-specific CSV files. It refreshes the report. GA4 and GSC remain **Not connected** until their *own* read-only property credentials are configured.

For provenance, limitations and a safe learning route to the official GA4 demo account and BigQuery's **obfuscated Google Merchandise Store sample**, see [public ecommerce test stores and source separation](../docs/PUBLIC_ECOMMERCE_TEST_STORES.md). Neither external demo store is linked to the historical TheLook warehouse transactions.

### Manual collector alternative (no GA4/GSC property required)

~~~cmd
python scripts\google_measurement.py pagespeed --url https://YOUR-PUBLIC-SITE --strategy mobile
python scripts\google_measurement.py pagespeed --url https://YOUR-PUBLIC-SITE --strategy desktop
python scripts\google_measurement_marts.py
python -m streamlit run dashboard\google_marketing_app.py
~~~

Do not run the mart builder **before** collecting a real snapshot; it rightly rejects empty inputs.

### Alternative: real Chrome Lighthouse without the PageSpeed API

If Google's public PageSpeed Insights endpoint responds with HTTP 429 (rate limit), **do not invent performance numbers or use third-party quick-scan scores as Lighthouse**. Google Chrome's built-in Lighthouse panel offers an independent local laboratory measurement:

1. Open https://nexus-commerce-lab.vercel.app/ in Chrome.
2. Press **F12** → **Lighthouse** tab (via the DevTools menu if hidden).
3. Select **Mobile** and the desired audit categories; click **Analyze page load**.
4. Use **Export → JSON** to save the full Chrome Lighthouse report.
5. In the local NEXUS dashboard open **PSI · Lighthouse → Local Chrome Lighthouse**, then upload that JSON. It is parsed **in memory** and clearly labeled `local_lighthouse_cli`, not `pagespeed_insights_api`.
6. Repeat with **Desktop** for comparison. To persist files under the ignored local source directory, copy them to `target/google_measurement/local_lighthouse/` and refresh the page.

The loader checks Lighthouse version, device, URL, timestamp and full category scores, rejecting partial/mock reports. Metrics are Lighthouse **lab** values only. These local reports are distinct from both PageSpeed Insights API output and real-user CrUX field Core Web Vitals. They do not generate GA4 sessions or order revenue. Full JSON reports may contain page URLs and diagnostics; **never commit these raw reports to Git**.

### NEXUS Commerce Lab · separate GA4 event-reporting source

The new **Commerce Lab · Test Events** tab is intentionally empty until the **dedicated NEXUS Commerce Lab GA4 property** is configured and the read-only collector exports verified daily `lab_*` event counts. It never substitutes the legacy ToyStore stream `G-EL4EZ01CVH` or the personal portfolio property, and never labels a test checkout as an actual order or revenue.

Configuration and QA steps: [Commerce Lab independent GA4 event reporting](../docs/GA4_LAB_EVENT_REPORTING.md). The collector runs as `python -m scripts.lab_ga4_events --start YYYY-MM-DD --end YYYY-MM-DD` with a numeric, authorized `GA4_LAB_PROPERTY_ID`; the G-... Measurement ID alone cannot read Google Analytics reports. The source is kept in a separate gitignored JSON, outside the original GA4 acquisition/export contract.

### GA4 and Search Console later

The GA4 Data API needs a numeric GA4 Property ID and read-only account authorization; GSC needs the exact verified site property and authorized read-only API access. Follow `docs/GOOGLE_MEASUREMENT_INTEGRATION.md`. They are *separate optional connectors*; the PageSpeed workflow works independently.

For shared/public deployment, an authentication and data-exposure review is required before enabling on-demand API use. This is currently a **local-only** personal dashboard, not a hosted public scanning service.

### Pages

| Dashboard view | Real source | Supported metrics | Explicit non-features |
| --- | --- | --- | --- |
| GA4 · Acquisition | GA4 Data API | sessions, engaged sessions, engagement ratio, e-commerce purchases, purchase revenue (GA4 property currency), daily source trends | Active users are not summed across dates/channels; neither validated orders nor Ads spend is inferred |
| GSC · Search | GSC Search Analytics API | search clicks, impressions, clicks/impressions CTR, impression-weighted search position, device/time filters | GSC clicks are not GA4 sessions |
| PSI · Lighthouse | PageSpeed Insights API | URL/device latest lab scores (performance, accessibility, best practices, SEO), LCP/CLS/TBT lab diagnostics | No field CrUX/INP claim |
| Measurement Contracts | Source manifest, safeguards | source isolation, privacy, limitations | No partial or simulated source figures |

Palette: **NEXUS navy/cyan/purple**, responsive Streamlit Plotly figures, time filters, property selectors and download buttons for the already verified aggregate rows. Everything works with open-source tools and does not require a Power BI Pro license. The portable PBIP has separate source/schema checks; this viewer does not establish Desktop rendering or refresh.

### Metric correctness

- The dashboard selects **one GA4 property at a time**. Active users is a distinct metric and is deliberately not summed; real user counts over arbitrary windows must be queried at the desired aggregation grain from GA4 directly.
- Search Console selects **one verified site property at a time**. CTR is total clicks / total impressions. Average position is impressions-weighted. Device filters apply before summing metrics.
- PageSpeed selects the **latest audit per page URL and device strategy**; a score of 0 is valid, not missing. Lighthouse lab diagnostics are separate from real-user CrUX field Core Web Vitals.
- Without a manifest, **onboarding remains accessible** and each source displays Not connected. A validated *single source* is sufficient: the exporter creates header-only CSVs for unconnected sources. Corrupt manifests, unsupported versions, source mismatch, row-count mismatch and partial extractions are rejected before displaying business KPIs.
- Ads spend and conversion attribution are not available; true Google Ads CAC and ROAS **cannot** be calculated. Neither Google report is ever joined to legacy E-Commerce orders or Greenweez finance records.
- Dates, names and reported values in any user export remain tied to the actual source property and its business time zone; the app does not imply a unified global time zone.

### Review & QA

- Offline contract tests: python -m unittest discover -s tests -p 'test_google_measurement*.py' -v
- Dashboard CLI: streamlit run dashboard/google_marketing_app.py
- CI smoke test: tests/smoke_google_marketing_app.py using Streamlit AppTest on empty and synthetic isolated **test-only** export fixtures, plus dbt CI run.
- Source authorization and a fresh live account reconciliation are **outside CI**; publishing a public dashboard requires an access policy and appropriate masking of account/property IDs.
- Google Sheets Greenweez campaign linkage is maintained in this repository: [integrated campaign audit evidence](../integrations/greenweez/docs/GOOGLE_SHEETS_CAMPAIGN_LINKAGE.md) and [audit script](../integrations/greenweez/scripts/audit_sheet_campaign_links.py).

## Further product gates

1. Configure GA4 and GSC read-only property access and compare totals with their UIs.
2. Load externally measured data to source-qualified BigQuery tables using reviewed service identity and cost controls (the chat connection to BigQuery is not available at present).
3. Implement CrUX API field metrics and Google Ads account cost after authorizing and validating sources.
4. Apply NEXUS measures within actual Power BI Desktop and re-capture screenshot evidence after reconciliation.
5. Deploy an authenticated/appropriate-access dashboard; this PR does not publish a public live app.
