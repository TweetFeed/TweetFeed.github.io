#!/usr/bin/env python3
"""Refresh <lastmod> in sitemap.xml for frequently-updated URLs.

Daily/hourly-changefreq pages (home, feeds, dashboard, graphs, search, the tag
pages, malicious-* feeds, hubs) get the current UTC date so Google sees an
honest, advancing recrawl signal. Weekly/monthly/yearly pages keep their
existing lastmod so the signal stays truthful. Run by regen-landing-pages.yml
after regen_tag_pages.py (and committed alongside tag/).
"""
import re
from datetime import datetime, timezone

SITEMAP = "sitemap.xml"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
text = open(SITEMAP, encoding="utf-8").read()


def fix(block: str) -> str:
    cf = re.search(r"<changefreq>(\w+)</changefreq>", block)
    if cf and cf.group(1) in ("hourly", "daily"):
        return re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{today}</lastmod>", block)
    return block


new = re.sub(r"<url>.*?</url>", lambda m: fix(m.group(0)), text, flags=re.S)
open(SITEMAP, "w", encoding="utf-8").write(new)
n = new.count(f"<lastmod>{today}</lastmod>")
print(f"sitemap: {n} daily/hourly URLs set to {today}")
