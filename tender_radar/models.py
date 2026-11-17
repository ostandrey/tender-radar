"""Data model: the ``Tender`` record and URL helpers."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import SITE_BASE

_TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|yclid|mc_cid|mc_eid|_ga|ref)$", re.I)


def strip_tracking(url: str) -> str:
    """Remove ``utm_*``, ``gclid`` and similar parameters; keep everything else."""
    url = (url or "").strip()
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not _TRACKING_PARAMS.match(k)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def tender_url(tender_id: str) -> str:
    """Public page of a tender on prozorro.gov.ua."""
    return f"{SITE_BASE}/tender/{tender_id}"


@dataclass
class Tender:
    """One public tender, normalised from the Prozorro API.

    Dates are ISO strings so the record maps 1:1 to JSON.
    """

    id: str  # tenderID, e.g. "UA-2026-11-16-015140-a"
    title: str
    buyer: str = ""
    region: str = ""  # oblast of the buyer, from the details endpoint
    cpv_code: str = ""
    cpv_label: str = ""
    categories: list[str] = field(default_factory=list)
    amount: float | None = None  # in the tender's own currency
    currency: str = "UAH"
    amount_uah: float | None = None
    deadline: str = ""  # tenderPeriod.endDate, ISO 8601 with offset
    status: str = ""
    url: str = ""
    first_seen: str = ""  # YYYY-MM-DD, the first run that saw this tender
    score: int = 0  # relevance 0..100

    def __post_init__(self) -> None:
        self.url = strip_tracking(self.url) or tender_url(self.id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tender":
        """Build from JSON, ignoring unknown keys (so old datasets keep loading)."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})
