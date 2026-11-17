"""Persistence: merge today's run into the previous dataset and write the JSON files.

The dataset is one JSON file that GitHub Pages serves. The next daily run
downloads it back (``--previous URL``), so the site itself is the database.
The merge is idempotent: running it twice with the same input gives the same
output.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from .collector import RunSummary
from .config import EXPIRY_GRACE_DAYS
from .currency import RateProvider
from .models import Tender

log = logging.getLogger(__name__)

# Fields filled from the details card. A refresh from the search list leaves
# them empty, so we keep the stored values.
DETAIL_FIELDS = ("region", "cpv_code", "cpv_label", "categories", "score")


def load_previous(location: str | None, timeout: float = 20.0) -> list[Tender]:
    """Load a previous ``tenders.json`` from a file path or an http(s) URL.

    A missing file, a 404 or broken JSON is not an error: it just means
    "first run", so we return an empty list.
    """
    if not location:
        return []
    try:
        if location.startswith(("http://", "https://")):
            resp = httpx.get(location, timeout=timeout, follow_redirects=True)
            if resp.status_code == 404:
                log.info("No previous dataset at %s (404): starting fresh", location)
                return []
            resp.raise_for_status()
            raw = resp.json()
        else:
            path = Path(location)
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
        return [Tender.from_dict(row) for row in raw]
    except (httpx.HTTPError, ValueError, TypeError, OSError) as exc:
        log.warning("Could not read previous dataset %s: %s", location, exc)
        return []


def merge(previous: list[Tender], current: list[Tender], today: date,
          grace_days: int = EXPIRY_GRACE_DAYS) -> list[Tender]:
    """Combine datasets by tender id.

    * ``first_seen`` always comes from the oldest record;
    * volatile fields (status, deadline, amount) come from the newest;
    * detail fields are kept from the old record when the new one lacks them;
    * tenders whose deadline passed more than ``grace_days`` ago are dropped.
    """
    old_by_id = {t.id: t for t in previous}
    merged: dict[str, Tender] = dict(old_by_id)
    for new in current:
        old = old_by_id.get(new.id)
        if old is None:
            merged[new.id] = new
            continue
        kept = {name: getattr(old, name) for name in DETAIL_FIELDS if not getattr(new, name)}
        merged[new.id] = replace(new, first_seen=old.first_seen or new.first_seen, **kept)
    cutoff = today - timedelta(days=grace_days)
    alive = [t for t in merged.values() if not _expired(t, cutoff)]
    return sorted(alive, key=lambda t: (t.deadline or "9999", t.id))


def _expired(tender: Tender, cutoff: date) -> bool:
    deadline = _parse_date(tender.deadline)
    return deadline is not None and deadline < cutoff


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def write_dataset(out_dir: Path, tenders: list[Tender], summary: RunSummary, rates: RateProvider, *,
                  new_count: int, now: datetime | None = None) -> None:
    """Write ``tenders.json`` (list) and ``meta.json`` (run info) into ``out_dir``."""
    now = now or datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tenders.json").write_text(
        json.dumps([t.to_dict() for t in tenders], ensure_ascii=False, indent=1), encoding="utf-8")
    meta = {
        "generated_at": now.isoformat(timespec="seconds"),
        "counts": {"tenders": len(tenders), "new": new_count, "search_hits": summary.hits},
        "run": {"queries": summary.queries, "pages": summary.pages, "detail_requests": summary.detail_requests},
        "errors": summary.errors,
        "source": {
            "name": "Prozorro public search",
            "url": "https://prozorro.gov.ua",
            "rates": rates.source,
            "rates_date": rates.rates_date,
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
