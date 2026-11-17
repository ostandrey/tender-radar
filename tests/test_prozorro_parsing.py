import json

from tender_radar.sources.prozorro import clean, parse_details, parse_search_page


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


def test_parse_search_page(fixtures_dir):
    total, hits = parse_search_page(load(fixtures_dir, "search_page1.json"))
    assert total == 4
    assert len(hits) == 3  # the row without a title is skipped
    first = hits[0]
    assert first.id == "UA-2099-01-01-000001-a"
    assert first.buyer == "Тестова міська рада"
    assert first.locality == "Тестоград"
    assert first.amount == 1200000.0 and first.currency == "UAH"
    assert first.deadline.startswith("2099-02-10")
    assert hits[1].currency == "EUR"


def test_parse_search_page_tolerates_empty_or_odd_payloads():
    assert parse_search_page({}) == (0, [])
    odd = {"total": 1, "data": [{"tenderID": "X", "title": "t", "value": None}]}
    assert parse_search_page(odd)[1][0].amount is None


def test_parse_details_reads_cpv_region_and_description(fixtures_dir):
    details = parse_details(load(fixtures_dir, "details_UA-2099-01-01-000001-a.json"))
    assert details.cpv_code == "72413000-8"
    assert details.cpv_label == "Послуги з веб-дизайну"
    assert details.region == "Вигаданська область"
    assert "інтернет-порталу" in details.description


def test_parse_details_falls_back_to_item_classification():
    data = {"items": [{"classification": {"id": "48810000-9", "description": "Information systems"}}]}
    details = parse_details(data)
    assert (details.cpv_code, details.cpv_label) == ("48810000-9", "Information systems")


def test_clean_collapses_whitespace():
    assert clean("  a \n\t b ") == "a b"
    assert clean(None) == ""
