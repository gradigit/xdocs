# Mission Control

## Active Directives
<!-- Human writes steering directives here. Agent acknowledges and follows. -->

## Acknowledged
<!-- Agent moves processed directives here with timestamp and action taken. -->

### [2026-03-06] crawl4ai/cloudscraper headed mode for JS rendering (cloudscraper REMOVED — CVE-2024-28397)
**Directive:** check if other crawl methods like crawl4ai or cloudscraper that we're using has headed mode, to crawl js rendered websites without having to fallback all the way to playwright.
**Action:** Full research completed. Findings:
- **crawl4ai IS Playwright** — it imports `playwright.async_api` directly and lists `playwright>=1.49.0` as a hard dependency. Using crawl4ai = using Playwright. It does support `BrowserConfig(headless=False)` for headed mode, but this is just Playwright's headed mode.
- **cloudscraper cannot render JS** — it only solves Cloudflare IUAM challenges via JS interpreters. It cannot execute page JavaScript or render SPAs.
- **No lightweight alternative exists** — pyppeteer (unmaintained), requests-html (archived 2019), Selenium (still needs Chrome binary) all require a browser engine. JS rendering fundamentally requires a browser.
- **Playwright is already installed** (v1.58.0, 622MB Chromium cache) as a hard dependency of crawl4ai. The current `--render auto` cascade (requests first → Playwright fallback) is already the optimal approach.
- **Conclusion:** No changes needed. The crawl cascade is architecturally sound.
