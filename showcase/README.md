# NEXUS Commerce — static portfolio presentation

English-language presentation of two independent synthetic dbt sources and a separate historical public Olist research portal.
The official NEXUS logo is copied unchanged during the build.

```powershell
python -m scripts.build_demo --deps
python -m scripts.serve_portfolio
```

Open `http://127.0.0.1:8787` yourself. The build does not launch or control a browser.
Alternatively extract [the packaged demo](NEXUS_Commerce_Web_Demo.zip), run `python serve.py` inside the extracted folder, and open the printed localhost address. The bundled server uses only Python's standard library and sends `.mjs` as JavaScript. Windows MIME associations can make a generic server send modules as `text/plain`, which browsers reject. Opening `index.html` directly as a
`file://` URL can block the local JSON fetch.

The site filters the selected domain by inclusive dates and recomputes weighted
ratios. A missing period is an empty state. Daily distinct orders are labelled
order-days; they are not guaranteed period-distinct orders. Exports contain only
filtered synthetic aggregates. No account data, tracking script, credentials,
remote font, LLM or warehouse call is required.

Source, metric and export behavior has local unit coverage. Browser interactions,
responsive rendering and screen-reader behavior remain unverified because this
pass does not use Playwright, a browser session or a PC screen.

Rebuild both portable artifacts with `python -m scripts.package_portfolio`.

## Research studio

Open `/research/index.html` from the same local server. Five study views retain their own population, finding, method, decision and limits. The forecasting explorer compares recorded methods over the last eight or all thirty evaluated weeks, recomputes displayed-date MAE/WAPE/day coverage, and exports every displayed forecast. Its full benchmark table remains fixed. The review explorer varies explicitly assumed unavailable-rating probabilities; it does not impute truth or estimate causal effects.

The builder validates the pinned public Olist package before writing any research output. The website archive includes the five complete reports, source receipts, twelve figures, aggregate CSVs, protocols, and a downloadable native BI ZIP. Portal fingerprints bind the client assets and evidence to that package. The original commerce `data.json` remains synthetic-only; research data lives under `research/` with its own historical provenance and CC BY-NC-SA 4.0 license. No totals are combined between those surfaces.

Local formula, chronology/selection, SVG safety and evidence-link tests run without a browser. They do not establish actual browser rendering, responsive fidelity, native Power BI refresh or assistive-technology acceptance.
