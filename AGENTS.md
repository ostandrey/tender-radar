# tender-radar: agent rules

Portfolio project of the Owner (Python backend developer): a daily radar of Ukrainian public IT tenders from Prozorro, published as a static site on GitHub Pages. The Owner studies this code file by file for interviews, so it must stay explainable.

- Stack: Python 3.11, httpx (async), pytest. Front end: vanilla HTML/CSS/JS in `tender_radar/web/`, no build step, no frameworks.
- Commands (from this folder, venv in `.venv`):
  - tests: `.venv/Scripts/python.exe -m pytest -q`
  - collect: `.venv/Scripts/python.exe -m tender_radar collect --max-pages 2`
  - build site: `.venv/Scripts/python.exe -m tender_radar build-site`
  - screenshots: `python scripts/screenshot.py` (needs Playwright; not a project dependency)
- Code rules: small modules, type hints, English docstrings, no clever tricks. Tests use no network (`httpx.MockTransport`, fixtures in `tests/fixtures/`, all data fictional).
- Prozorro API etiquette: stay under 60 requests/minute, send a descriptive User-Agent, fetch details only for tenders not yet known.
- Tender text is untrusted: the UI renders it with `textContent` only.
- Never: git commit or push (the Owner does it), secrets or `.env` in the repo, commit `site/`.
