# Project level and development assessment

Assessment date: 27 October 2026. Scope: repository, local dbt artifacts, executable analysis, reporting and source contracts. No browser, Playwright or PC-screen access.

## Level

**Intermediate-to-advanced analytics engineering; developing professional analytical case study.** This is a qualitative assessment, not a certification or an invented numeric score.

| Dimension | Evidence | Remaining gap |
| --- | --- | --- |
| Data engineering | Two independently executable dbt projects, staging/intermediate/marts, adapter branches | Live source refresh and business reconciliation are separate acceptance steps |
| Data quality | Uniqueness, relationships, status/revenue tests and source-isolated adapters | Greenweez warning cases remain visible; they cannot be silently promoted to verified finance |
| Analytical correctness | Executable channel, ordered funnel and product analysis, uncertainty diagnostics | Synthetic fixtures cannot establish real commercial findings |
| Reproducibility | One local build command, database/query fingerprints, aggregate CSV results | Original Olist notebooks depend on their own external source data |
| Communication | Questions → methods → findings → implications → limitations | No new live BI publication or UI screenshot evidence is claimed |
| Design | Official NEXUS logo; midnight, cyan, blue and lavender palette | Browser and Desktop render verification intentionally not performed |

## Defects addressed

- Funnel referenced a channel column absent from its source model and collapsed sessions across different users. The corrected SQL takes session attribution from the session mart and requires chronological steps within `(session_id, user_id)`.
- Channel analysis treated an absent session denominator as a zero conversion rate. It now returns null.
- Historical chi-square figures appeared as current conclusions in SQL comments. Current-snapshot expected-cell checks and descriptive confidence intervals replace those claims.
- Summed daily distinct orders were labelled as period-unique orders/AOV. Public aggregates now use order-day terminology; the report computes true period-distinct orders from the fact.
- Power BI charts overlapped KPI cards, and local CSV paths were unsuitable for portable distribution. Layout coordinates were corrected and the public project embeds aggregate data.
- A Unix-specific GA4 authentication test failed on Windows. Both OS branches are now tested explicitly without changing permissions or requesting credentials.

## Completion standard

A professional portfolio release needs inspectable results, tested grain and denominator definitions, transparent source limitations, concise navigation, approved branding and a reproducible native BI artifact. Code/schema acceptance does not establish Desktop rendering, financial audit or source freshness.
