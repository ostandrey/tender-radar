"""Build the static site: copy the files from ``tender_radar/web/`` into the output folder."""
from __future__ import annotations

import shutil
from pathlib import Path

WEB_DIR = Path(__file__).parent / "web"


PLACEHOLDER = "__BASE_URL__"


def build_site(out_dir: Path, web_dir: Path = WEB_DIR, base_url: str = "") -> list[Path]:
    """Copy every static asset into ``out_dir``, leaving ``out_dir/data/`` untouched.

    ``base_url`` (e.g. ``https://owner.github.io/tender-radar/``) goes into the link-preview tags,
    ``robots.txt`` and ``sitemap.xml``; link previews need absolute URLs. Without it the tags get
    relative URLs and no sitemap is written. Returns the list of files written. The ``.nojekyll``
    marker tells GitHub Pages to serve files as they are.
    """
    base = base_url.rstrip("/") + "/" if base_url else ""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source in sorted(web_dir.rglob("*")):
        if source.is_file():
            target = out_dir / source.relative_to(web_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".html":
                target.write_text(source.read_text(encoding="utf-8").replace(PLACEHOLDER, base or "./"),
                                  encoding="utf-8")
            else:
                shutil.copyfile(source, target)
            written.append(target)
    robots = out_dir / "robots.txt"
    robots.write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {base}sitemap.xml\n" if base else ""), encoding="utf-8")
    written.append(robots)
    if base:
        sitemap = out_dir / "sitemap.xml"
        sitemap.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                           f"<url><loc>{base}</loc><changefreq>daily</changefreq></url></urlset>\n", encoding="utf-8")
        written.append(sitemap)
    marker = out_dir / ".nojekyll"
    marker.touch()
    written.append(marker)
    return written
