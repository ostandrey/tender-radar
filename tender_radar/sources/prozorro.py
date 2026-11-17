"""Prozorro (Ukrainian public procurement): the API behind prozorro.gov.ua.

Endpoints used (the same ones the public site calls, no key needed):

* ``POST /api/search/tenders`` with ``{"cpv": [...], "status": [...], "page": N}``
  or ``{"text": "...", "status": [...], "page": N}``. 20 results per page,
  pages start at 1. The ``cpv`` filter is an OR over *exact* 10-char codes.
* ``GET /api/tenders/{tenderID}/details`` - full card: buyer region, CPV
  classifier, description, items.

Limit: 60 requests per minute per IP, reported in ``x-ratelimit-*`` headers.
Rate limiting and retries live in ``sources/base.py``; this module only knows
the shape of Prozorro's JSON.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..config import ACTIVE_STATUSES, API_BASE
from .base import ApiClient

_WS = re.compile(r"\s+")
_CPV_IN_TEXT = re.compile(r"(\d{8}-\d)\s*[-—–]\s*(.+)")


def clean(text: str | None) -> str:
    """Collapse whitespace; ``None`` becomes an empty string."""
    return _WS.sub(" ", text or "").strip()


@dataclass(frozen=True)
class SearchHit:
    """One row of a search result (a subset of the tender's fields)."""

    id: str
    title: str
    buyer: str
    locality: str
    deadline: str
    amount: float | None
    currency: str
    status: str


@dataclass(frozen=True)
class TenderDetails:
    """The fields we need from the details endpoint."""

    region: str = ""
    cpv_code: str = ""
    cpv_label: str = ""
    description: str = ""
    published: str = ""
    enquiry_end: str = ""
    method: str = ""
    guarantee: float | None = None
    documents: tuple[tuple[str, str], ...] = ()


def parse_search_page(data: dict[str, Any]) -> tuple[int, list[SearchHit]]:
    """Return ``(total_matches, hits_on_this_page)``. Rows without an id or title are skipped."""
    hits: list[SearchHit] = []
    for row in data.get("data") or []:
        tender_id = row.get("tenderID")
        title = clean(row.get("title"))
        if not tender_id or not title:
            continue
        buyer = row.get("procuringEntity") or {}
        value = row.get("value") or {}
        amount = value.get("amount")
        hits.append(
            SearchHit(
                id=tender_id,
                title=title,
                buyer=clean(buyer.get("name") or (buyer.get("identifier") or {}).get("legalName")),
                locality=clean((buyer.get("address") or {}).get("locality")),
                deadline=(row.get("tenderPeriod") or {}).get("endDate") or "",
                amount=float(amount) if isinstance(amount, (int, float)) else None,
                currency=value.get("currency") or "UAH",
                status=row.get("status") or "",
            )
        )
    return int(data.get("total") or 0), hits


# Prozorro procurementMethodType -> what a bidder calls it.
METHOD_LABELS = {
    "aboveThreshold": "Open tender",
    "aboveThresholdUA": "Open tender",
    "aboveThresholdEU": "Open tender (EU)",
    "belowThreshold": "Simplified procurement",
    "competitiveOrdering": "Competitive ordering",
    "competitiveDialogueUA": "Competitive dialogue",
    "negotiation": "Negotiated procedure",
    "reporting": "Direct contract",
    "priceQuotation": "Price quotation",
    "requestForProposal": "Request for proposals",
}
MAX_DOCUMENTS = 8
MAX_DESCRIPTION = 700


def _documents(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Public tender documents as (title, url), newest version of each, signatures skipped."""
    out: list[tuple[str, str]] = []
    for versions in (data.get("publicDocuments") or {}).values():
        if not versions:
            continue
        doc = versions[-1] if isinstance(versions, list) else versions
        title, url = clean(doc.get("title")), doc.get("url") or ""
        if title and url and not title.lower().endswith(".p7s"):
            out.append((title, url))
    return tuple(out[:MAX_DOCUMENTS])


def parse_details(data: dict[str, Any]) -> TenderDetails:
    """Extract region, CPV and description from a details response.

    The CPV code sits in ``generalClassifier`` ("ДК 021:2015: 72260000-5 — ...");
    older tenders carry it only in ``items[].classification``.
    """
    code = label = ""
    classifier = data.get("generalClassifier") or {}
    match = _CPV_IN_TEXT.search(classifier.get("description") or "")
    if match:
        code, label = match.group(1), clean(match.group(2))
    else:
        for item in data.get("items") or []:
            cls = item.get("classification") or {}
            if cls.get("id"):
                code, label = cls["id"], clean(cls.get("description"))
                break
    parts = [clean(data.get("description"))]
    parts += [clean(lot.get("title")) for lot in data.get("lots") or []]
    parts += [clean((item or {}).get("description")) for item in data.get("items") or []]
    address = (data.get("procuringEntity") or {}).get("address") or {}
    tender_period = data.get("tenderPeriod") or {}
    method_type = data.get("procurementMethodType") or ""
    guarantee = (data.get("guarantee") or {}).get("amount")
    description = " | ".join(dict.fromkeys(p for p in parts if p))
    return TenderDetails(
        region=clean(address.get("region")),
        cpv_code=code,
        cpv_label=label,
        description=description,
        published=tender_period.get("startDate") or data.get("noticePublicationDate") or "",
        enquiry_end=(data.get("enquiryPeriod") or {}).get("endDate") or "",
        method=METHOD_LABELS.get(method_type, method_type),
        guarantee=float(guarantee) if isinstance(guarantee, (int, float)) and guarantee > 0 else None,
        documents=_documents(data),
    )


class ProzorroSource:
    """Thin async wrapper over the two endpoints."""

    def __init__(self, api: ApiClient, base_url: str = API_BASE) -> None:
        self._api = api
        self._base = base_url.rstrip("/")

    async def search_page(self, query: dict[str, Any], page: int) -> tuple[int, list[SearchHit]]:
        """Fetch one page of results for ``query`` (``{"cpv": [...]}`` or ``{"text": "..."}``)."""
        body = {**query, "status": ACTIVE_STATUSES, "page": page}
        data = await self._api.post_json(f"{self._base}/search/tenders", json=body)
        return parse_search_page(data)

    async def details(self, tender_id: str) -> TenderDetails:
        data = await self._api.get_json(f"{self._base}/tenders/{tender_id}/details")
        return parse_details(data)
