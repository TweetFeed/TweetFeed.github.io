#!/usr/bin/env python3
"""Consistency checks across the 12 main pages of TweetFeed.

Run from the repo root (frontend-stage/ or frontend-prod/):
    python3 scripts/check_consistency.py

Exits 0 on pass, 1 on any check failure, 2 on missing pages.

Why this exists: TweetFeed has 30 HTML pages copy-pasted with no templating.
Site-wide changes are replicated by hand or one-shot scripts, and drift
between pages happens silently. Real bugs caught by this kind of check:
nav order on agents.html (2026-04-25), missing canonical on feed.html
(2026-04-12), GA4+Matomo lingering in prod (2026-04-11), wrong footer
pattern on agents.html at creation (2026-04-19).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

# The 11 user-facing main pages — the ones that share nav, footer, analytics,
# and canonical patterns. (CLAUDE.md still lists 12 including base.html, but
# base.html was dropped in commit ddefac1 "drop stale base.html".) Excludes
# 404.html, today.html, tos.html (no shared nav anchor) and the SB Admin 2
# scaffolds + legacy joke pages.
MAIN_PAGES = [
    "about.html", "agents.html", "api.html", "changelog.html",
    "dashboard.html", "feeds.html", "graphs.html", "hunt.html", "index.html",
    "researchers.html", "search.html",
]

REPO_ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def extract_desktop_nav(html: str) -> list[str] | None:
    """Return ordered list of href values from the left desktop nav."""
    block = re.search(
        r'<ul class="nav navbar-nav navbar-left">(.*?)</ul>', html, re.DOTALL
    )
    if not block:
        return None
    return re.findall(r'<a class="nav-link[^"]*"\s+href="([^"]+)"', block.group(1))


def extract_mobile_dropdown(html: str) -> list[str] | None:
    """Return ordered list of href values from the mobile hamburger dropdown."""
    block = re.search(
        r'<div class="dropdown-menu[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL
    )
    if not block:
        return None
    return re.findall(r'<a class="dropdown-item"\s+href="([^"]+)"', block.group(1))


def extract_canonical(html: str) -> str | None:
    m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    return m.group(1) if m else None


def list_drift(expected: tuple[str, ...], actual: tuple[str, ...]) -> str:
    if expected == actual:
        return "(none)"
    only_expected = [x for x in expected if x not in actual]
    only_actual = [x for x in actual if x not in expected]
    if not only_expected and not only_actual:
        return "same items, different order"
    return f"missing: {only_expected or '[]'} | extra: {only_actual or '[]'}"


def check_nav_order(pages: list[str]) -> list[str]:
    """Desktop nav and mobile dropdown should have identical href order on every page."""
    failures: list[str] = []

    for label, extractor in [
        ("desktop nav", extract_desktop_nav),
        ("mobile dropdown", extract_mobile_dropdown),
    ]:
        per_page = {p: extractor(read(p)) for p in pages}
        missing = [p for p, v in per_page.items() if v is None]
        for p in missing:
            failures.append(f"{p}: missing {label} block")

        present = {p: tuple(v) for p, v in per_page.items() if v is not None}
        if not present:
            continue
        baseline, count = Counter(present.values()).most_common(1)[0]
        for p, hrefs in present.items():
            if hrefs != baseline:
                failures.append(
                    f"{p}: {label} order differs from baseline\n"
                    f"        baseline ({count} pages): {list(baseline)}\n"
                    f"        this page:                {list(hrefs)}\n"
                    f"        drift: {list_drift(baseline, hrefs)}"
                )
    return failures


def check_canonicals(pages: list[str]) -> list[str]:
    """Every page must have <link rel='canonical'> pointing to its own URL."""
    failures: list[str] = []
    for p in pages:
        canonical = extract_canonical(read(p))
        if canonical is None:
            failures.append(f"{p}: missing <link rel='canonical' href='...'>")
            continue
        # index.html canonical should be the bare domain (with or without trailing /).
        # All others should end with /<filename>.
        if p == "index.html":
            ok = re.match(r"^https://tweetfeed\.live/?$", canonical)
        else:
            ok = canonical.endswith(f"/{p}")
        if not ok:
            failures.append(f"{p}: canonical points elsewhere: {canonical}")
    return failures


def check_analytics(pages: list[str]) -> list[str]:
    """Every main page must have the analytics anchor + Umami + Ahrefs scripts."""
    failures: list[str] = []
    for p in pages:
        html = read(p)
        if "<!-- 100% privacy-first analytics -->" not in html:
            failures.append(f"{p}: missing '<!-- 100% privacy-first analytics -->' anchor")
        if "cloud.umami.is" not in html:
            failures.append(f"{p}: missing Umami script (cloud.umami.is)")
        if "analytics.ahrefs.com" not in html:
            failures.append(f"{p}: missing Ahrefs script (analytics.ahrefs.com)")
    return failures


def check_footers(pages: list[str]) -> list[str]:
    """Every page must have BOTH a desktop footer and a mobile sticky-footer."""
    desktop_re = re.compile(r'<footer[^>]*\bd-none\b[^>]*\bd-md-block\b', re.DOTALL)
    mobile_re = re.compile(r'<footer[^>]*\bsticky-footer\b[^>]*\bd-lg-none\b', re.DOTALL)
    failures: list[str] = []
    for p in pages:
        html = read(p)
        if not desktop_re.search(html):
            failures.append(f"{p}: missing desktop <footer class='... d-none d-md-block'>")
        if not mobile_re.search(html):
            failures.append(f"{p}: missing mobile <footer class='sticky-footer ... d-lg-none'>")
    return failures


CHECKS = [
    ("Nav order (desktop + mobile dropdown)", check_nav_order),
    ("Canonical URLs", check_canonicals),
    ("Analytics scripts (anchor + Umami + Ahrefs)", check_analytics),
    ("Footer pattern (desktop + mobile)", check_footers),
]


def main() -> int:
    missing = [p for p in MAIN_PAGES if not (REPO_ROOT / p).is_file()]
    if missing:
        print(f"ERROR: missing main pages in {REPO_ROOT}: {missing}", file=sys.stderr)
        return 2

    total_failures = 0
    for label, fn in CHECKS:
        failures = fn(MAIN_PAGES)
        if not failures:
            print(f"[PASS] {label}: all {len(MAIN_PAGES)} pages OK")
        else:
            print(f"[FAIL] {label}: {len(failures)} issue(s)")
            for f in failures:
                print(f"  - {f}")
            total_failures += len(failures)

    print()
    if total_failures == 0:
        print(f"All checks passed across {len(MAIN_PAGES)} pages.")
        return 0
    print(f"Total: {total_failures} consistency issue(s) across {len(MAIN_PAGES)} pages.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
