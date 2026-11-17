# Design — Tender Radar

Claude · 2026-11-17 · built with the `ui-design` skill after the Owner rejected the first dark «radar» look («нейрослоп», no pagination, no way to shortlist). Approved direction: Owner «так», 2026-11-17.

## Direction

- **Product:** a daily board of open Ukrainian public IT tenders (Prozorro) for IT companies and freelancers who bid: find → compare → shortlist → export.
- **Character:** clear, businesslike, trustworthy, fast to scan — like a good public service. **Not:** a dark neon dashboard.
- **World:** procurement portals and job boards — light, document-like, data in rows.
- **Moments (the only loud parts):** the deadline (colour warms as it nears) and the shortlist.
- **Signature:** the **deadline ruler** in every row — a bar from «bids open» to the deadline, filled to today, coloured by urgency.

## References (patterns taken, never copied)

| Reference | Take |
|---|---|
| prozorro.gov.ua search | facets as filters, active filters as removable tags + «clear», result count, sort on the right, expected value on the right |
| UK Find a Tender / Contracts Finder | left filter panel with sections and per-option counts, a hint under search saying what it searches |
| SAM.gov | «Showing 1–25 of N results», sort top-right, key dates in a right column |
| Djinni | clean type, meta line joined with «·», amount right-aligned |
| GOV.UK Design System (OGL v3) | table and pagination patterns |

Screenshots: Owner's private folder `projects/career/private/` (not in this repo — third-party pages).

## Tokens

Font **Onest** (OFL, `tender_radar/web/fonts/OFL.txt`, self-hosted, Cyrillic + Latin), tabular numbers. Ink `#101828`, muted `#667085`, lines `#E4E7EC`, background `#F5F6F8`, surface white. One accent `#1F4FD8` (links, primary button, focus). Urgency: hot `#B42318` (≤ 2 days), warm `#B54708` / bar `#F79009` (≤ 7 days), calm grey. New `#067647`. Star `#E68A00`. Radius 12 / 8. Shadows barely there.

## Screen spec

### Screen: Tender list — operate
Data: ~220 open tenders today; a few hundred at most (one country, IT only).
- **Summary:** 4 stats, each a shortcut: open tenders (clears filters), total value (sorts by budget), closing within 7 days (filter), new since your last visit (filter). On the first day of data, when ≥ 90% is new, the 4th stat says «Tracking since …» and no «New» badges are shown.
- **Views:** tabs «All tenders N | Shortlist N».
- **List:** **pagination**, 25 / 50 / 100 per page, «Showing 1–25 of 218 open tenders», ‹ Prev 1 … 4 5 6 … 9 Next ›; on phones «‹ Prev · Page 2 of 9 · Next ›». Row: star · title (2 lines) + buyer · region · procedure + category chips + CPV · expected value (₴, compact; exact in tooltip; original currency if not UAH) · time left + deadline + deadline ruler. Whole title opens the details.
- **Sort:** deadline soonest (default) · budget largest · newest (bids opened) · relevance.
- **Filters (left panel; bottom sheet under 900 px):** search (title, buyer, CPV; 150 ms debounce) · category · deadline (radio) · budget buckets · procedure · buyer region (top 8 + «show all»). Every option shows a count computed against the other active filters; zero options are greyed, not hidden. Active filters as tags with «Clear all».
- **URL state:** `q, cat, dl, budget, proc, region, new, sort, per, page, view=shortlist, id` — refresh, back and shared links keep the place; page changes and the drawer push history.
- **Shortlist:** star per row and in the details; stored in this browser (`localStorage` with a snapshot of the tender), survives the daily refresh; tenders that disappear stay with «No longer listed», closed ones with «Closed». Summary bar: count · total value · next deadline · closed count; Copy list · Export CSV · Clear shortlist (with Undo).
- **Details drawer (right, 560 px; full screen on phones):** categories, title, buyer · region, actions (Open on Prozorro · Add to shortlist · Copy link), facts grid (expected value, time left, procedure, bid security, CPV, Prozorro ID), timeline (bids open → questions until → deadline, next step highlighted), what the buyer needs (only if it adds to the title), tender documents (links). Esc and scrim close it; focus returns to the row.
- **Export:** CSV of the filtered results (all pages) or of the shortlist; UTF-8 BOM for Excel; cells starting with `= + - @` are neutralised.
- **States:** loading skeleton rows · error with «Try again» (filters kept) · no data yet · no results with «Clear all filters» · empty shortlist with «Browse tenders» · stale banner when the data is older than 36 h.
- Keyboard: everything is a button or link; Esc closes drawer/sheet. Narrow: see above; no horizontal scroll at 375 px (checked).
- Motion: drawer slide 200 ms ease-out; star pop 180 ms; skeleton shimmer; all off under `prefers-reduced-motion`.

## Checked (2026-11-17)

Playwright at 1440 and 375: list, drawer, shortlist with 3 items, no results, filtered page 2 (URL `?cat=Software+dev&dl=14&page=2`), filter sheet, mobile drawer; no console errors, no horizontal overflow. Fixed after review: toast showed «null», «New» on every row on day one, buyer names taking 5 lines on phones, a description that only repeated the title.
