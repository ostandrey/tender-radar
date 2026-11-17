"""Collect IT tenders from Prozorro and normalise them into ``Tender`` records.

Flow of one run::

    search by CPV codes (+ a few text queries), page by page
        -> merge hits by tender id
        -> fetch the details card only for tenders we have not seen before
        -> convert the amount to UAH, tag categories, score relevance

Failure isolation: a failed page or details call is recorded in
``RunSummary.errors`` and the run goes on. Only the caller decides whether a
run with many errors is acceptable.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

import httpx

from .config import (CATEGORIES, CPV_CODES, DETAIL_CONCURRENCY, FALLBACK_CATEGORY, MAX_PAGES_PER_QUERY,
                      PAGE_SIZE, TEXT_ONLY_MIN_SCORE, TEXT_QUERIES)
from .currency import RateProvider
from .models import Tender, tender_url
from .sources.prozorro import MAX_DESCRIPTION, ProzorroSource, SearchHit, TenderDetails
from .textmatch import KeywordMatcher

log = logging.getLogger(__name__)

CPV_QUERY_CHUNK = 25  # codes per search request, keeps request bodies small


@dataclass
class RunSummary:
    """What happened during one collection run (written to meta.json)."""

    queries: int = 0
    pages: int = 0
    hits: int = 0
    detail_requests: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _Hit:
    """A search hit plus how it was found."""

    hit: SearchHit
    via_cpv: bool  # found by a CPV query (the buyer itself classified it as IT)


def build_matcher() -> KeywordMatcher:
    return KeywordMatcher({c.name: c.terms for c in CATEGORIES})


def build_queries(cpv_codes: Iterable[str] = CPV_CODES, text_queries: Iterable[str] = TEXT_QUERIES
                  ) -> list[tuple[dict, bool]]:
    """Return ``[(search_query, is_cpv_query), ...]``."""
    codes = list(cpv_codes)
    queries: list[tuple[dict, bool]] = [
        ({"cpv": codes[i:i + CPV_QUERY_CHUNK]}, True) for i in range(0, len(codes), CPV_QUERY_CHUNK)
    ]
    queries += [({"text": text}, False) for text in text_queries]
    return queries


def categories_for(text: str, cpv_code: str, matcher: KeywordMatcher) -> tuple[list[str], int]:
    """Tag a tender and score it.

    Categories come from keywords in the text and from the CPV code prefix.
    Score (0..100): 50 for an IT CPV code plus 15 per distinct keyword, max 50.
    """
    result = matcher.match(text)
    names = set(result.groups)
    for category in CATEGORIES:
        if cpv_code and cpv_code.startswith(category.cpv_prefixes):
            names.add(category.name)
    ordered = [c.name for c in CATEGORIES if c.name in names] or [FALLBACK_CATEGORY]
    cpv_points = 50 if cpv_code in CPV_CODES else 0
    return ordered, min(100, cpv_points + min(50, 15 * len(set(result.terms))))


class Collector:
    """Runs the search and builds ``Tender`` records."""

    def __init__(self, source: ProzorroSource, rates: RateProvider, matcher: KeywordMatcher, *,
                 known_ids: set[str] | None = None, today: date | None = None,
                 max_pages: int = MAX_PAGES_PER_QUERY, concurrency: int = DETAIL_CONCURRENCY,
                 queries: list[tuple[dict, bool]] | None = None) -> None:
        self._source = source
        self._rates = rates
        self._matcher = matcher
        self._known = known_ids or set()
        self._today = (today or date.today()).isoformat()
        self._max_pages = max_pages
        self._semaphore = asyncio.Semaphore(concurrency)
        self._queries = queries if queries is not None else build_queries()
        self.summary = RunSummary()

    async def collect(self) -> list[Tender]:
        """Run every query, fetch details for new tenders, return normalised tenders."""
        found: dict[str, _Hit] = {}
        for query, is_cpv in self._queries:
            self.summary.queries += 1
            for hit in await self._search_all(query):
                entry = found.get(hit.id)
                if entry is None:
                    found[hit.id] = _Hit(hit, is_cpv)
                elif is_cpv:
                    entry.via_cpv = True
        self.summary.hits = len(found)

        wanted = [e for e in found.values() if self._wants_details(e)]
        details = await asyncio.gather(*(self._fetch_details(e.hit.id) for e in wanted))
        by_id = {e.hit.id: d for e, d in zip(wanted, details)}

        tenders = [self._build(e, by_id.get(e.hit.id)) for e in found.values()]
        return [t for t in tenders if t is not None]

    # --- search -----------------------------------------------------------
    async def _search_all(self, query: dict) -> list[SearchHit]:
        """Fetch all pages of one query (up to ``max_pages``); a failed page is skipped."""
        hits: list[SearchHit] = []
        total_pages = 1
        page = 1
        while page <= min(total_pages, self._max_pages):
            try:
                total, rows = await self._source.search_page(query, page)
            except (httpx.HTTPError, ValueError) as exc:
                self._error(f"search {_describe(query)} page {page}: {_short(exc)}")
                page += 1
                continue
            self.summary.pages += 1
            hits.extend(rows)
            total_pages = max(1, -(-total // PAGE_SIZE))
            page += 1
        return hits

    # --- details ----------------------------------------------------------
    def _wants_details(self, entry: _Hit) -> bool:
        """Only new tenders need the details card. Text-only hits must match a keyword in the title."""
        if entry.hit.id in self._known:
            return False
        return entry.via_cpv or bool(self._matcher.match(entry.hit.title).terms)

    async def _fetch_details(self, tender_id: str) -> TenderDetails | None:
        async with self._semaphore:
            self.summary.detail_requests += 1
            try:
                return await self._source.details(tender_id)
            except (httpx.HTTPError, ValueError) as exc:
                self._error(f"details {tender_id}: {_short(exc)}")
                return None

    # --- normalisation ----------------------------------------------------
    def _build(self, entry: _Hit, details: TenderDetails | None) -> Tender | None:
        """Build a Tender, or ``None`` if it is not IT-related."""
        hit = entry.hit
        if hit.id in self._known:  # already stored: the store keeps its details, we refresh volatile fields
            return self._make(hit, TenderDetails(), [], 0)
        details = details or TenderDetails()
        categories, score = categories_for(f"{hit.title} {details.description}", details.cpv_code, self._matcher)
        if not entry.via_cpv and score < TEXT_ONLY_MIN_SCORE:
            return None
        if not details.cpv_code and entry.via_cpv:
            score = max(score, 50)  # details failed, but the buyer filed it under an IT CPV code
        return self._make(hit, details, categories, score)

    def _make(self, hit: SearchHit, details: TenderDetails, categories: list[str], score: int) -> Tender:
        return Tender(
            id=hit.id,
            title=hit.title,
            buyer=hit.buyer,
            region=details.region,
            cpv_code=details.cpv_code,
            cpv_label=details.cpv_label or CPV_CODES.get(details.cpv_code, ""),
            categories=categories,
            amount=hit.amount,
            currency=hit.currency,
            amount_uah=self._rates.to_uah(hit.amount, hit.currency),
            deadline=hit.deadline,
            status=hit.status,
            url=tender_url(hit.id),
            first_seen=self._today,
            score=score,
            published=details.published,
            enquiry_end=details.enquiry_end,
            method=details.method,
            guarantee=details.guarantee,
            description=details.description[:MAX_DESCRIPTION],
            documents=[{"title": t, "url": u} for t, u in details.documents],
        )

    def _error(self, message: str) -> None:
        log.warning(message)
        self.summary.errors.append(message)


def _describe(query: dict) -> str:
    return f"text={query['text']!r}" if "text" in query else f"cpv[{len(query.get('cpv', []))}]"


def _short(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:120]}"
