import json
from datetime import date, datetime, timezone

import httpx

from tender_radar.collector import RunSummary
from tender_radar.currency import RateProvider
from tender_radar.models import Tender
from tender_radar.store import load_previous, merge, write_dataset

TODAY = date(2099, 1, 10)


def make(tid, deadline="2099-02-01T00:00:00+02:00", **kw):
    return Tender(id=tid, title=f"title {tid}", deadline=deadline, **kw)


def test_merge_keeps_first_seen_and_detail_fields_but_updates_volatile_ones():
    old = make("A", first_seen="2099-01-01", region="Oblast", categories=["Web"], score=80,
               amount=1.0, status="active.enquiries")
    new = make("A", first_seen="2099-01-10", amount=2.0, status="active.tendering")  # search refresh: no details
    [result] = merge([old], [new], TODAY)
    assert result.first_seen == "2099-01-01"
    assert result.region == "Oblast" and result.categories == ["Web"] and result.score == 80
    assert result.amount == 2.0 and result.status == "active.tendering"


def test_merge_adds_new_and_keeps_tenders_missing_from_this_run():
    result = merge([make("A")], [make("B", first_seen="2099-01-10")], TODAY)
    assert {t.id for t in result} == {"A", "B"}


def test_merge_is_idempotent():
    previous = [make("A", first_seen="2099-01-01", score=70)]
    current = [make("A", first_seen="2099-01-10"), make("B", first_seen="2099-01-10")]
    once = merge(previous, current, TODAY)
    twice = merge(once, current, TODAY)
    assert once == twice


def test_expiry_drops_old_deadlines_only_after_grace_period():
    gone = make("gone", deadline="2099-01-01T00:00:00+02:00")  # 9 days ago
    recent = make("recent", deadline="2099-01-09T00:00:00+02:00")  # 1 day ago: inside the grace period
    undated = make("undated", deadline="")
    result = merge([gone, recent, undated], [], TODAY, grace_days=2)
    assert {t.id for t in result} == {"recent", "undated"}


def test_result_is_sorted_by_deadline():
    result = merge([], [make("late", "2099-05-01T00:00:00+02:00"), make("soon", "2099-02-01T00:00:00+02:00")], TODAY)
    assert [t.id for t in result] == ["soon", "late"]


def test_load_previous_from_path_and_missing_file(tmp_path):
    path = tmp_path / "tenders.json"
    path.write_text(json.dumps([make("A").to_dict()]), encoding="utf-8")
    assert [t.id for t in load_previous(str(path))] == ["A"]
    assert load_previous(str(tmp_path / "nope.json")) == []
    assert load_previous(None) == []


def test_load_previous_survives_broken_json(tmp_path):
    path = tmp_path / "tenders.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_previous(str(path)) == []


def test_load_previous_from_url_treats_404_as_first_run(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(404, request=httpx.Request("GET", url)))
    assert load_previous("https://example.github.io/repo/data/tenders.json") == []


def test_load_previous_from_url_reads_json(monkeypatch):
    body = [make("A").to_dict()]
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(200, json=body, request=httpx.Request("GET", url)))
    assert [t.id for t in load_previous("https://example.github.io/repo/data/tenders.json")] == ["A"]


def test_write_dataset_writes_tenders_and_meta(tmp_path):
    summary = RunSummary(queries=2, pages=3, hits=5, detail_requests=4, errors=["boom"])
    now = datetime(2099, 1, 10, 4, 30, tzinfo=timezone.utc)
    rates = RateProvider({"EUR": 40.0}, source="NBU")
    write_dataset(tmp_path / "data", [make("A")], summary, rates, new_count=1, now=now)
    tenders = json.loads((tmp_path / "data" / "tenders.json").read_text(encoding="utf-8"))
    meta = json.loads((tmp_path / "data" / "meta.json").read_text(encoding="utf-8"))
    assert tenders[0]["id"] == "A"
    assert meta["generated_at"] == "2099-01-10T04:30:00+00:00"
    assert meta["counts"] == {"tenders": 1, "new": 1, "search_hits": 5}
    assert meta["errors"] == ["boom"]
