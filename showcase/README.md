# NEXUS Commerce — static portfolio presentation

English-language presentation of the two independent synthetic dbt sources.
The official NEXUS logo is copied unchanged during the build.

```powershell
python -m scripts.build_demo --deps
python -m http.server 8787 --bind 127.0.0.1 --directory target/showcase
```

Open `http://127.0.0.1:8787` yourself. The build does not launch or control a browser.
Alternatively extract [the packaged demo](NEXUS_Commerce_Web_Demo.zip) and serve
that folder using any static HTTP server. Opening `index.html` directly as a
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
