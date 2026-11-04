# Research reproduction and acceptance

This project separates three reproducibility claims: analytical methods on adversarial examples, the complete build on temporary synthetic CSVs, and the historical Olist results on separately acquired official inputs. None establishes native Power BI execution or current business validity.

## Locked research environment

`requirements-research.in` declares the six research dependencies. `requirements-research.lock` pins their transitive dependencies, platform markers and accepted distribution SHA-256 hashes. The direct numerical/data versions match the validated analytical environment. Use CPython 3.11. The lock supports platform-aware installation; Windows is verified locally and Linux is exercised by the dedicated automatic CI job. Other Python/platform combinations are not certified.

Windows, from the repository root:

```powershell
python -m venv target/research-repro-venv
target/research-repro-venv/Scripts/python.exe -m pip install --require-hashes --only-binary :all: -r requirements-research.lock
target/research-repro-venv/Scripts/python.exe -m pip check
target/research-repro-venv/Scripts/python.exe -m scripts.research_environment --require-lock
target/research-repro-venv/Scripts/python.exe -m unittest discover -s tests -p test_research_reproduction.py -v
```

Linux/macOS use `target/research-repro-venv/bin/python` for the same commands after `python3.11 -m venv target/research-repro-venv`. Installation needs package-index access; the analyses and synthetic test require no account, credentials, network, browser or paid resource. No raw source dataset is downloaded by CI.

`python -m scripts.research_environment` records actual active package versions, expected pins, mismatches, Python/platform and both requirements hashes. `--require-lock` exits unsuccessfully on a missing/mismatched active package or a Python version outside 3.11. A normal research build also stores this environment receipt in `research_build.json`; it can report a mismatch rather than silently claim a locked build. This lock covers research only. dbt, Streamlit, Node, .NET, fonts, the OS and Power BI remain separate environments. Hash verification authenticates distributions against the recorded lock; it is not a security audit. Matching versions do not guarantee byte-identical figures across platforms or fonts.

## Complete success-path test

The integration test generates six bounded synthetic raw CSVs in a temporary directory. It runs the actual five analysis functions, SQL, fixed statistical protocols, figure/report writers and native BI builder without mocked stages or lowered bootstrap settings. The fixture contains both delivery groups within customer clusters, repeat purchase days, multiple item lines, missing/pre-delivery/late reviews, duplicate review answers, cancelled orders, cutoff boundaries and both matched calendar years.

Acceptance checks cover untouched raw-file hashes, source-to-fact/order-window counts, delivered versus all-status forecasting populations, 30 evaluation weeks/210 days, cross-study raw snapshot identity, each derived aggregate hash, five reports, twelve figures, nine native pages, sixteen semantic tables, the final archive hash and exclusion of fixture order identifiers from exported assets. A sparse support case verifies that unavailable month-standardization is reported as **not estimable**, rather than crashing or inventing an estimate.

These are engineering tests on synthetic values, not additional scientific findings. Their temporary results never replace `docs/advanced-analysis`, public study receipts or shipped archives. Historical study labels inside the temporary build describe the production builder; the test fixture itself is synthetic and must not be published as Olist evidence. Existing independent method and failure-path tests remain necessary; success-path coverage does not replace them.

## Reproduce historical results

Acquire the six official Olist CSVs separately and retain them under ignored `target/olist/raw/`. The optional Kaggle downloader requires its own free account/CLI; it is deliberately excluded from the research runtime and CI. When that CLI is installed, `python -m scripts.fetch_olist --products` fetches all six inputs and preserves existing files.

Using the locked interpreter:

```powershell
target/research-repro-venv/Scripts/python.exe -m scripts.build_research --raw target/olist/raw --out target/research
```

This rebuilds all five studies and a nine-page/sixteen-table native Power BI source package. The output includes source/query/aggregate hashes, statistical protocols, reports, analytical figures and `research_build.json` with the environment receipt. `--schemas` additionally validates official Microsoft JSON schemas, downloading only those schemas if the local cache is absent. TOM parsing, actual refresh, DAX execution and rendering are separate checks; this command does not claim them.

A failed build removes an old success receipt and prevents native export after a failed analysis stage. Keep raw and output folders separate. Cross-platform numerical comparisons should use declared tolerances and population/definition checks; PNG bytes are unsuitable as a scientific equality criterion. The source is retrospective, so the lock does not establish event-time ingestion history or point-in-time availability.

The build receipt also fingerprints the scientific/reporting scripts, analytical SQL, both protocols, environment inputs and official logo. These fingerprints must remain unchanged across analysis and export; otherwise the build refuses a success receipt. Raw CSV hashes remain independently recorded and cross-checked across the five studies. These checks establish observed file stability, not a transactional filesystem snapshot or independently authenticated business origin. The [historical reproduction receipt](research_reproduction.json) records the completed local locked run and comparison with previously published aggregate tables.

## Validate published calculations without raw inputs

```powershell
target/research-repro-venv/Scripts/python.exe -m scripts.analysis_audit --out target/analysis-validation.json
```

This read-only audit uses published aggregates and receipts, without cloud credentials, private raw files or a UI. It independently reconstructs all three forecasting candidates at 44 origins, including an augmented least-squares ridge solution instead of production normal equations. It replays past-fold selection, calibration upper ranks, all four methods' evaluation metrics and the three paired block-bootstrap intervals. It also reconstructs sharp missing-rating bounds at three windows and the complete 441-scenario primary assumption grid from integer outcome counts. Production estimator/bootstrap/bound helpers are not called; tests explicitly disable them during the real audit.

Automatic CI executes the replay and its adversarial tests inside the hash-locked research job, alongside the synthetic full-build check. The general dbt/dashboard environment does not define the numerical replay's dependency versions.

Six checks combine an input fingerprint snapshot, cross-study/evidence and executive-readout integrity, independent forecast replay, independent missing-rating replay, the three actual portable archives, and final input stability. Forty-seven input files are content-addressed with canonical JSON or LF-normalized text. The receipt records the validator's implementation hash, numerical tolerances and actual runtime versions. The [committed result](analysis-validation.json) captures the completed local check; repeat it rather than relying on an old PASS after edits.

Historical reproduction receipts retain their exact captured file hashes. For known text inputs, the audit accepts only exact bytes or CRLF/LF-equivalent text when verifying those old hashes; binary files remain byte-exact. This handles the legacy Windows report generator on Linux without rewriting historical evidence. Added comments, whitespace beyond line endings and other content edits still invalidate the fingerprint.

The CLI exits unsuccessfully and writes a FAIL receipt if an input is missing, a formula does not reproduce, evidence is stale or files change during validation. That replaces an old result, preventing stale success. Matching CSV and JSON summaries are insufficient: tests forge both a positive forecasting interval and a rating bound together, and independent arithmetic still rejects them. Unknown metrics remain null rather than becoming zero.

PASS applies only to the checked published calculations and artifacts. It does not certify original raw-source authenticity, source ingestion times, current business validity, financial interpretation, causal effects, original review customer-cluster sampling intervals, prospective forecast utility or native DAX/refresh/rendering. The review sampling intervals require their original customer-level evidence and are explicitly marked **not replayed** here. The financial, operational and native BI gates remain HOLD. This adds a reproducible verification path, not a new business study or a revised scientific conclusion. Olist-derived results retain CC BY-NC-SA 4.0 attribution and noncommercial use.

## Replay review-selection cluster intervals from local raw inputs

```powershell
target/research-repro-venv/Scripts/python.exe -m scripts.review_cluster_audit
```

The default receipt is `target/review-cluster-validation.json`. Four separately acquired Olist CSVs must already exist in `target/olist/raw`; this command never downloads data. [The historical acceptance receipt](review-cluster-validation.json) records a completed locked-runtime replay of **68,448 mature delivered orders / 66,295 customers**, six group/window cells, 24 availability cells and **eighteen pointwise confidence limits**. All 1,000 bootstrap replicates were valid; 98 distinct customer-ledger patterns were reconstructed.

The validator streams CSV records with the standard library. It independently applies purchase/maturity boundaries, positive-item eligibility, calendar-date lateness and first eligible review selection, including creation-time/ID/score tie breaks. Customer identities are kept only in memory; one customer's complete three-window ledger stays together. A `Counter` and sorted patterns replace the production `np.unique` path; scalar multinomial draws and explicit integer accumulation replace batched matrix multiplication. Linear order-statistic interpolation replaces the production quantile call. The pinned NumPy random generator is shared deliberately to replay the declared seed; this is independent selection/aggregation/statistic implementation, not an independent RNG library. See NumPy's [multinomial](https://numpy.org/doc/2.1/reference/random/generated/numpy.random.Generator.multinomial.html) and [linear quantile convention](https://numpy.org/doc/2.3/reference/generated/numpy.quantile.html).

The protocol is pinned, raw file sizes/hashes and row counts must match published evidence, and independently reconstructed counts, availability reasons, bootstrap metadata and estimates must agree with both CSV and JSON. Input and validator stability are checked around execution. Failure overwrites an earlier CLI PASS with FAIL; receipts contain no raw IDs, review text or absolute source paths. Raw hashes are byte-exact; public text fingerprints normalize CRLF/LF for cross-platform receipt checking.

Fourteen tests use temporary synthetic CSVs, never historical replacements. They disable production loaders/estimators/quantiles during the independent replay, check against the separate production reference, and reject forged matching CSV/JSON/checksums, rehashed duplicate item rows, altered customer clustering, changed availability counts, redefined protocols/provenance and mid-run changes. CLI tests verify stale-PASS replacement and protection against writing into raw inputs. CI exercises those fixtures and public receipt/code fingerprints; it does **not** download or rerun historical source records.

This closes numerical replay for the **review-selection study's** original customer-cluster intervals only. The earlier delivery-association study has a different cohort and bootstrap and is outside this command. Endpoint intervals remain pointwise sampling intervals, not simultaneous coverage of a partially identified set. Source authenticity, representativeness, capture completeness, noninformative selection, current business validity, causality and native BI remain unverified. The aggregate-only `scripts.analysis_audit` correctly continues to say it does not perform raw cluster replay; the two commands have separate scopes. No scientific conclusion, study CSV, figure or native report was changed by this validation pass.

## Replay the original retrospective delivery association

```powershell
target/research-repro-venv/Scripts/python.exe -m scripts.delivery_association_audit
```

This command uses the same four separately acquired local source CSVs and writes `target/delivery-association-validation.json`. It independently selects the **latest** review with descending answer/creation/ID/score tie breaks, valid delivery chronology and the original retrospective eligibility. It does not call production SQL, the order-fact loader, estimator or bootstrap. Shared primitives from the separate CSV audit perform parsing, hashing and independently implemented percentile interpolation; their code hash is also captured. The NumPy RNG is shared for exact declared-seed replay, while multiplicity-weighted customer ledgers replace the production copied resample matrix. Every customer's orders remain together in all 1,000 draws.

[Historical acceptance](delivery-association-validation.json) reproduces **84,763 reviewed orders / 82,228 customer clusters**, all 38 month/group cells, 13 common-support months, pooled-month standardization, the all-review-timing contrast and the original **+10.73 pp** association with **+8.90 to +12.54 pp** pointwise customer-cluster percentile limits. State Fisher/FDR calculations are outside this validator. Twelve tests cover independent-helper execution, agreement with the reference, null/sparse support, boundary/tie/fallback selection, consistent rehashed forgeries, changed inputs, provenance/specification, invalid ledgers and CLI stale-success/raw-output protection. CI uses temporary synthetic raw records and verifies public receipt/code fingerprints; it does not fetch historical records.

The original study is explicitly retrospective: purchase before the cutoff does not require delivery or review before it. In the observed original sample, **1,862 deliveries** and **2,761 selected answers** occurred on/after 2018-08-01; their union is 2,761 orders. These counts quantify an already documented design boundary, not an undisclosed defect or proof of original ingestion availability. The native Power BI context and footer now carry this qualification directly.

The additional descriptive event-time restriction requires delivery before the cutoff and selects the latest dated answer **from answers before the cutoff**, then checks that it follows delivery. It retains **82,005 orders** (1,626 late; 80,379 on time), with a **+10.74 pp** contrast. Three orders with a post-cutoff latest answer regain an earlier eligible answer; simply filtering the already-selected latest answer would omit them. This is a different selected sample, with no new sampling interval or equivalence/robustness test. Final delivered statuses are still retrospective, and original source/status ingestion history is unavailable: this is **not a genuine point-in-time backtest**. It identifies neither a delivery intervention effect nor current operational performance. Original scientific CSVs, figures and numerical Power BI measures are preserved.

Raw hashes are byte-exact; public/helper text snapshots normalize CRLF/LF. Inputs and both independent implementations must remain stable around validation. A failed CLI run removes stale success and writes FAIL without raw keys, review text or absolute source paths. Olist-derived aggregate receipts retain CC BY-NC-SA 4.0; no paid infrastructure or cloud queries are added.

## Replay the matched-period delivery comparison

Run `python -m scripts.operations_audit` with the three local order, customer and item CSVs. The command reconstructs the January–July cohorts and groups customer orders across both years for the seeded bootstrap. It checks the fourteen monthly counts and rates, all 102 common-support strata, pooled standardization and the rate and mix contributions against the published CSVs and evidence.

The historical replay covers 64,230 delivered orders and 62,529 customer clusters. The crude late-rate increase was 4.30 percentage points, with a 95% customer-cluster percentile interval of 3.94 to 4.67 points. In the common-support comparison, within-stratum changes contributed 3.84 points and changes in stratum weights contributed 0.31 points. The decomposition is descriptive and the interval applies to the crude comparison. [Historical receipt](operations-validation.json)

## Updating the lock

Change the direct requirements deliberately, regenerate with the documented command in the lock header, inspect the diff, create a fresh environment and repeat dependency, method and complete-build checks. Do not silently upgrade versions while reproducing an existing result. The lock generator (`uv`) is an authoring tool, not a runtime requirement; ordinary pip installs the result.

No monetization or recurring paid infrastructure is added. This remains an English-language, noncommercial NEXUS portfolio. CI runs temporary synthetic data within the existing repository workflow; do not manually dispatch cloud jobs or publish fixture outputs.
