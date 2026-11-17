"""Offline mode: serve Prozorro-shaped JSON from a folder instead of the network.

Used by ``collect --fixture-dir`` (demos, CI smoke tests). Layout of the folder:

* ``search_page<N>.json``: answer to a CPV search for page N (missing = empty page);
* ``details_<tenderID>.json``: answer of the details endpoint;
* ``nbu.json``: answer of the NBU exchange-rate endpoint.

Text searches always get an empty page: the folder models the CPV query only.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

EMPTY_PAGE = {"page": 1, "per_page": 20, "total": 0, "data": []}


def fixture_transport(folder: Path) -> httpx.MockTransport:
    """Build an ``httpx`` transport that answers from ``folder``."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "bank.gov.ua":
            return _file(folder / "nbu.json", [])
        if path.endswith("/search/tenders"):
            body = json.loads(request.content or b"{}")
            if "cpv" not in body:
                return httpx.Response(200, json=EMPTY_PAGE)
            return _file(folder / f"search_page{body.get('page', 1)}.json", EMPTY_PAGE)
        if path.endswith("/details"):
            tender_id = path.split("/")[-2]
            return _file(folder / f"details_{tender_id}.json", None)
        return httpx.Response(404, json={"message": "not in fixtures"})

    return httpx.MockTransport(handler)


def _file(path: Path, default: object) -> httpx.Response:
    if path.exists():
        return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))
    if default is None:
        return httpx.Response(404, json={"message": "not found"})
    return httpx.Response(200, json=default)
