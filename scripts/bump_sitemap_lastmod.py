#!/usr/bin/env python3
"""Refresh <lastmod> in sitemap.xml.

Daily/hourly-changefreq pages (home, feeds, dashboard, graphs, search, the tag
pages, malicious-* feeds, hubs) get the current UTC date so Google sees an
honest, advancing recrawl signal. Weekly/monthly/yearly pages instead take the
date of the page's last real content commit (`git log -1 --format=%cs` on its
index.html) so lastmod stays truthful instead of freezing forever - caught
2026-07-16, 9 non-daily URLs were still stamped 2026-06-07 months after real
edits. Falls back to the existing <lastmod> if git can't resolve a date (e.g.
untracked file, shallow clone with no history for that path). Run by
regen-landing-pages.yml after regen_tag_pages.py (and committed alongside
tag/).
"""
import re
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

SITEMAP = "sitemap.xml"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
text = open(SITEMAP, encoding="utf-8").read()


def page_path(loc: str) -> str:
    """Map a sitemap <loc> URL to its repo-relative index.html path."""
    path = urlparse(loc).path.strip("/")
    return f"{path}/index.html" if path else "index.html"


def git_lastmod(path: str) -> str | None:
    """Last commit date (UTC, YYYY-MM-DD) touching path, or None if git can't tell."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", path],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out or None


def fix(block: str) -> str:
    cf = re.search(r"<changefreq>(\w+)</changefreq>", block)
    if cf and cf.group(1) in ("hourly", "daily"):
        return re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{today}</lastmod>", block)
    loc = re.search(r"<loc>([^<]+)</loc>", block)
    new_date = git_lastmod(page_path(loc.group(1))) if loc else None
    if new_date:
        return re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{new_date}</lastmod>", block)
    return block


new = re.sub(r"<url>.*?</url>", lambda m: fix(m.group(0)), text, flags=re.S)
open(SITEMAP, "w", encoding="utf-8").write(new)
n = new.count(f"<lastmod>{today}</lastmod>")
print(f"sitemap: {n} daily/hourly URLs set to {today}; other URLs synced to git lastmod")
