import json

from tender_radar.__main__ import main


def test_build_site_creates_index_and_assets(tmp_path):
    out = tmp_path / "site"
    assert main(["build-site", "--out", str(out)]) == 0
    for name in ("index.html", "app.js", "style.css", "favicon.svg", ".nojekyll"):
        assert (out / name).is_file(), name
    assert "Tender Radar" in (out / "index.html").read_text(encoding="utf-8")


def test_build_site_keeps_existing_data(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tenders.json").write_text("[]", encoding="utf-8")
    main(["build-site", "--out", str(tmp_path)])
    assert (tmp_path / "data" / "tenders.json").read_text(encoding="utf-8") == "[]"


def test_collect_with_fixtures_then_second_run_is_idempotent(tmp_path, fixtures_dir):
    out = tmp_path / "data"
    args = ["collect", "--fixture-dir", str(fixtures_dir), "--out", str(out)]
    assert main(args) == 0
    first = json.loads((out / "tenders.json").read_text(encoding="utf-8"))
    assert {t["id"] for t in first} == {f"UA-2099-01-01-00000{n}-a" for n in (1, 2, 3)}

    assert main(args + ["--previous", str(out / "tenders.json")]) == 0
    second = json.loads((out / "tenders.json").read_text(encoding="utf-8"))
    assert second == first
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["counts"]["new"] == 0
