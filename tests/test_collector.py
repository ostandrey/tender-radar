import asyncio
import json
from datetime import date

import httpx

from tender_radar.collector import Collector, build_matcher, build_queries, categories_for
from tender_radar.currency import RateProvider
from tender_radar.fixtures import fixture_transport
from tender_radar.sources.base import ApiClient, RateLimiter
from tender_radar.sources.prozorro import ProzorroSource

TODAY = date(2099, 1, 5)
CPV_QUERY = [({"cpv": ["72413000-8"]}, True)]


def row(n: int) -> dict:
    return {"tenderID": f"UA-{n}", "title": f"Розробка веб-сайту {n}", "status": "active.tendering",
            "procuringEntity": {"name": "Buyer"}, "tenderPeriod": {"endDate": "2099-03-01T00:00:00+02:00"},
            "value": {"amount": 1000.0 * n, "currency": "UAH"}}


def run_collector(transport, fake_sleep, *, queries=None, known=None, max_pages=5):
    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            limiter = RateLimiter(1000, sleep=fake_sleep)
            api = ApiClient(client, limiter, retries=3, backoff=1.0, sleep=fake_sleep)
            collector = Collector(ProzorroSource(api), RateProvider({"EUR": 40.0}), build_matcher(),
                                  known_ids=known, today=TODAY, max_pages=max_pages, queries=queries)
            return await collector.collect(), collector.summary

    return asyncio.run(go())


def is_details(request: httpx.Request) -> bool:
    return request.url.path.endswith("/details")


def test_pagination_reads_every_page(fake_sleep):
    pages = {1: [row(n) for n in range(1, 21)], 2: [row(n) for n in range(21, 31)]}
    requested = []

    def handler(request):
        if is_details(request):
            return httpx.Response(200, json={"generalClassifier": {"description": "ДК 021:2015: 72413000-8 — Web"}})
        body = json.loads(request.content)
        requested.append(body["page"])
        return httpx.Response(200, json={"total": 30, "data": pages[body["page"]]})

    tenders, summary = run_collector(httpx.MockTransport(handler), fake_sleep, queries=CPV_QUERY)
    assert requested == [1, 2]
    assert len(tenders) == 30 and summary.pages == 2 and summary.errors == []


def test_max_pages_limits_reading(fake_sleep):
    requested = []

    def handler(request):
        if is_details(request):
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        requested.append(body["page"])
        return httpx.Response(200, json={"total": 100, "data": [row(body["page"])]})

    run_collector(httpx.MockTransport(handler), fake_sleep, queries=CPV_QUERY, max_pages=2)
    assert requested == [1, 2]


def test_retry_on_503_then_success_with_backoff(fake_sleep):
    attempts = {"n": 0}

    def handler(request):
        if is_details(request):
            return httpx.Response(200, json={})
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"total": 1, "data": [row(1)]})

    tenders, summary = run_collector(httpx.MockTransport(handler), fake_sleep, queries=CPV_QUERY)
    assert len(tenders) == 1 and summary.errors == []
    assert fake_sleep.calls[:2] == [1.0, 2.0]  # exponential: 1s, 2s


def test_429_honours_retry_after(fake_sleep):
    attempts = {"n": 0}

    def handler(request):
        if is_details(request):
            return httpx.Response(200, json={})
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, json={"total": 1, "data": [row(1)]})

    tenders, _ = run_collector(httpx.MockTransport(handler), fake_sleep, queries=CPV_QUERY)
    assert len(tenders) == 1
    assert 7.0 in fake_sleep.calls


def test_failed_page_is_recorded_and_does_not_kill_the_run(fake_sleep):
    def handler(request):
        if is_details(request):
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        if body["page"] == 2:
            return httpx.Response(500)  # every retry fails
        return httpx.Response(200, json={"total": 60, "data": [row(body["page"])]})

    tenders, summary = run_collector(httpx.MockTransport(handler), fake_sleep, queries=CPV_QUERY)
    assert {t.id for t in tenders} == {"UA-1", "UA-3"}
    assert len(summary.errors) == 1 and "page 2" in summary.errors[0]


def test_details_only_for_unknown_tenders(fake_sleep):
    detail_calls = []

    def handler(request):
        if is_details(request):
            detail_calls.append(request.url.path)
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"total": 2, "data": [row(1), row(2)]})

    tenders, _ = run_collector(httpx.MockTransport(handler), fake_sleep, queries=CPV_QUERY, known={"UA-1"})
    assert len(detail_calls) == 1 and "UA-2" in detail_calls[0]
    assert {t.id for t in tenders} == {"UA-1", "UA-2"}  # the known one is still refreshed from the search


def test_fixture_run_builds_normalised_tenders(fixtures_dir, fake_sleep):
    tenders, summary = run_collector(fixture_transport(fixtures_dir), fake_sleep, queries=CPV_QUERY)
    by_id = {t.id: t for t in tenders}
    web = by_id["UA-2099-01-01-000001-a"]
    assert web.region == "Вигаданська область"
    assert web.cpv_code == "72413000-8" and "Web" in web.categories
    assert web.amount_uah == 1200000.0 and web.first_seen == "2099-01-05"
    crm = by_id["UA-2099-01-01-000002-a"]
    assert crm.currency == "EUR" and crm.amount_uah == 2000000.0  # 50 000 EUR * 40
    assert "Support & licences" in crm.categories
    # details are missing for tender 3: it is kept (found by a CPV query) and the error is recorded
    assert "UA-2099-01-01-000003-a" in by_id
    assert any("000003" in e for e in summary.errors)


def test_text_only_hit_needs_keywords(fake_sleep):
    off_topic = dict(row(1), title="Закупівля канцелярського паперу")

    def handler(request):
        if is_details(request):
            return httpx.Response(200, json={"description": "папір"})
        return httpx.Response(200, json={"total": 1, "data": [off_topic]})

    tenders, summary = run_collector(httpx.MockTransport(handler), fake_sleep, queries=[({"text": "CRM"}, False)])
    assert tenders == [] and summary.detail_requests == 0


def test_categories_and_score():
    matcher = build_matcher()
    names, score = categories_for("Хостинг та хмарні послуги", "72415000-2", matcher)
    assert "Cloud & hosting" in names
    assert score >= 50  # IT CPV code plus keywords
    names, score = categories_for("Папір", "", matcher)
    assert names == ["Other IT"] and score == 0


def test_build_queries_chunks_cpv_codes():
    queries = build_queries([f"7{n:07d}-0" for n in range(60)], ["CRM"])
    assert [len(q["cpv"]) for q, is_cpv in queries if is_cpv] == [25, 25, 10]
    assert queries[-1] == ({"text": "CRM"}, False)
