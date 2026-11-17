"""New detail fields: published date, procedure label, bid security, documents (signatures skipped)."""
from tender_radar.sources.prozorro import parse_details


def test_details_fields_for_the_drawer():
    data = {
        "tenderPeriod": {"startDate": "2026-11-02T13:27:33+02:00", "endDate": "2026-11-18T00:00:00+02:00"},
        "enquiryPeriod": {"endDate": "2026-11-15T00:00:00+02:00"},
        "procurementMethodType": "aboveThreshold",
        "guarantee": {"amount": 150000, "currency": "UAH"},
        "publicDocuments": {
            "a": [{"title": "sign.p7s", "url": "https://docs.example/a"}],
            "b": [{"title": "Old spec.docx", "url": "https://docs.example/b1"}, {"title": "Spec.docx", "url": "https://docs.example/b2"}],
        },
        "procuringEntity": {"address": {"region": "м. Київ"}},
    }
    d = parse_details(data)
    assert d.published.startswith("2026-11-02")
    assert d.enquiry_end.startswith("2026-11-15")
    assert d.method == "Open tender"
    assert d.guarantee == 150000
    assert d.documents == (("Spec.docx", "https://docs.example/b2"),)  # newest version, no signature file


def test_unknown_method_and_no_guarantee():
    d = parse_details({"procurementMethodType": "somethingNew", "guarantee": {"amount": 0}})
    assert d.method == "somethingNew" and d.guarantee is None and d.documents == ()
