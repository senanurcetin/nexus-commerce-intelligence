# Portfolio delivery readiness

Regenerate with `python -m scripts.release_audit --out docs`. This checks the actual published ZIP bytes, not a different working build. It performs no network requests or UI automation.

**Portable artifact delivery: READY. Native Power BI acceptance: HOLD.**

| Deliverable | Offline artifact checks |
| --- | --- |
| synthetic_powerbi_archive | PASS |
| public_research_archive | PASS |
| synthetic_website_archive | PASS |

The checks cover pinned archive size/SHA-256, bounded safe archive paths, PBIP/report/model bindings, page/table counts, portable model paths, official logo bytes, matching research sources/aggregate hashes, current bundled reports/protocol/query, report links, and synthetic-only website provenance. They do not establish visual fidelity, successful refresh, or DAX results. Microsoft schema and TOM parser results are separate checks recorded in [delivery evidence](DELIVERY.md).

The research package contains four reports and ten figures alongside an eight-page/fourteen-table native BI project. Review-selection sensitivity is a companion report, without a separate native page. E-Commerce and Greenweez fixtures remain synthetic, and Olist remains a separate historical public study under CC BY-NC-SA 4.0. A live private-source refresh is not required to present that explicitly historical portfolio; it is required before making new live-business claims.

Outstanding native acceptance requires actual Power BI opening, refresh, DAX execution and visual inspection. This command cannot promote those gates. Browser and PC-screen automation remain excluded from this workflow. PR review and merging are independent repository actions and are not performed by this audit.
