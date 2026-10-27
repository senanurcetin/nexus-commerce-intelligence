# NEXUS Commerce — Power BI delivery

## Portable portfolio report

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
