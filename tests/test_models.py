from tender_radar.models import Tender, strip_tracking, tender_url


def test_strip_tracking_keeps_real_parameters():
    url = "https://example.org/page?id=7&utm_source=x&gclid=abc"
    assert strip_tracking(url) == "https://example.org/page?id=7"
    assert strip_tracking("https://example.org/page") == "https://example.org/page"


def test_url_defaults_to_prozorro_page():
    tender = Tender(id="UA-1", title="t")
    assert tender.url == tender_url("UA-1") == "https://prozorro.gov.ua/uk/tender/UA-1"


def test_from_dict_ignores_unknown_keys_and_round_trips():
    tender = Tender(id="UA-1", title="t", amount=5.0, categories=["Web"])
    data = {**tender.to_dict(), "legacy_field": 1}
    assert Tender.from_dict(data) == tender
