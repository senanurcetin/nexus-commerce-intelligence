# NEXUS Commerce Lab — Controlled Test Storefront

**Purpose:** A controlled, independently deployable storefront for **real browser interaction studies, voluntary GA4 measurements and Lighthouse performance audits**. It is not a payment-accepting commerce business and does not generate the legacy TheLook historical order records.

## Local Windows start (no npm install or paid plan)

From a local checkout of the NEXUS Commerce Intelligence GitHub repository:

~~~cmd
cd /d C:\Users\MONSTER\E-commerce
git pull origin main
python -m http.server 8787 --directory storefront
~~~

Open **http://localhost:8787**. Browse, filter, add/remove products, open cart and complete a clearly marked *test checkout*. The catalog names and prices are illustrative. No personal customer information, actual order or bank card is requested.

To build deployment assets (requires Node.js 20+):

~~~cmd
node --test storefront\tests\lab.test.mjs
node storefront\scripts\build.mjs
python -m http.server 8788 --directory storefront\dist
~~~

Open **http://localhost:8788** for the production static bundle. The app is deliberately self-contained; no runtime backend, npm packages, or credit card provider is required.

## Deploy an owned storefront on Vercel

1. Create or connect a Vercel project to the existing GitHub repository.
2. In Vercel configure **Root Directory: storefront**.
3. The included `vercel.json` builds with `node scripts/build.mjs` into `dist`.
4. Keep the optional environment variable `NEXUS_GA4_MEASUREMENT_ID` blank until your own GA4 web data stream exists. Never enter an API key, Google service-account JSON or private token in this variable: it appears in the public page.
5. Deploy and visually review the issued Vercel HTTPS URL before sharing. Configure a verified domain only if you own it.

**Deployment status (16 October 2026):** A Vercel project named `nexus-commerce-lab` was created in the authorized user workspace and a Git deployment built successfully (READY) from `main` as `https://nexus-commerce-lab.vercel.app/`. **Production Vercel Authentication protection was changed to preview-only with user approval on 16 October 2026**; preview deployments remain protected. Authorized Vercel fetch received HTTP 200 for the homepage and public configuration. Anonymous browser functional QA remains outstanding. The build explicitly had **no GA4 Measurement ID**. No live browser, PageSpeed, GA4 property ownership or GSC result is verified yet. Public access and privacy review remain an operator release decision.

## Initial external site assessment

A FlawPilot quick scan completed its own 36 checks and reported performance 100, infrastructure 84.88, security 73.85 and SEO 58, overall GROWTH_READY: https://flawpilot.com/report/X88JSW . **These are not Google Lighthouse or PageSpeed scores** and should never be imported into the PageSpeed source mart. The production domain currently has intentional `noindex, nofollow`, so Search Console organic Search data is not expected. The Google PageSpeed API still needs a separately documented live mobile and desktop run.

## Consent-first analytics

The default public `config.js` has a blank Measurement ID. This makes the site **completely GA4-disconnected**. If you own an authorized GA4 web property and have a measurement ID such as `G-ABC123456`, build the deployed bundle with that ID (for Windows CMD):

~~~cmd
set NEXUS_GA4_MEASUREMENT_ID=G-ABC123456
node storefront\scripts\build.mjs
~~~

The Measurement ID is intentionally public; GA4 Admin authorization is required to **read** the resulting reports. Merely adding somebody else's Measurement ID does not grant access or ownership.

Visitors may accept or reject optional analytics. Before consent, no `gtag.js` or third-party fonts are loaded. The app also works if browser storage is disabled. Consent preference is remembered locally when permitted. The visitor can reopen their analytics preference control.

The only allowed custom event names are `lab_page_view`, `lab_view_item`, `lab_add_to_cart`, `lab_remove_from_cart` and `lab_checkout_completed`. Allowed item-specific fields are catalog item ID and unit count. Every event includes `lab_environment=sandbox` and `lab_catalog=illustrative`. There is **no** GA4 `purchase` event, revenue, transaction ID, customer email, address or any actual checkout record.

For production operation, review the site's jurisdiction-specific privacy disclosure, deletion/retention controls and consent compliance. Browser-side analytics must not be represented as tamper-proof or fraud-resistant.

## Data isolation

| Source | What can be shown | What cannot be inferred |
| --- | --- | --- |
| Existing historical E-Commerce / TheLook-style BigQuery tables | Product, order-item, session and channel demo-analysis marts | Real sessions on this newly deployed domain |
| Owned Commerce Lab GA4 property, **if explicitly configured** | Actual opted-in interactions with `lab_*` event names | Real purchase revenue, CAC, ROAS, or historical TheLook order counts |
| PageSpeed Insights on a **deployed** Lab URL | Real Lighthouse lab performance and mobile/desktop comparison | GA4 unique visitors, test purchases or real-user CrUX Core Web Vitals |
| Google Search Console verified Lab URL | Organic Search queries/clicks/impressions, when indexed and data becomes available | Historical TheLook purchases or data about third-party storefronts |

The launch version includes `<meta name="robots" content="noindex, nofollow">` because it is a private testing environment. This means GSC performance data is not expected until indexing is explicitly approved, the robots policy is changed and a site is verified.

## Presentation acceptance

- Test the actual deployed store under a known URL, not a third-party demo site.
- Check responsive mobile layout, cart, consent opt-in and reject, no external payment flow, and keyboard navigation.
- Confirm in GA4 DebugView (after enabling your own property and opting in) that custom `lab_*` events arrive without `purchase` or `value`. Code/CI tests alone cannot prove live arrival.
- Run PageSpeed mobile and desktop audits on the deployed URL and record actual API source and timestamp.
- Keep the TheLook Power BI finance KPIs separate from live test-site events.
- Only when source ownership, API reconciliation and visuals are checked should the portfolio describe it as a **connected lab**.

The [delivery record](../docs/DELIVERY.md) tracks the remaining work.
