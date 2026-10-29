# GitHub Copilot repository instructions — E-commerce

This is an **analytics engineering** project: BigQuery/dbt Cloud models with a local DuckDB adapter path and historical Power BI evidence. It includes a separate test-only storefront and a synthetic portfolio presentation. Read `README.md`, `dbt_project.yml`, `models/marts/marts.yml` and relevant `tests/` before proposing changes.

## Project-specific boundaries
- The **main clickstream and orders dataset** drives dbt marts and Power BI references; the public **Olist** analysis is a separate historical domain. Its controlled pipeline is `scripts.advanced_olist` with SQL under `analytics/olist/`, aggregate evidence under `docs/advanced-analysis/`, and independent native BI via `scripts.build_olist_powerbi`. Historical notebooks are exploratory references. Never mix source results, denominators or case-study claims.
- Preserve grain: `fct_order_marketing` is order-item level and rebuilt each run to capture mutable returns; `fct_marketing_web_performance` is session plus user grain. Avoid multiply joining these facts without careful aggregation.
- Keep `dim_user.signup_traffic_source` (acquisition) distinct from `fct_marketing_web_performance.traffic_source` (session first-touch) and from order attribution.
- Use existing dbt tests, deterministic local seed fixtures, and offline Python scripts. For target-specific expressions review BigQuery and DuckDB branches. Do not change either adapter silently.
- Never expose production rows, credentials, user emails/IP addresses, BigQuery datasets or sensitive notebook output in PRs.
- A portable synthetic PBIP and a seven-page private-source generator are available. Historical screenshots have been removed; generated analytical figures are not BI screenshots. Do not imply that a changed theme or screenshot was validated or published. The Turkish `B` abbreviation means *bin* (thousand), not billion.
- Preserve revenue/return reconciliation, price validation, event-order tiebreakers, stable business labels, and existing source-to-mart tests.
- Metric definitions live in `contracts/metrics.json`; validate/render via `scripts.metric_contracts`. Product contribution rates require a matched known-cost revenue denominator. Greenweez coverage diagnostics preserve existing missing-component policies and are raw-branch only. Do not relabel completed value as recognized accounting revenue, returned item value as refunded cash, or sessions per user as acquisition cost.
- `scripts.build_research` reproduces all three Olist studies from six local CSVs. Preserve shared raw/fact fingerprints, LF-normalized aggregate hashes, matched Jan–Jul windows, common-support coverage and separate full/standardized/decomposition estimands. Kitagawa components and state burden priorities are descriptive; never turn them into causal effects, service-quality rankings or lost revenue.
- CI quotas are unavailable: **do not manually run or dispatch GitHub Actions, CircleCI, Vercel, or dbt Cloud jobs**. Local, credential-free tests are permitted when installed. Never bypass required checks.
- Do not claim tests were run if only source checks were performed. Report exact commands, errors and unverified scopes.
- Use narrow changes with regression tests and PR review; do not autonomously merge or rewrite unrelated workflow, README, screenshots or notebooks.

## Select a specialized agent
- `commerce-dbt-integrity`: dbt data contracts, attribution, revenue/returns and adapter-specific SQL.
- `commerce-powerbi-evidence`: DAX/SQL lineage, screenshot provenance, presentation evidence and release gates.

See `docs/COPILOT_AGENTS.md` for offline acceptance prompts and scope.
