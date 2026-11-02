# Core-source observation and financial acceptance

The main E-Commerce and Greenweez domains now have a reproducible **private source-observation path**, separate from the synthetic public website and independent public Olist studies. This closes the missing source-row evidence gate for the six approved projections. It does not certify real business origin or accounting meaning.

The 2 November 2026 read captured 180,450 E-Commerce item rows, 29,120 product rows, 13,362 Greenweez rows in each of orders/shipping/refund, and 15 daily advertising rows. The complete paginated read used 97,126,767 response bytes within a 100,000,000-byte cumulative cap, including before/after metadata. Table metadata fingerprints remained stable; CSV hashes and full row counts are retained locally. No SQL query job, export job or Storage Read API was created. The endpoint is the read-only REST equivalent of the documented [`bq head` table preview](https://docs.cloud.google.com/bigquery/docs/managing-table-data); ordinary network access and an already authorized gcloud identity are required.

[Public status](status.json) exposes only source aliases, population counts, transport, contract hashes and acceptance flags. It contains no source records, monetary aggregates, raw identifiers, warehouse account locations or credentials. The detailed source receipt, CSVs, finance results and dbt logs stay under ignored `target/core_source/`. This public receipt is a local observation record, not independent certification of the private source. The source's business dates remain historical; the extraction date is not a current-trading claim.

## Decision readout

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

Obtain an authoritative currency/unit/refund/cost-timing definition and source-origin statement before presenting business finance conclusions. Establish ingestion-time/as-of history before retrospective operational prediction. Native Power BI refresh, DAX execution and rendering remain unverified. Public demo fixtures and distributed archives retain their existing synthetic/historical labels. This remains a noncommercial portfolio; no payment flow, recurring paid resource or monetization feature is introduced.
