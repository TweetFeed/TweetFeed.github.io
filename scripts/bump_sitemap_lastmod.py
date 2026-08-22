#!/usr/bin/env python3
"""Refresh <lastmod> in sitemap.xml from each page's real last content change.

Every URL's <lastmod> is now derived the same way regardless of its
<changefreq>: `git log -1 --format=%cs` on the page's index.html, the UTC
date of the commit that actually last touched it. A page nothing has
changed in stops advancing - caught 2026-08-22, all 45 URLs (including
pages with no daily job touching them at all, like the 5 malicious-*
feeds) were stamped with today's date purely because they were tagged
hourly/daily, which is not a truthful recrawl signal and is exactly the
kind of "lastmod always says today" pattern search engines learn to
ignore.

Ordering trap
--------------
This script runs near the end of .github/workflows/regen-landing-pages.yml,
after regen_tag_pages.py and bake_freshness.py have already rewritten
tag/*, tags/, malicious-*/ and trends/ for today, but BEFORE the workflow
commits. So at the moment this script runs, a page one of those two scripts
just regenerated is still UNCOMMITTED: `git log` would still return the
date of the PREVIOUS commit, one regen cycle stale, even though the file on
disk right now is today's true content. `git status --porcelain -- <path>`
catches that: any page with a pending modification, or a brand-new
untracked page with no history at all, is stamped with today's UTC date
instead of the git-log date - today IS the real last-modified date for
whatever this run is about to commit.

Falls back to the sitemap's existing <lastmod> when git can't resolve a
date either way (e.g. a shallow clone with no history for that path).

Run by regen-landing-pages.yml after bake_freshness.py, right before the
workflow commits tag/, tags/, malicious-*/, trends/ and sitemap.xml together.
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


def is_dirty(path: str) -> bool:
    """True if `path` has uncommitted changes, or is untracked (no commit
    history to read a date from yet). Either way, whatever is on disk right
    now is about to become today's real content."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", path],
        capture_output=True, text=True,
    ).stdout
    return bool(out.strip())


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
    loc = re.search(r"<loc>([^<]+)</loc>", block)
    if not loc:
        return block
    path = page_path(loc.group(1))
    new_date = today if is_dirty(path) else git_lastmod(path)
    if new_date:
        return re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{new_date}</lastmod>", block)
    return block


new = re.sub(r"<url>.*?</url>", lambda m: fix(m.group(0)), text, flags=re.S)
open(SITEMAP, "w", encoding="utf-8").write(new)
n_today = new.count(f"<lastmod>{today}</lastmod>")
n_total = len(re.findall(r"<lastmod>", new))
print(
    f"sitemap: {n_total} URLs synced to their real last-modified date "
    f"({n_today} landed on {today}: today's commits or today's regen output; "
    f"the rest kept their own git-log date)"
)
