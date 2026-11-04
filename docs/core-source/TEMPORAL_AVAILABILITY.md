# Snapshot availability and as-of selection

The core-source workflow now has a private, append-only-by-API SQLite history under ignored `target/core_source/history.sqlite3`. It records whole validated six-table snapshots, not individual row changes. Its purpose is to prevent a retrospective analysis from silently substituting data that was unavailable at the requested cutoff.

**Availability begins at local registration.** The original source observation time is retained separately. Business dates and warehouse modification times never backdate availability. Registering the existing historical source today does not demonstrate that those final statuses, refunds or costs were known during 2021. The CLI has no backdating override. An inclusive cutoff permits a version at its recorded availability timestamp; before that boundary it remains unavailable.

## Verified observation

One existing private source snapshot has been registered without another cloud read. The published [history status](temporal-status.json) contains only availability boundaries and an opaque chain-head hash. The [verification receipt](temporal-verification.json) records that a 2021-10-15 cutoff returns **unavailable**, while the exact registration boundary permits a controlled profile of 180,450 E-Commerce items and 13,362 Greenweez orders. The independent raw amount reconciliation still passes. No source rows, monetary aggregates, warehouse account locations or join identifiers are published.

These checks establish conservative local eligibility, not original source ingestion times, a transactional warehouse snapshot, freshness or current business validity. Olist is a separate frozen retrospective study; this feature does not turn its historical forecasting benchmark into an operational point-in-time backtest.

## Local commands

Use an already captured, private source snapshot. These commands make no network requests and create no SQL query jobs:

```powershell
python -m scripts.core_source_history register
python -m scripts.core_source_history as-of --at 2021-10-15T23:59:59Z
python -m scripts.core_source_history audit --out docs/core-source/temporal-status.json
$historyCutoff = (Get-Content docs/core-source/temporal-status.json | ConvertFrom-Json).latest_available_at_utc
python -m scripts.profile_core_source --as-of $historyCutoff
```

`register` defaults to the existing private `latest.json` pointer, or accepts `--snapshot` for another captured version beneath the private root. Each registration rechecks the fixed read contract, source projection, file hashes and complete row counts. A future observation or regressing local clock rejects a new registration. Identical receipts are idempotent and cannot change their first availability time or directory binding. Concurrent registration is serialized with an immediate SQLite transaction; failures roll back without appending a partial version.

`as-of` requires an explicit timezone-aware ISO timestamp and normalizes offsets to UTC. Missing history or no eligible version produces `availability: unavailable`, never the current latest snapshot. Add `--require` to exit unsuccessfully instead. Python callers can use `require_as_of(cutoff)` to obtain a validated path and its history entry, or `resolve_as_of(cutoff)` to obtain `None` when unavailable. The selected version is revalidated against its registered receipt and raw files. No per-table latest-version mixing is performed.

`profile_core_source --as-of` enforces that selection and records the cutoff, availability time and history-entry hash in its private profile. These results go into `analysis/as-of/<normalized-cutoff>/`, leaving the original retrospective profile and dbt receipt untouched. `--snapshot` and `--as-of` are mutually exclusive. The existing default profile command remains an explicitly retrospective latest-snapshot profile; it must not be presented as historical availability evidence.

## Integrity and limits

Entries form an ordered SHA-256 chain, binding snapshot receipts, source-file hashes, populations, registration/observation times and the previous entry. Reads reject changed fields, broken chronology and missing intermediate sequence numbers. The public projection omits paths, table file hashes and raw/financial values.

The chain is an integrity mechanism, **not authentication of a hostile local writer or proof of a trustworthy system clock**. A complete rewrite or removal of the final suffix cannot be detected from a self-contained local chain alone. Preserve a previously published status as an independent comparison anchor:

```powershell
python -m scripts.core_source_history audit --anchor path/to/previously-published-status.json
```

The anchor's recorded entry count and chain head must match the corresponding prefix of the current history. Legitimate later appends are allowed. Keep previous public anchors in version control; replacing the anchor with the altered local head supplies no independent assurance. Automatic selection verifies local chain and source integrity; independent anchor checking is an additional explicit audit step.

Retain the SQLite history and its matching immutable private snapshot directories together. Moving/deleting source files can make an old version unavailable for verification. No automatic source refresh, scheduler, paid storage or row-level change feed is introduced. Future source reads should be registered as new observations without editing older receipts. Finance semantics, original business provenance, new prospective outcomes and native Power BI execution remain separate acceptance gates.

The current reader intentionally accepts only the fixed source contract. A contract/projection change needs a deliberate migration and review; old versions must not be silently interpreted under a new schema. Registration verifies source integrity, not uniqueness of every analytical join or financial eligibility; the separate profile retains those controls.
