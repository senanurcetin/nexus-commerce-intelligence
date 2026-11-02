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

## Updating the lock

Change the direct requirements deliberately, regenerate with the documented command in the lock header, inspect the diff, create a fresh environment and repeat dependency, method and complete-build checks. Do not silently upgrade versions while reproducing an existing result. The lock generator (`uv`) is an authoring tool, not a runtime requirement; ordinary pip installs the result.

No monetization or recurring paid infrastructure is added. This remains an English-language, noncommercial NEXUS portfolio. CI runs temporary synthetic data within the existing repository workflow; do not manually dispatch cloud jobs or publish fixture outputs.
