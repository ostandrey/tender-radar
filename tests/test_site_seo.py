"""Link preview tags, robots.txt and sitemap.xml from build-site."""
from tender_radar.site import build_site


def test_base_url_goes_into_preview_tags_and_sitemap(tmp_path):
    build_site(tmp_path, base_url="https://someone.github.io/tender-radar")
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'property="og:image" content="https://someone.github.io/tender-radar/og.png"' in html
    assert "__BASE_URL__" not in html
    assert "Sitemap: https://someone.github.io/tender-radar/sitemap.xml" in (tmp_path / "robots.txt").read_text(encoding="utf-8")
    assert "<loc>https://someone.github.io/tender-radar/</loc>" in (tmp_path / "sitemap.xml").read_text(encoding="utf-8")


def test_without_base_url_tags_are_relative_and_no_sitemap(tmp_path):
    build_site(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "__BASE_URL__" not in html and 'content="./og.png"' in html
    assert not (tmp_path / "sitemap.xml").exists()
