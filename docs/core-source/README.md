# Core-source observation and financial acceptance

The main E-Commerce and Greenweez domains now have a reproducible **private source-observation path**, separate from the synthetic public website and independent public Olist studies. This closes the missing source-row evidence gate for the six approved projections. On 5 November 2026, BigQuery table metadata identified both E-Commerce tables as part of the fictitious The Look dataset and explicitly described the order items as generated. The four Greenweez tables had no table or field descriptions and no external source definition. Greenweez origin and accounting meanings remain unverified.

The 2 November 2026 read captured 180,450 E-Commerce item rows, 29,120 product rows, 13,362 Greenweez rows in each of orders/shipping/refund, and 15 daily advertising rows. The complete paginated read used 97,126,767 response bytes within a 100,000,000-byte cumulative cap, including before/after metadata. Table metadata fingerprints remained stable; CSV hashes and full row counts are retained locally. No SQL query job, export job or Storage Read API was created. The endpoint is the read-only REST equivalent of the documented [`bq head` table preview](https://docs.cloud.google.com/bigquery/docs/managing-table-data); ordinary network access and an already authorized gcloud identity are required.

[Public status](status.json) exposes only source aliases, population counts, transport, contract hashes and acceptance flags. It contains no source records, monetary aggregates, raw identifiers, warehouse account locations or credentials. The detailed source receipt, CSVs, finance results and dbt logs stay under ignored `target/core_source/`. This public receipt is a local observation record, not independent certification of the private source. The source's business dates remain historical; the extraction date is not a current-trading claim.

## Decision readout

The count-only operational analysis now covers 180,450 observed E-Commerce item rows and 124,244 distinct order keys. The snapshot has zero mixed-status orders and zero ambiguous customer orders under the recorded keys. Independent CSV counts reconcile the SQL status populations.

Delivery precedes item creation in 6,031 rows, including 4,317 Complete and 1,714 Returned items. The materialized duration inputs retain 57,231 of 63,262 Complete/Returned item rows. The other 6,031 rows are stored in a private quarantine with source identifiers and original timestamps for investigation. Every terminal item belongs to exactly one output. Eligible inputs have zero invalid duration rows. [Operational receipt](operations.json)

Run `python -m scripts.core_operations` against the existing private snapshot to reproduce the receipt. The command publishes counts and decision criteria. Financial amounts and source keys remain in the private source boundary. Current status describes the observed snapshot. Historical status availability remains an open evidence requirement.

The private outputs are `eligible_delivery_items.csv`, `quarantined_delivery_items.csv` and `manifest.json` beneath ignored `target/core_source/derived_operations/`. Directory versions bind the source hash, implementation hash and observation boundary. Repeated execution verifies existing file hashes. Staged writes publish the complete partition together. Source CSVs and timestamps remain preserved. The quarantine resolves downstream input eligibility while upstream corrections require authoritative event definitions.

On 5 November 2026, a one-to-one comparison by product ID matched all 29,120 observed products to Google's published theLook catalogue. Category and department matched exactly. Cost and retail price matched within relative tolerance 1e-9 and absolute tolerance 1e-8. All 180,450 observed item sale prices also matched their reference catalogue retail price within that tolerance. The reference CSV SHA-256 is `26107d3ac2d0acf08499eab4d81e2acc692abf2ed5d9518076b62568a39d50c0`. This supports catalogue lineage. Transaction-time costs, currency and the order snapshot's exact generation history remain unverified. [Pinned catalogue reference](https://github.com/GoogleCloudPlatform/public-datasets-pipelines/blob/14735c60589ab22361dc0d54ad7491ba7ae96a04/datasets/thelook_ecommerce/pipelines/_images/run_thelook_kub/data/products.csv)

All 6,031 reversed timestamps occur in multi-item orders. Of those rows, 1,672 reverse within the same UTC date and 4,359 reverse across UTC dates. Google's published generator copies order delivery timestamps into items and can advance item creation by up to four days during multi-item event generation. The code provides a plausible mechanism for the observed pattern. The private partition retains the source values for review. [Pinned generator reference](https://github.com/GoogleCloudPlatform/public-datasets-pipelines/blob/14735c60589ab22361dc0d54ad7491ba7ae96a04/datasets/thelook_ecommerce/pipelines/_images/run_thelook_kub/fake.py)

- **Proceed with source-scoped engineering:** observed item/product keys and Greenweez order/component keys are unique and non-null. Complete projections reconcile to source metadata, and independent Python decimal sums reconcile with DuckDB decimal sums. These controls support reproducible analysis of the observed fields.
- **Investigate zero-cost interpretation:** the observed Greenweez source includes 561 zero purchase-cost records and 13 zero-turnover records. These are retained and flagged, rather than automatically corrected or asserted to be errors. All three order-component populations align on key and date in this snapshot.
- **Hold financial claims:** currency, refund units, tax/shipping inclusion and transaction-time COGS remain unverified. Zero missing joins does not resolve their meaning. E-Commerce product catalogue costs are snapshots, not historical COGS. Greenweez's refund field is never subtracted from turnover while its units remain unknown.
- **Hold current funnel and operating decisions:** this read excludes the large events table and personal user table. It supplies no refreshed full-funnel denominator, incremental campaign return, current demand forecast or causal evidence. Do not merge these populations with Olist or the separate Greenweez media workbooks.

## Reproduce locally

From the repository root, with the existing Python/dbt dependencies and authorized gcloud identity:

```powershell
python -m scripts.read_core_source
python -m scripts.profile_core_source
python -m scripts.build_observed_greenweez
python -m scripts.export_core_source_status
```

Only the first command contacts the cloud. Do not repeat it merely to regenerate documentation; subsequent commands use the recorded private snapshot. The read is fixed to approved scalar fields and pinned sources, capped at 250,000 rows per table, 10,000 rows per response and 100 MB total response bytes. It excludes personal names, email, addresses and event-level rows. A row-count, pagination, byte-budget or metadata-version failure rejects publication of a new local pointer. Source IDs used as join keys still remain private. Metadata checks detect observed changes during the read; they do not constitute a transactional database snapshot or event-time history.

The selected Greenweez finance dbt build uses an isolated local database, no synthetic seeds, no cloud execution and no changes to the existing demo databases. Its 11 models and 41 data tests passed, with one retained warning: 12,426 rows have a refund number above turnover, an arithmetic comparison of unverified units rather than evidence of over-refunding. Source row counts and the null refund-adjusted revenue gate are checked after the build. Unit tests are excluded from this observed-data build; offline adversarial tests independently exercise the new import and finance eligibility controls. Legacy marts preserve their documented component policies. The separate profile requires unique, valid, nonnegative, same-date components and never fills missing costs with zero.

[Read contract](../../contracts/core_source_read.json) and [financial semantics contract](../../contracts/financial_semantics.json) define the executable boundaries. A completed-item catalogue contribution uses the same valid-price/known-cost rows for its numerator and denominator. A complete-component Greenweez subtotal is selected arithmetic, not audited net profit or a bound on business profit. Daily advertising is not allocated to individual orders.

## Remaining acceptance

[Temporal availability](TEMPORAL_AVAILABILITY.md) now provides a private whole-snapshot registration history and strict as-of selection. It prevents latest-snapshot fallback before local availability and retains separate observation/registration times. This creates a forward-looking control; it does not reconstruct source ingestion history or make the historical finance fields point-in-time valid.

Obtain an authoritative currency/unit/refund/cost-timing definition and a Greenweez source-origin statement before presenting business finance conclusions. Establish ingestion-time/as-of history before retrospective operational prediction. Native Power BI refresh, DAX execution and rendering remain unverified. Public demo fixtures and distributed archives retain their existing synthetic/historical labels. This remains a noncommercial portfolio; no payment flow, recurring paid resource or monetization feature is introduced.
