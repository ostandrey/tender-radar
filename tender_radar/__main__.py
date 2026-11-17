"""Command line: ``python -m tender_radar collect|build-site``."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

import httpx

from . import config
from .collector import Collector, build_matcher
from .currency import RateProvider
from .fixtures import fixture_transport
from .site import build_site
from .sources.base import ApiClient, RateLimiter
from .sources.prozorro import ProzorroSource
from .store import load_previous, merge, write_dataset

log = logging.getLogger("tender_radar")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tender_radar", description="Daily radar of Ukrainian public IT tenders.")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="fetch tenders from Prozorro and write tenders.json + meta.json")
    collect.add_argument("--previous", help="path or URL of the previously published tenders.json")
    collect.add_argument("--max-pages", type=int, default=config.MAX_PAGES_PER_QUERY,
                         help="pages (20 tenders each) to read per search query")
    collect.add_argument("--out", type=Path, default=Path("site/data"), help="output folder for the JSON files")
    collect.add_argument("--fixture-dir", type=Path, help="offline mode: answer from JSON files in this folder")

    build = sub.add_parser("build-site", help="copy the static website into the output folder")
    build.add_argument("--out", type=Path, default=Path("site"), help="site folder (data/ inside it is kept)")
    build.add_argument("--base-url", default="", help="public URL of the site, for link previews and sitemap")
    return parser


async def run_collect(args: argparse.Namespace) -> int:
    """Run one collection and write the dataset. Returns the process exit code."""
    today = date.today()
    previous = load_previous(args.previous)
    transport = fixture_transport(args.fixture_dir) if args.fixture_dir else None
    headers = {"user-agent": config.USER_AGENT, "accept": "application/json"}
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT, headers=headers, transport=transport) as client:
        rates = RateProvider()
        await rates.load(client)
        limiter = RateLimiter(config.REQUESTS_PER_MINUTE)
        api = ApiClient(client, limiter, retries=config.MAX_RETRIES, backoff=config.BACKOFF_BASE)
        collector = Collector(ProzorroSource(api), rates, build_matcher(),
                              known_ids={t.id for t in previous if t.published}, today=today, max_pages=args.max_pages)
        current = await collector.collect()

    previous_ids = {t.id for t in previous}
    tenders = merge(previous, current, today)
    new_count = sum(1 for t in current if t.id not in previous_ids)
    write_dataset(args.out, tenders, collector.summary, rates, new_count=new_count)

    summary = collector.summary
    print(f"tenders: {len(tenders)} (new: {new_count}, search hits: {summary.hits}); "
          f"requests: {api.request_count}; errors: {len(summary.errors)}")
    for message in summary.errors[:10]:
        print(f"  error: {message}")
    # A run where every query failed has produced nothing useful: fail the CI job.
    return 1 if summary.queries and summary.pages == 0 else 0


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request is noise
    if args.command == "collect":
        return asyncio.run(run_collect(args))
    files = build_site(args.out, base_url=args.base_url)
    print(f"site built in {args.out} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
