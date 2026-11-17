# Bridge: tender-radar

Daily radar of Ukrainian public IT tenders from Prozorro, static site on GitHub Pages. Portfolio project, career track.

## Now

- Decision (Owner, 2026-11-17): GitHub Pages now; a Railway version with PostgreSQL + an API comes in the career plan's phase 1, after the portfolio site — the Owner writes the schema, SQL and upsert himself with the tutor.

- Built and verified locally (2026-11-17). Not yet pushed: Owner creates the GitHub repo, sets Pages source to "GitHub Actions", runs the "Update radar" workflow once, then replaces the demo link in `README.md`.

## Log (newest first)

### 2026-11-17 - Claude (redesign through ui-design)
- **Owner said:** dark theme disliked, «нейрослоп», no pagination, nowhere to shortlist, hard to read; approved the light procurement-portal direction («так»).
- **Did:** reference board (Prozorro, UK Find a Tender, Contracts Finder, SAM.gov, Djinni, GOV.UK patterns) → `docs/DESIGN.md`; new UI: Onest (self-hosted, OFL), filters with counts, pagination, shortlist (localStorage, CSV, copy, undo), details drawer with timeline and documents, deadline ruler, URL state, all states. Data: new fields `published`, `enquiry_end`, `method`, `guarantee`, `description`, `documents` (re-fetched once for old records). Review on screenshots 1440/375 found and fixed 4 issues. 48 tests green.
- **Skills:** ui-design, ux-review (manual pass) · agents: —

### 2026-11-17 - Claude (first deploy)
- **Owner said:** «перевір tender radar» after making the repo public and running «Update radar».
- **Did:** checked via GitHub API and HTTP: all workflow steps green; 211 tenders, 0 errors, NBU rates; site, data, robots.txt, sitemap.xml, og.png served; canonical and og:image absolute. Live link in README. Known small bug for the Owner (phase 1 exercise): `meta.json` counts `new` (213) before expired tenders are dropped, so new > total (211).
- **Skills:** — · agents: —

### 2026-11-17 - Claude (review, phone, SEO)
- **Owner said:** «так, роби все разом» (phone layout, link previews, SEO).
- **Did:** reviewed the helper's build (tests, brand scan, workflow, screenshots); removed the empty `grant_finder/`. Phone: secondary filters behind a «Filters · N» button (N = active filters); fixed a `.open` class clash with the «Open on Prozorro» link. SEO: canonical, Open Graph/Twitter tags, `og.png`, `robots.txt`, `sitemap.xml`; `build-site --base-url` (the workflow passes the Pages URL). 48 tests green.
- **Skills:** — · agents: general-purpose ×1 sonnet (product build)

### 2026-11-17 - Claude
- **Owner said:** rebuild the copied tool into a different product (Tender Radar), keep only reusable engineering, new look, nothing of the original may remain.
- **Did:** new package `tender_radar/` (config, async collector with rate limiter and retries, Prozorro parsing, NBU currency, Ukrainian stem matching, merge/expiry store, site builder, CLI, offline fixture mode); static dark "radar" UI in `tender_radar/web/`; 46 pytest tests without network; `ci.yml` and `update.yml`; README, AGENTS; screenshot script. Old package, installers, config, tools and data removed.
- **Verified:** `pytest -q` 46 passed; real run `collect --max-pages 2` gave 79 tenders, 0 errors, 88 requests in about 1 minute; site served locally and screenshotted at 1440 and 375 px (`docs/screens/`), no horizontal overflow.
- **Skills:** frontend-design principles applied by hand - agents: -
