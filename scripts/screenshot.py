"""Take README screenshots of the built site with Playwright.

Usage (needs Playwright + Chromium; the repo itself does not depend on them):
    python scripts/screenshot.py [--site site] [--out docs/screens]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWS = {"desktop-1440.png": (1440, 1000), "mobile-375.png": (375, 812)}


def serve(folder: Path) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--out", type=Path, default=Path("docs/screens"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    server = serve(args.site)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, (width, height) in VIEWS.items():
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(url)
                page.wait_for_selector(".card")
                page.wait_for_timeout(700)  # let the entrance animation finish
                page.screenshot(path=str(args.out / name))
                overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                print(f"{name}: horizontal overflow = {overflow}")
                page.close()
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
