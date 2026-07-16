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

# The 13 user-facing main pages - the ones that share nav, footer, analytics,
# and canonical patterns, and get the full check suite below (nav order,
# canonical, analytics, footer, meta-description length, single h1).
# Excluded, verified via ls 2026-07-16 (the old comment's today.html/tos.html
# flat-file stubs and SB Admin 2 scaffolds are long gone, removed 2026-05-11
# and earlier - not the current reason for any exclusion below):
#   - 404.html: its own template, no shared nav; only noindex polarity applies.
#   - tag/<slug>/index.html, tags/index.html, ioc-types/index.html + the
#     scripts/templates/*.j2 they're rendered from: checked separately by
#     landing_pages() (footer pattern only, not the full suite here).
#   - tos/index.html, threat-intelligence-guide/index.html and the
#     malicious-{urls,domains,ips,hashes-md5,hashes-sha256}/index.html hub
#     pages: DO carry the shared nav/footer/analytics but aren't wired into
#     any check yet - a real coverage gap, not an intentional exclusion.
MAIN_PAGES = [
    "about/index.html", "agents/index.html", "api/index.html", "campaigns/index.html",
    "changelog/index.html", "dashboard/index.html", "docs/index.html", "feeds/index.html",
    "graphs/index.html", "hunt/index.html", "index.html", "researchers/index.html",
    "search/index.html",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
# Only the prod repo (TweetFeed.github.io) carries a CNAME file; the stage
# clone does not. Checks with opposite expectations per repo key off this.
REPO_IS_PROD = (REPO_ROOT / "CNAME").is_file()


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

        # Normalize href prefixes: index.html uses 'X/' (root-relative) while
        # /<page>/index.html uses '../X/'. Same target. Strip leading ../ for
        # comparison so the check is depth-agnostic.
        def norm(href):
            return href.lstrip('./')
        present = {p: tuple(norm(h) for h in v) for p, v in per_page.items() if v is not None}
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
        # Other main pages live at /<name>/index.html and the canonical should
        # be /<name>/ (clean URL, no .html).
        if p == "index.html":
            ok = re.match(r"^https://tweetfeed\.live/?$", canonical)
        else:
            slug = p.split("/", 1)[0]
            ok = canonical.endswith(f"/{slug}/")
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
    # Both footers gate on lg (992): desktop d-lg-block (>=992), mobile d-lg-none
    # (<992). Was d-md-block until 2026-06-28; that overlapped both footers at
    # 768-991px (tablet). Do not revert to d-md-block.
    desktop_re = re.compile(r'<footer[^>]*\bd-none\b[^>]*\bd-lg-block\b', re.DOTALL)
    mobile_re = re.compile(r'<footer[^>]*\bsticky-footer\b[^>]*\bd-lg-none\b', re.DOTALL)
    failures: list[str] = []
    for p in pages:
        html = read(p)
        if not desktop_re.search(html):
            failures.append(f"{p}: missing desktop <footer class='... d-none d-lg-block'>")
        if not mobile_re.search(html):
            failures.append(f"{p}: missing mobile <footer class='sticky-footer ... d-lg-none'>")
        # Exactly the two footers above. A third block slips past the regexes
        # (changelog/search shipped a legacy 'bg-white d-lg-none' footer that
        # rendered as a duplicate on mobile until 2026-07-17).
        n = html.count("<footer")
        if n != 2:
            failures.append(f"{p}: expected exactly 2 <footer> blocks, found {n}")
    return failures


def check_meta_description_length(pages: list[str]) -> list[str]:
    """Meta description should be 80-160 chars (Google snippet limit ~155-160).
    Shorter than 80 leaves SEO real estate on the table; longer than 160
    truncates in SERPs.  Caught by audit 2026-05-02 — 7 pages over 160."""
    desc_re = re.compile(r'<meta name="description" content="([^"]*)"')
    failures: list[str] = []
    for p in pages:
        m = desc_re.search(read(p))
        if not m:
            failures.append(f"{p}: missing <meta name='description'>")
            continue
        n = len(m.group(1))
        if n > 160:
            failures.append(f"{p}: meta description too long ({n} chars; trim to <=160)")
        elif n < 80:
            failures.append(f"{p}: meta description too short ({n} chars; expand to >=80)")
    return failures


def check_single_h1(pages: list[str]) -> list[str]:
    """Each page should have exactly one <h1>.  Multiple h1s dilute the page-
    level topic signal; zero leaves the page without a primary heading."""
    h1_re = re.compile(r'<h1\b', re.IGNORECASE)
    failures: list[str] = []
    for p in pages:
        n = len(h1_re.findall(read(p)))
        if n != 1:
            failures.append(f"{p}: expected exactly 1 <h1>, found {n}")
    return failures


CHECKS = [
    ("Nav order (desktop + mobile dropdown)", check_nav_order),
    ("Canonical URLs", check_canonicals),
    ("Analytics scripts (anchor + Umami + Ahrefs)", check_analytics),
    ("Footer pattern (desktop + mobile)", check_footers),
    ("Meta description length (80-160)", check_meta_description_length),
    ("Single <h1> per page", check_single_h1),
]


def all_html_pages() -> list[str]:
    return sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*.html")
        if not any(part in (".git", "node_modules") for part in p.parts)
    )


def check_noindex_polarity(pages: list[str]) -> list[str]:
    """Stage pages must ALL carry a noindex meta (stage robots.txt allows
    crawling, so the meta does the blocking); prod pages must NEVER carry one
    (a stage->prod copy that leaks the meta would deindex the live site).
    Repo role is detected via the CNAME file (only prod has one). 404.html is
    exempt in prod: noindex on the 404 page is intentional there too."""
    noindex_re = re.compile(r'<meta name="robots" content="noindex')
    failures: list[str] = []
    for p in pages:
        has = bool(noindex_re.search(read(p)))
        if REPO_IS_PROD:
            if has and p != "404.html":
                failures.append(f"{p}: noindex meta present in PROD (stage-only marker leaked?)")
        elif not has:
            failures.append(f"{p}: missing noindex meta (stage must not be indexable)")
    return failures


def landing_pages() -> list[str]:
    """tag/<slug>/index.html + hub pages + the j2 templates they render from.
    The 2026-06-28 d-md-block fix regressed the next morning because only the
    rendered pages were patched, not the templates, and the daily regen
    re-stamped the bug (caught by audit 2026-07-04)."""
    pages = sorted(
        str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "tag").glob("*/index.html")
    )
    pages += ["tags/index.html", "ioc-types/index.html"]
    pages += sorted(
        str(p.relative_to(REPO_ROOT))
        for p in (REPO_ROOT / "scripts" / "templates").glob("*.j2")
    )
    return [p for p in pages if (REPO_ROOT / p).is_file()]


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

    extra = landing_pages()
    failures = check_footers(extra)
    if not failures:
        print(f"[PASS] Footer pattern (tag pages + hubs + templates): all {len(extra)} pages OK")
    else:
        print(f"[FAIL] Footer pattern (tag pages + hubs + templates): {len(failures)} issue(s)")
        for f in failures:
            print(f"  - {f}")
        total_failures += len(failures)

    pages_all = all_html_pages()
    role = "prod: must be absent" if REPO_IS_PROD else "stage: must be present"
    failures = check_noindex_polarity(pages_all)
    if not failures:
        print(f"[PASS] Noindex polarity ({role}): all {len(pages_all)} pages OK")
    else:
        print(f"[FAIL] Noindex polarity ({role}): {len(failures)} issue(s)")
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
