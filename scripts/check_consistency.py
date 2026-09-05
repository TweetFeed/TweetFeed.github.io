#!/usr/bin/env python3
"""Consistency checks across the 22 main pages of TweetFeed.

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

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# The 22 user-facing main pages - the ones that share nav, footer, analytics,
# and canonical patterns, and get the full check suite below (nav order,
# canonical, analytics, footer, meta-description length, single h1).
# Excluded, verified via ls 2026-07-16 (the old comment's today.html/tos.html
# flat-file stubs and SB Admin 2 scaffolds are long gone, removed 2026-05-11
# and earlier - not the current reason for any exclusion below):
#   - 404.html: its own template, no shared nav; only noindex polarity applies.
#   - tag/<slug>/index.html, tags/index.html, ioc-types/index.html + the
#     scripts/templates/*.j2 they're rendered from: checked separately by
#     landing_pages() (footer pattern only, not the full suite here).
MAIN_PAGES = [
    "about/index.html", "agents/index.html", "api/index.html", "campaigns/index.html",
    "changelog/index.html", "dashboard/index.html", "docs/index.html", "feeds/index.html",
    "graphs/index.html", "hunt/index.html", "index.html", "researchers/index.html",
    "search/index.html", "trends/index.html", "tos/index.html",
    "threat-intelligence-guide/index.html", "malicious-urls/index.html",
    "malicious-domains/index.html", "malicious-ips/index.html",
    "malicious-hashes-md5/index.html", "malicious-hashes-sha256/index.html",
    "blocklists/index.html",
]

# Direct link to the feedback issue form, added 2026-08-01 to replace the
# GitHub issue chooser (which forced an extra click before a user could
# actually write anything). See check_feedback_cta / check_no_chooser_link.
FEEDBACK_URL = "https://github.com/0xDanielLopez/TweetFeed/issues/new?template=feedback.yml"
# Split so this file itself doesn't trip a literal grep for the fragment.
CHOOSER_URL_FRAGMENT = "issues/new/" + "choose"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_ia as ia  # noqa: E402
from render_shell import close_element  # noqa: E402
from year_counts import YEAR_CLAIM_PAGES, YEAR_CLAIM_RE, fetch_year_counts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
# Only the prod repo (TweetFeed.github.io) carries a CNAME file; the stage
# clone does not. Checks with opposite expectations per repo key off this.
REPO_IS_PROD = (REPO_ROOT / "CNAME").is_file()


def read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


DESKTOP_NAV_RE = re.compile(r'<nav\b[^>]*\bnavbar-expand-lg\b[^>]*\bfixed-top\b[^>]*>', re.I)
MOBILE_NAV_RE = re.compile(
    r'<nav\b(?![^>]*\bnavbar-expand-lg\b)[^>]*\bnavbar-expand\b[^>]*\bd-lg-none\b[^>]*>', re.I
)
DESKTOP_FOOTER_RE = re.compile(r'<footer\b[^>]*\bd-none\b[^>]*\bd-lg-block\b[^>]*>', re.I)
MOBILE_FOOTER_RE = re.compile(r'<footer\b[^>]*\bsticky-footer\b[^>]*\bd-lg-none\b[^>]*>', re.I)


def _block(html: str, anchor: re.Pattern, tag: str) -> str | None:
    """Return the full text of the element the anchor opens, using a balanced
    scanner. A non-greedy `.*?</tag>` is unsafe here: feeds/ ships 3 <nav>
    elements and hunt/ ships 6 (content-level nav.page-toc)."""
    m = anchor.search(html)
    if not m:
        return None
    try:
        return html[m.start():close_element(html, m.start(), tag)]
    except ValueError:
        return None


def extract_desktop_nav(html: str) -> list[str] | None:
    """Ordered hrefs of the left desktop nav: wordmark, primaries, More trigger."""
    block = _block(html, DESKTOP_NAV_RE, "nav")
    if block is None:
        return None
    ul = re.search(r'<ul class="nav navbar-nav navbar-left">(.*?)</ul>', block, re.DOTALL)
    if not ul:
        return None
    return re.findall(r'<a class="nav-link[^"]*"\s+href="([^"]+)"', ul.group(1))


def extract_nav_right(html: str) -> list[str] | None:
    """Ordered hrefs of the right desktop group (search icon, Docs).

    The pre-2026-08-18 checker ignored this group entirely, so drift there was
    invisible."""
    block = _block(html, DESKTOP_NAV_RE, "nav")
    if block is None:
        return None
    ul = re.search(r'<ul class="nav navbar-nav navbar-right">(.*?)</ul>', block, re.DOTALL)
    if not ul:
        return None
    return re.findall(r'<a class="nav-link[^"]*"\s+href="([^"]+)"', ul.group(1))


def extract_desktop_more(html: str) -> list[str] | None:
    """Ordered hrefs inside the desktop More dropdown.

    Without this, 11 of the ~20 nav destinations would be unverified: the
    left-nav extractor only sees the 6 top-level items plus the trigger."""
    block = _block(html, DESKTOP_NAV_RE, "nav")
    if block is None:
        return None
    m = re.search(r'<div class="dropdown-menu[^"]*">', block)
    if not m:
        return None
    try:
        menu = block[m.start():close_element(block, m.start(), "div")]
    except ValueError:
        return None
    return re.findall(r'<a class="dropdown-item[^"]*"\s+href="([^"]+)"', menu)


def extract_mobile_dropdown(html: str) -> list[str] | None:
    """Ordered hrefs of the mobile hamburger dropdown.

    SCOPED to the mobile <nav> on purpose. The previous implementation did a
    bare re.search for the first `<div class="dropdown-menu...">` in the whole
    document and was non-greedy to the first `</div>`. Once the desktop More
    menu was added it silently started reading the WRONG menu (and would have
    truncated at any `<div class="dropdown-divider">`), while still printing
    [PASS]. Separators are therefore <hr class="dropdown-divider">, never a
    <div>, and the class match is a prefix so the Feedback CTA
    (`dropdown-item btn btn-tf nav-cta`) is no longer invisible to this check."""
    block = _block(html, MOBILE_NAV_RE, "nav")
    if block is None:
        return None
    m = re.search(r'<div class="dropdown-menu[^"]*">', block)
    if not m:
        return None
    try:
        menu = block[m.start():close_element(block, m.start(), "div")]
    except ValueError:
        return None
    return re.findall(r'<a class="dropdown-item[^"]*"\s+href="([^"]+)"', menu)


def extract_footer_links(html: str, mobile: bool) -> list[str] | None:
    anchor = MOBILE_FOOTER_RE if mobile else DESKTOP_FOOTER_RE
    cls = "tf-mfoot-link" if mobile else "tf-foot-link"
    block = _block(html, anchor, "footer")
    if block is None:
        return None
    return re.findall(r'<a class="' + cls + r'[^"]*"\s+href="([^"]+)"', block)


def norm(href: str) -> str:
    """Depth- and repo-agnostic form of an href.

    index.html uses 'X/', /<page>/index.html uses '../X/', depth-2 pages use
    '../../X/', and stage's 404.html uses '/tweetfeed-stage/X/'. All are the
    same target. Folding the stage prefix in means 404.html is finally covered
    by the same baseline as every other page instead of being excluded."""
    if href.startswith(("http://", "https://", "#")):
        return href
    h = href.lstrip("./")
    if h.startswith("tweetfeed-stage/"):
        h = h[len("tweetfeed-stage/"):]
    return h


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


def _expected_desktop_nav() -> tuple:
    return tuple([""] + [l.href for l in ia.NAV_PRIMARY] + ["#"])


def _expected_more() -> tuple:
    return tuple(l.href for l in ia.nav_more_links())


def _expected_nav_right() -> tuple:
    return (ia.SEARCH.href, ia.DOCS.href)


def _expected_mobile() -> tuple:
    # Separators are <hr>, so only the anchors are extractable.
    return tuple(l.href for l in ia.nav_mobile_links())


def check_nav_order(pages: list[str]) -> list[str]:
    """Every nav surface must match the IA declared in scripts/site_ia.py.

    This used to derive its baseline by MAJORITY VOTE across pages. That was
    right while edits were manual and drift was per-page, but it inverts under
    a scripted rollout: the renderer writes identical markup everywhere, so a
    uniform mistake simply becomes the baseline and passes green. Comparing
    against the declared IA makes the gate verify intent."""
    failures: list[str] = []
    surfaces = [
        ("desktop nav", extract_desktop_nav, _expected_desktop_nav()),
        ("desktop More menu", extract_desktop_more, _expected_more()),
        ("desktop nav right", extract_nav_right, _expected_nav_right()),
        ("mobile dropdown", extract_mobile_dropdown, _expected_mobile()),
    ]
    for label, extractor, expected in surfaces:
        expected_n = tuple(norm(h) for h in expected)
        for p in pages:
            got = extractor(read(p))
            if got is None:
                failures.append(f"{p}: missing {label} block")
                continue
            got_n = tuple(norm(h) for h in got)
            if got_n != expected_n:
                failures.append(
                    f"{p}: {label} does not match site_ia\n"
                    f"        expected: {list(expected_n)}\n"
                    f"        actual:   {list(got_n)}\n"
                    f"        drift: {list_drift(expected_n, got_n)}"
                )
    return failures


def check_dropdown_menu_count(pages: list[str]) -> list[str]:
    """Exactly two dropdown menus per page: desktop More, mobile hamburger.

    Cheap, and it permanently prevents a third menu from re-breaking any of the
    scoped extractors above."""
    failures: list[str] = []
    for p in pages:
        n = read(p).count('class="dropdown-menu')
        if n != 2:
            failures.append(f"{p}: expected exactly 2 dropdown menus, found {n}")
    return failures


def check_no_div_divider(pages: list[str]) -> list[str]:
    """Separators must be <hr class="dropdown-divider">, never a <div>.

    extract_*_dropdown scans for the balanced close of the menu <div>; a
    `<div class="dropdown-divider"></div>` inside would make an earlier
    non-greedy reader truncate, and it is the semantically wrong element."""
    failures: list[str] = []
    for p in pages:
        if re.search(r'<div[^>]*\bdropdown-divider\b', read(p)):
            failures.append(f"{p}: uses a <div> dropdown-divider; use <hr class=\"dropdown-divider\">")
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
        if "s.tweetfeed.live" not in html:
            failures.append(f"{p}: missing Umami script (s.tweetfeed.live)")
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


def check_footer_parity(pages: list[str]) -> list[str]:
    """Both footers on every page must carry exactly the links site_ia declares.

    check_footers only ever asserted that two <footer> blocks EXIST. That is
    why the footer silently drifted into 4 variants: 33 generated pages had 10
    links, 20 pages had 11, index.html had 13 (the only page linking
    /malicious-ips/ and /feeds/), and tos/index.html omitted Changelog."""
    expected_desktop = tuple(norm(l.href) for l in ia.footer_links())
    expected_mobile = tuple(norm(l.href) for l in ia.footer_links_mobile())
    failures: list[str] = []
    for p in pages:
        html = read(p)
        for mobile, label in ((False, "desktop footer"), (True, "mobile footer")):
            expected = expected_mobile if mobile else expected_desktop
            got = extract_footer_links(html, mobile)
            if got is None:
                failures.append(f"{p}: missing {label} block")
                continue
            got_n = tuple(norm(h) for h in got)
            if got_n != expected:
                failures.append(
                    f"{p}: {label} links do not match site_ia\n"
                    f"        drift: {list_drift(expected, got_n)}"
                )
    return failures


def check_footer_headings(pages: list[str]) -> list[str]:
    """Each footer must carry its own declared column headings, so the columns
    cannot silently collapse back into a one-line run-on row.

    Desktop and mobile are checked separately on purpose: since 2026-08-18 the
    mobile footer is a deliberate subset (see site_ia.FOOTER_MOBILE_COLUMNS),
    not a copy."""
    failures: list[str] = []
    for p in pages:
        html = read(p)
        for mobile, columns, label in (
            (False, ia.FOOTER_COLUMNS, "desktop footer"),
            (True, ia.FOOTER_MOBILE_COLUMNS, "mobile footer"),
        ):
            anchor = MOBILE_FOOTER_RE if mobile else DESKTOP_FOOTER_RE
            block = _block(html, anchor, "footer")
            if block is None:
                failures.append(f"{p}: missing {label} block")
                continue
            for heading, _ in columns:
                if f">{heading}</p>" not in block:
                    failures.append(f"{p}: {label} missing heading {heading!r}")
    return failures


SHELL_HREF_RE = re.compile(
    r'<a class="(?:nav-link|dropdown-item|tf-foot-link|tf-mfoot-link|tf-social|tf-foot-wordmark)[^"]*"'
    r'\s+href="([^"]+)"'
)


def check_links_resolve(pages: list[str]) -> list[str]:
    """Every relative nav/footer href must resolve to a file that exists.

    Parity and order checks are not enough: norm() strips leading './' and
    '../', so a depth prefix wrongly glued onto an absolute URL
    ("../../https://github.com/...") normalizes to the correct-looking value
    and passes. Only resolving the path catches it. Depth-2 pages (31 of 56)
    are the highest-risk case, and stage's 404.html is the only page using an
    absolute base."""
    failures: list[str] = []
    for p in pages:
        page_dir = os.path.dirname(p)
        for href in sorted(set(SHELL_HREF_RE.findall(read(p)))):
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if href.startswith("/tweetfeed-stage/"):
                target = href[len("/tweetfeed-stage/"):] or "index.html"
            elif href.startswith("/"):
                target = href.lstrip("/") or "index.html"
            else:
                target = os.path.normpath(os.path.join(page_dir, href))
            if target in (".", ""):
                target = "index.html"
            path = Path(target) if target.endswith(".html") else Path(target) / "index.html"
            if not (REPO_ROOT / path).is_file():
                failures.append(f"{p}: href {href!r} does not resolve ({path})")
    return failures


DOCS_SIDEBAR_RE = re.compile(r'<aside\b[^>]*\bdocs-sidebar\b[^>]*>', re.I)


def check_docs_sidebar(pages: list[str]) -> list[str]:
    """Every .docs-wrap page must carry the sidebar declared in site_ia, and
    must highlight ITS OWN entry.

    This block used to be copy-pasted and had drifted into seven variants with
    nothing watching it. On all five malicious-* pages `class="active"` sat on
    ../ioc-types/ rather than the page's own link, because the whole aside had
    been copied from ioc-types/. Neither the drift nor the wrong highlight was
    detectable before this check existed."""
    expected = tuple(norm(l.href) for l in ia.docs_sidebar_links())
    failures: list[str] = []
    for p in pages:
        html = read(p)
        if not DOCS_SIDEBAR_RE.search(html):
            continue                      # not a docs-layout page
        block = _block(html, DOCS_SIDEBAR_RE, "aside")
        if block is None:
            failures.append(f"{p}: docs sidebar block is unbalanced")
            continue
        got = tuple(norm(h) for h in re.findall(r'<li><a href="([^"]+)"', block))
        if got != expected:
            failures.append(
                f"{p}: docs sidebar links do not match site_ia\n"
                f"        drift: {list_drift(expected, got)}"
            )
        want_active = ia.docs_sidebar_active_for(p)
        active = re.findall(r'<a href="([^"]+)"[^>]*\bclass="[^"]*\bactive\b', block)
        active_n = [norm(h) for h in active]
        if want_active is None:
            continue
        if active_n != [norm(want_active)]:
            failures.append(
                f"{p}: docs sidebar should highlight {want_active!r}, highlights {active_n}"
            )
        if "<details" not in block:
            failures.append(f"{p}: docs sidebar is not collapsible (<details> missing)")
    return failures


def check_orphan_pages() -> list[str]:
    """Every page directory must be reachable from the nav or the footer.

    Footer parity alone only guarantees every page is equally wrong. This is
    the check that would have caught /malicious-urls/, /malicious-hashes-md5/
    and /malicious-hashes-sha256/ sitting in no footer at all.

    Depth 2 (`*/*/index.html`) is checked too, added 2026-08-23. `tag/<slug>/`
    subdirs get a pass: they are reachable from /tag/ (a real hub page with
    real <a href> links to each) and regenerated daily. Nothing else at depth
    2 gets a pass - in particular campaigns/tfc-*/ permalink pages are NOT
    reached through /campaigns/, despite what the old comment here claimed:
    that hub only ever writes `#tfc-<id>` in-page anchors for its own
    scrollIntoView deep-linking, never an `<a href="tfc-.../">` to a separate
    permalink page, so a stale campaigns/tfc-*/ directory with no other
    inbound link is a true orphan."""
    reachable = set(ia.internal_footer_targets())
    reachable |= {l.href for l in ia.NAV_PRIMARY}
    reachable |= {l.href for l in ia.nav_more_links() if not l.external}
    reachable |= {ia.SEARCH.href, ia.DOCS.href, ""}
    failures: list[str] = []
    for path in sorted(REPO_ROOT.glob("*/index.html")):
        d = path.parent.name + "/"
        if d in reachable:
            continue
        # tag/ subtree is reached through its hub page.
        if d in ("tag/",):
            continue
        failures.append(f"/{d} exists but is linked from neither the nav nor the footer")
    for path in sorted(REPO_ROOT.glob("*/*/index.html")):
        # Same skip as the page enumeration in main(): node_modules/ is
        # gitignored dev tooling (bs-snippet-injector ships an index.html)
        # and never deploys, so it can't be an orphan page.
        if any(part in (".git", "node_modules") for part in path.parts):
            continue
        parent = path.parent.parent.name + "/"
        d = parent + path.parent.name + "/"
        if parent == "tag/":
            continue
        failures.append(f"/{d} exists at depth 2 but is not reachable (only tag/<slug>/ is allowed there)")
    return failures


# Local CSS/JS assets that get cache-busted with a `?v=N` query string.
# tweetfeed.css and index.css bump together (render_shell.py --bump-css), so
# they are tracked as one group; every other asset stands on its own.
#
# Extended 2026-08-19: this used to hardcode just those two filenames.
# js/utils.js turned up referenced on 58 pages with NO ?v= at all (one
# straggler carried ?v=2) - a real edit to that file would never have
# reached anyone's warm cache, and the check as written had no way to catch
# it because it only ever looked at tweetfeed.css/index.css.
CSS_BUST_GROUP = frozenset({"tweetfeed.css", "index.css"})

# Matches a same-repo css/ or js/ asset reference: href="…" or src="…" whose
# path is a chain of "../" (or the 404.html stage prefix) followed directly
# by "css/<file>" or "js/<file>", optionally with "?v=N". No wildcard skip
# between the anchor and "css/"/"js/", so this does not match vendor/ or
# js/demo/ paths (e.g. "../vendor/bootstrap/js/bootstrap.bundle.min.js" or
# "../js/demo/datatables-demo.js") - those have another directory name
# between the leading "../" run and the "js/" segment, or another "/" inside
# the filename slot, and either breaks the match.
ASSET_REF_RE = re.compile(
    r'(?:href|src)="'
    r'(?:\.\./)*(?:/tweetfeed-stage/)?'
    r'(?:css|js)/'
    r'([\w.-]+\.(?:css|js))'
    r'(?:\?v=(\d+))?'
    r'"'
)


def check_cachebust_uniform() -> list[str]:
    """Every local CSS/JS asset that carries a ?v=N ANYWHERE must carry the
    SAME N everywhere, and never show up unversioned once it has started
    being versioned at all.

    With 107+ files across two repos a partial bump is the single most
    likely mechanical failure, and its symptom (new markup + cached old
    asset) is exactly the unstyled-CTA bug documented in
    check_stylesheet_present. Assets are discovered rather than hardcoded so
    this covers "todo asset local versionable" per the 2026-08-19 audit, not
    just the CSS pair: tweetfeed.css and index.css are one group because
    render_shell.py --bump-css always moves them together; every other
    local css/js file (table.css, utils.js, ...) is its own group. An asset
    nobody has started versioning yet (tooltip.css, config.js, the vendored
    sb-admin-2 files) is not this check's problem - only a group with at
    least one ?v= reference somewhere gets enforced, so adopting
    cache-busting for a new asset is opt-in, never a drive-by fix forced
    onto unrelated files that never asked for it."""
    targets = [REPO_ROOT / p for p in all_html_pages()]
    targets += sorted((REPO_ROOT / "scripts" / "templates").glob("*.j2"))

    refs: dict[str, list[tuple[str, str]]] = {}  # group -> [(version, file), ...]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for m in ASSET_REF_RE.finditer(text):
            filename, version = m.group(1), m.group(2)
            group = "tweetfeed.css+index.css" if filename in CSS_BUST_GROUP else filename
            refs.setdefault(group, []).append((version or "(none)", str(path.relative_to(REPO_ROOT))))

    failures: list[str] = []
    for group, entries in sorted(refs.items()):
        versions = {v for v, _ in entries}
        if versions == {"(none)"}:
            continue  # nobody has started versioning this asset - not our problem
        if len(versions) <= 1:
            continue
        by_version: dict[str, list[str]] = {}
        for v, f in entries:
            by_version.setdefault(v, []).append(f)
        out = [f"{group} cache-bust is not uniform:"]
        for v, files in sorted(by_version.items()):
            out.append(f"        ?v={v}: {len(files)} file(s), e.g. {files[:3]}")
        failures.append("\n".join(out))
    return failures


def check_templates_include_shell() -> list[str]:
    """The Jinja templates must pull the shell in, never inline a copy.

    The 2026-06-28 d-md-block fix regressed the very next morning because only
    the rendered pages were patched and the daily regen re-stamped the old
    shell from the templates."""
    failures: list[str] = []
    tpl_dir = REPO_ROOT / "scripts" / "templates"
    for tpl in sorted(tpl_dir.glob("*.j2")):
        if tpl.name.startswith("_"):
            continue
        text = tpl.read_text(encoding="utf-8")
        for inc in ("{{ shell_nav }}", "{{ shell_footer }}"):
            if inc not in text:
                failures.append(f"scripts/templates/{tpl.name}: missing {inc}")
        if DESKTOP_NAV_RE.search(text) or DESKTOP_FOOTER_RE.search(text):
            failures.append(
                f"scripts/templates/{tpl.name}: still inlines a copy of the shell"
            )
    return failures


def check_feedback_cta(pages: list[str]) -> list[str]:
    """Every page must expose a one-click Feedback CTA in the nav, styled as
    a button (btn-tf), pointing straight at the feedback issue template.
    Added 2026-08-01: the only feedback entry point used to be a plain-text
    footer link to the GitHub issue chooser, which forced a second click
    (pick a template) before a user could write anything."""
    failures: list[str] = []
    btn_re = re.compile(
        r'class="[^"]*\bbtn-tf\b[^"]*"[^>]*href="' + re.escape(FEEDBACK_URL)
        + r'"|href="' + re.escape(FEEDBACK_URL) + r'"[^>]*class="[^"]*\bbtn-tf\b[^"]*"'
    )
    for p in pages:
        html = read(p)
        if FEEDBACK_URL not in html:
            failures.append(f"{p}: missing feedback CTA (expected an href to {FEEDBACK_URL})")
        elif not btn_re.search(html):
            failures.append(f"{p}: feedback link present but not styled as a button (missing btn-tf)")
    return failures


def check_no_chooser_link(pages: list[str]) -> list[str]:
    """Regression guard for the 2026-08-01 feedback CTA change: nothing
    should link to the GitHub issue chooser anymore, on any page - it forces
    an extra click (pick a template) before a user can write feedback."""
    failures: list[str] = []
    for p in pages:
        if CHOOSER_URL_FRAGMENT in read(p):
            failures.append(f"{p}: still links to the issue chooser ({CHOOSER_URL_FRAGMENT})")
    return failures


def check_stylesheet_present(pages: list[str]) -> list[str]:
    """Every page must link the shared css/tweetfeed.css. tos/index.html
    shipped without it and its nav CTA rendered as unstyled black text -
    check_feedback_cta asserts the CTA markup exists, not that the stylesheet
    which dresses it actually loads. Substring match covers ../css/,
    ../../css/ and 404.html's /tweetfeed-stage/css/ form."""
    failures: list[str] = []
    for p in pages:
        if "css/tweetfeed.css" not in read(p):
            failures.append(f"{p}: missing css/tweetfeed.css <link>")
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


def check_duplicate_ids(pages: list[str]) -> list[str]:
    """Every id="..." on a page must be unique - duplicate ids break
    getElementById/jQuery id selectors, which silently resolve to only the
    first match and leave any duplicate untouched. Caught trends/index.html
    shipping a second, empty <p id="trendsGeneratedLine"> glued onto the
    freshness comment (2026-09-02): $('#trendsGeneratedLine') only ever
    reached the first element, so prod painted a stray empty paragraph."""
    # (?<![-\w]) and not \b: `\bid="` matches INSIDE `data-website-id="`,
    # because the hyphen before it is a word boundary. That would fold the
    # Umami site id into the id namespace of every page.
    id_re = re.compile(r'(?<![-\w])id="([^"]+)"')
    failures: list[str] = []
    for p in pages:
        counts: dict[str, int] = {}
        for m in id_re.finditer(read(p)):
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        for i, n in sorted(counts.items()):
            if n > 1:
                failures.append(f"{p}: id \"{i}\" appears {n} times")
    return failures


# Files describing the /v1/campaigns machine-facing contract (schema +
# discovery docs). Kept in sync by hand - added 2026-08-16 after the
# 2026-08-13 window change (7d -> 30d) shipped in the API but left these
# stale.
MACHINE_SURFACE_FILES = [
    "openapi.yaml",
    ".well-known/mcp/server-card.json",
    ".well-known/agent-skills/index.json",
    ".well-known/agent-skills/tweetfeed-ioc-lookup/SKILL.md",
    ".well-known/agent-skills/tweetfeed-iocs/SKILL.md",
    "AGENTS.md",
    "llms.txt",
    "llms-full.txt",
]


# Fields campaigns/index.html actually reads off a Campaign object (grep the
# page's JS for `c.<field>`/`c['<field>']` before trusting this list - it is
# hand-maintained, not derived). Added 2026-08-23 alongside the honesty-label
# batch (member_cluster_ids/anchors render the "merged from N pre-clusters"
# and evidence blocks; targeted_sector/targeted_country render in the
# apparent-target chip/line) so the openapi Campaign schema can never again
# document less than the page consumes.
CAMPAIGN_PAGE_FIELDS = (
    "id", "name", "context", "confidence", "targeted_brand", "targeted_sector",
    "targeted_country", "ttps", "first_seen", "last_seen", "ioc_count", "ioc_count_1d",
    "ioc_count_7d", "ioc_count_30d", "types", "tags", "reporters", "iocs",
    "member_cluster_ids", "anchors",
    # Added 2026-08-29 for the accordion-list redesign: all five are OPTIONAL
    # (build-time ASN join / enrichment rollups), absent from every campaign
    # in the live payload as of this date, and every read on the page is
    # behind a presence check - see campaigns/index.html's renderAct/
    # renderFamiliesRow/renderInfra.
    "activity", "enriched_count", "threat_types", "families", "infra",
)

# Fields the same page reads off each sampled Ioc object inside a campaign
# (c.iocs[i].<field>) - same freshness caveat as CAMPAIGN_PAGE_FIELDS above.
IOC_PAGE_FIELDS = (
    "date", "user", "type", "value", "tags", "tweet",
    # Added 2026-08-29: optional per-IOC enrichment mirrors of GET /v1/ioc's
    # `ai`/`net` objects, same presence-check discipline as the campaign
    # fields above.
    "ai", "net",
)


def check_machine_surfaces(pages: list[str]) -> list[str]:
    """The /v1/campaigns contract must stay in sync across openapi.yaml and
    the machine-facing discovery docs: (1) the Campaigns `window` enum must
    be exactly `month` (it was `week` before 2026-08-13); (2) the Campaign
    schema must document every field campaigns/index.html actually consumes
    (CAMPAIGN_PAGE_FIELDS), and the Ioc schema every field it reads off a
    sampled campaign IOC (IOC_PAGE_FIELDS) - added 2026-08-23 after
    targeted_sector/targeted_country/tweet shipped on the page ahead of the
    schema; (3) no campaign-related line may still claim a 7-day window -
    scoped to lines mentioning 'campaign' so the legitimate 7-day /v1/week
    endpoint docs are left alone. Offline, regex/line-scan based (no yaml
    import, matching the rest of this file - openapi.yaml is not valid
    enough JSON to abuse a JSON parser on, and a real YAML parser is not a
    stdlib dep)."""
    del pages  # fixed file set, not MAIN_PAGES
    failures: list[str] = []
    openapi = read("openapi.yaml")

    window_m = re.search(
        r"enum:\s*\[([^\]]*)\]\s*\n\s*description:\s*Source window for clustering",
        openapi,
    )
    if not window_m or [w.strip() for w in window_m.group(1).split(",")] != ["month"]:
        found = window_m.group(1) if window_m else "(anchor not found)"
        failures.append(f"openapi.yaml: Campaigns `window` enum is not exactly [month] (found: [{found}])")

    idx = openapi.find("\n    Campaign:\n")
    campaign_schema = openapi[idx:] if idx != -1 else ""
    for field in CAMPAIGN_PAGE_FIELDS:
        if not re.search(rf"^        {field}:", campaign_schema, re.MULTILINE):
            failures.append(f"openapi.yaml: Campaign schema missing `{field}` property (consumed by campaigns/index.html)")

    ioc_idx = openapi.find("\n    Ioc:\n")
    # Bounded to the next schema key (IocRecord immediately follows Ioc in
    # openapi.yaml) - unlike campaign_schema above, Ioc is NOT the last
    # schema in the file, and IocRecord/IocLookupResult both redeclare
    # `type`/`value`/`tags`, so an unbounded slice would let a field missing
    # from Ioc itself pass by matching one of those instead.
    ioc_end = openapi.find("\n    IocRecord:\n")
    ioc_schema = openapi[ioc_idx:ioc_end] if ioc_idx != -1 and ioc_end != -1 else ""
    for field in IOC_PAGE_FIELDS:
        if not re.search(rf"^        {field}:", ioc_schema, re.MULTILINE):
            failures.append(f"openapi.yaml: Ioc schema missing `{field}` property (consumed by campaigns/index.html sample IOCs)")

    seven_day_re = re.compile(r"7[- ]day", re.IGNORECASE)
    for name in MACHINE_SURFACE_FILES:
        for i, line in enumerate(read(name).splitlines(), start=1):
            if "campaign" in line.lower() and seven_day_re.search(line):
                failures.append(f"{name}:{i}: still claims a 7-day window: {line.strip()}")

    return failures


# Trigger substrings for anything that documents the /v1/ioc single-value
# lookup (path, MCP tool name, skill slug, or schema name).
IOC_LOOKUP_TRIGGERS = ("/v1/ioc", "enrich_ioc", "ioc-lookup", "IocLookupResult")


def check_ioc_archive_surfaces(pages: list[str]) -> list[str]:
    """The /v1/ioc archive block (added 2026-08-23: an additive `archive`
    field on IocLookupResult covering everything published before the
    365-day window, back to `first_date` in TweetFeed/archive/meta.json)
    must be documented everywhere the live 365-day lookup is documented,
    and the old "365 days is a hard ceiling" claim must not survive
    anywhere. Sibling to check_machine_surfaces (which stays scoped to
    /v1/campaigns per its own docstring - do not widen that one instead of
    adding this). Offline, regex/line-scan based (no yaml import), same
    style as the rest of this file.

    The archive-mention check (b below) is file-level, not same-line: a
    pretty-printed JSON manifest (index.json) splits `name`/`url` and
    `description` across separate lines, so requiring the trigger and the
    word `archive` on one physical line would false-fail there. What
    matters is that a file which talks about /v1/ioc at all also talks
    about archive somewhere."""
    del pages  # fixed file set, not MAIN_PAGES
    failures: list[str] = []
    openapi = read("openapi.yaml")

    # (a) IocLookupResult schema has an `archive` property, and the file
    # carries the literal archive-window string.
    m = re.search(
        r"\n    IocLookupResult:\n(.*?)(?=\n    [A-Za-z_][A-Za-z0-9_]*:\n)",
        openapi,
        re.DOTALL,
    )
    lookup_schema = m.group(1) if m else ""
    if not m or "archive:" not in lookup_schema:
        failures.append("openapi.yaml: IocLookupResult schema is missing an `archive` property")
    if "pre-365d" not in openapi:
        failures.append("openapi.yaml: missing the literal `pre-365d` archive window string")

    # (b) Any machine-surface file that documents the ioc-lookup surface at
    # all must also mention `archive` somewhere in the same file.
    for name in MACHINE_SURFACE_FILES:
        text = read(name)
        if any(t in text for t in IOC_LOOKUP_TRIGGERS) and "archive" not in text:
            failures.append(f"{name}: documents the /v1/ioc lookup surface but never mentions `archive`")

    # (c) The retired "365 days is a hard ceiling" claim must be gone.
    for name in MACHINE_SURFACE_FILES:
        for i, line in enumerate(read(name).splitlines(), start=1):
            if "values older than that return" in line:
                failures.append(f"{name}:{i}: retired 365-day-ceiling claim still present: {line.strip()}")

    return failures


# Files that genuinely ENUMERATE the REST surface (a route list a human or
# agent would read to discover what exists), as opposed to files that only
# mention one endpoint in passing. Deliberately NOT the same set as
# MACHINE_SURFACE_FILES - added 2026-09-05 alongside /v1/status and
# /v1/manifest, after checking each candidate file by hand (see the task
# report for the read-and-decide trail):
#   - .well-known/mcp/server-card.json documents MCP TOOLS (a different
#     abstraction over the same data), not a literal REST path list -
#     forcing every /v1/... path into its tool descriptions would fight
#     the file's own design rather than fix a real gap.
#   - .well-known/agent-skills/index.json and the individual SKILL.md files
#     are single-capability deep-dives (one endpoint each), not general
#     endpoint enumerations - there is no "every route should be mentioned
#     here" invariant to check on any one of them.
API_SURFACE_FILES = [
    "AGENTS.md",
    "llms.txt",
    "llms-full.txt",
]

# Matches a literal path key at the top level of `paths:` in openapi.yaml,
# e.g. "  /v1/counts:" - two-space indent, ends the line right after the
# colon (the nested `get:` etc. sit on following lines, more indented).
API_PATH_KEY_RE = re.compile(r"^  (/v1/\S*):$", re.MULTILINE)


def check_api_surface_parity(pages: list[str]) -> list[str]:
    """One direction only: openapi.yaml is the source of truth, and every
    /v1/... path documented there must also be mentioned (as a substring)
    in every file in API_SURFACE_FILES - added 2026-09-05 alongside
    /v1/status and /v1/manifest, so a route that ships in the spec but
    never reaches the discovery docs cannot go unnoticed.

    This does NOT check the reverse. Removing a path from openapi.yaml
    does not make this check fail - the requirement it would have checked
    disappears along with the path key, since requirements are extracted
    FROM openapi.yaml on every run (reproduced by hand: deleting
    `/v1/manifest`'s path item yields 0 failures here). Nor does it flag a
    doc that name-drops a route the spec doesn't have. The regression test
    that IS valid - removing a path's mention from one of the
    API_SURFACE_FILES while leaving it in openapi.yaml - was run once by
    hand and reverted (see the task report).

    Path templates (a key containing `{`) are reduced to their literal
    prefix before the first `{`, with any trailing `/` stripped - e.g.
    `/v1/since/{datetime}` -> `/v1/since`, `/v1/ioc/{value}` -> `/v1/ioc`.
    The trailing-slash strip specifically matters for `/v1/ioc/{value}`:
    every doc describes that same logical endpoint via its query-string
    sibling (`/v1/ioc?value=...`), never the `/{value}` path form, so
    requiring the slash would fail on pre-existing, correct documentation
    that predates this check. `/v1/{time}` and its filtered variants all
    reduce to the same generic `/v1` prefix, which is present everywhere
    that mentions any `/v1/...` route at all - a trivial pass, not a hole
    in the check."""
    del pages  # fixed file set, not MAIN_PAGES
    failures: list[str] = []
    openapi = read("openapi.yaml")

    requirements: set[str] = set()
    for path in API_PATH_KEY_RE.findall(openapi):
        if "{" in path:
            path = path.split("{", 1)[0].rstrip("/")
        if path:
            requirements.add(path)

    for name in API_SURFACE_FILES:
        text = read(name)
        for req in sorted(requirements):
            if req not in text:
                failures.append(f"{name}: does not mention `{req}` (documented as a path in openapi.yaml)")

    return failures


def check_agent_skill_digests() -> list[str]:
    """.well-known/agent-skills/index.json pins a sha256 digest per skill so a
    consumer can cache-validate a SKILL.md without re-fetching it. Nothing
    verified those pins actually matched the file on disk before this check -
    a forgotten re-pin after editing a SKILL.md is silent, and the /v1/ioc
    archive change (2026-08-23) touches two digests at once."""
    failures: list[str] = []
    manifest = json.loads(read(".well-known/agent-skills/index.json"))
    marker = "/.well-known/agent-skills/"
    for skill in manifest.get("skills", []):
        name = skill.get("name", "<unnamed>")
        url = skill.get("url", "")
        digest = skill.get("digest", "")
        idx = url.find(marker)
        if idx == -1:
            failures.append(f"agent-skills/index.json: {name}: cannot resolve a local path from url {url!r}")
            continue
        rel_path = marker.lstrip("/") + url[idx + len(marker):]
        path = REPO_ROOT / rel_path
        if not path.is_file():
            failures.append(f"agent-skills/index.json: {name}: referenced file missing: {rel_path}")
            continue
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            failures.append(
                f"agent-skills/index.json: {name}: digest mismatch "
                f"(index.json has {digest}, {rel_path} hashes to {actual})"
            )
    return failures


# Handle values arriving from the feed are the only field that used to reach a
# URL or an attribute unvalidated: on / , /search/ and /researchers/ the same
# string escaped `user` for the href, the alt and the link text, but built
# `picSrc` and the inline `onerror=` fallback from the raw value. escapeHtml()
# alone cannot close the onerror case - the HTML parser decodes entities before
# the JS runs, so an escaped quote becomes a real quote again. The fix is to
# validate the handle first, which search/index.html's userCell() already did.
RAW_USER_PATTERNS = (
    "'pics/' + user",
    "'../pics/' + user",
)


def check_no_raw_user_interpolation(pages: list[str]) -> list[str]:
    """Regression guard for the 2026-08-20 fix: a feed-derived handle must be
    validated (the safeUser / HANDLE_RE pattern) before it is used to build a
    URL or an HTML attribute."""
    failures: list[str] = []
    for p in pages:
        body = read(p)
        for pat in RAW_USER_PATTERNS:
            if pat in body:
                failures.append(f"{p}: builds a URL from an unvalidated feed handle ({pat})")
    return failures


# Regression guard for the 2026-08-21 fix: the Google Fonts <link> requests
# used to ask for `family=Rubik` / `family=Alegreya+Sans+SC` with no :wght@
# axis, which Google Fonts serves as weight 400 ONLY - every 500/600/700/800
# in the CSS was therefore browser-synthesised, not the real face. The links
# now carry explicit axes (Rubik variable 400..700, Alegreya Sans SC static
# 400;600;800); this check keeps a future page/rule from drifting back to a
# weight nobody asked Google Fonts to serve.
TRACKED_FONT_FAMILIES = ("Rubik", "Alegreya Sans SC")
FONT_LINK_FAMILY_RE = re.compile(r"fonts\.googleapis\.com/css2\?family=([^\"&]+)")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
CSS_LEAF_BLOCK_RE = re.compile(r"\{([^{}]*)\}")
FONT_FAMILY_DECL_RE = re.compile(r"font-family\s*:\s*([^;]+);")
FONT_WEIGHT_DECL_RE = re.compile(r"font-weight\s*:\s*(\d+)\s*;")
STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
SHARED_FONT_CSS_FILES = ("css/tweetfeed.css", "css/index.css", "css/table.css")


def _page_loaded_font_weights(html: str) -> dict[str, tuple]:
    """Per tracked family, the set of weights this page's Google Fonts
    <link>s actually request. `family=X` with no `:wght@` axis loads only
    400 (Google Fonts default). Returned as ('set', frozenset[int]) for an
    explicit list or ('range', lo, hi) for a variable-font closed range."""
    loaded: dict[str, tuple] = {}
    for m in FONT_LINK_FAMILY_RE.finditer(html):
        spec = m.group(1)
        name_part, _, weight_part = spec.partition(":wght@")
        family = name_part.replace("+", " ")
        if family not in TRACKED_FONT_FAMILIES:
            continue
        if not weight_part:
            loaded[family] = ("set", frozenset({400}))
        elif ".." in weight_part:
            lo, hi = weight_part.split("..", 1)
            loaded[family] = ("range", int(lo), int(hi))
        else:
            weights = frozenset(int(w) for w in weight_part.split(";") if w.strip().isdigit())
            loaded[family] = ("set", weights)
    return loaded


def _weight_loaded(spec: tuple, weight: int) -> bool:
    if spec[0] == "range":
        return spec[1] <= weight <= spec[2]
    return weight in spec[1]


def _describe_loaded(spec: tuple) -> str:
    if spec[0] == "range":
        return f"{{{spec[1]}..{spec[2]}}}"
    return "{" + ", ".join(str(w) for w in sorted(spec[1])) + "}"


def _same_block_family_weights(css_text: str) -> set[tuple[str, int]]:
    """(family, weight) pairs where a tracked font-family and a numeric
    font-weight are set in the SAME leaf declaration block. Comments are
    stripped first so prose that merely mentions a family/weight is never
    mistaken for a rule. No cascade/inheritance resolution on purpose -
    conservative by design, so it can miss cases but must never false-fail."""
    text = CSS_COMMENT_RE.sub("", css_text)
    pairs: set[tuple[str, int]] = set()
    for block in CSS_LEAF_BLOCK_RE.findall(text):
        fam_m = FONT_FAMILY_DECL_RE.search(block)
        weight_m = FONT_WEIGHT_DECL_RE.search(block)
        if not fam_m or not weight_m:
            continue
        fam_value = fam_m.group(1)
        weight = int(weight_m.group(1))
        for family in TRACKED_FONT_FAMILIES:
            if family in fam_value:
                pairs.add((family, weight))
    return pairs


# Families deliberately requested at 400 only, so their bold is synthesised.
# See check_font_weights_loaded's docstring for why these are here.
SYNTHETIC_BOLD_BY_DESIGN = {"Alegreya Sans SC", "Rubik"}


def check_font_weights_loaded(pages: list[str]) -> list[str]:
    """Every font-weight paired with a tracked family in the shared CSS or a
    page's own <style> blocks must be a weight that page's Google Fonts
    <link>s actually load - otherwise the browser is back to synthesising a
    bold that was never served (see TRACKED_FONT_FAMILIES comment above).

    SYNTHETIC_BOLD_BY_DESIGN holds the deliberate exceptions. BOTH of the
    site's families are in it, and both for the same reason: the owner looked
    at the real cuts and rejected them.

    Alegreya Sans SC is the hero wordmark. Its real 700 and 800 are a heavier,
    more condensed face than the 400 the browser was faking, loading them
    visibly changed the wordmark, and it was rejected on sight (2026-08-22).
    .toph1 / .cardTitle are synthesised as a result.

    Rubik went the same way one day later. It dresses the navbar - .tf-wordmark
    at 600, .tf-navlink and .nav-cta at 500 - and switching from a faked bold
    over the 400 to the real 500/600 changed the wordmark's drawing (measured:
    "TweetFeed" at 20px went 101.8px at every weight to 101.8 / 105.85 / 107.8
    / 109.88). The owner rejected that too, so the family went back to
    `family=Rubik` with no weight axis on 2026-08-22 and every Rubik bold on
    the site - navbar, body copy, footer, tables - is synthetic again.

    Both are typographic compromises taken with eyes open, not the bug this
    check exists to catch. Any family added later is still enforced. Do NOT
    "fix" either of these by adding a :wght@ axis without showing the owner a
    before/after render first: that is exactly how both got reverted."""
    shared_pairs = _same_block_family_weights(
        "\n".join(read(name) for name in SHARED_FONT_CSS_FILES)
    )
    failures: list[str] = []
    for p in pages:
        html = read(p)
        loaded = _page_loaded_font_weights(html)
        if not loaded:
            continue  # page requests neither tracked family - out of scope
        page_pairs = _same_block_family_weights(
            "\n".join(m.group(1) for m in STYLE_BLOCK_RE.finditer(html))
        )
        for family, weight in sorted(shared_pairs | page_pairs):
            if family in SYNTHETIC_BOLD_BY_DESIGN:
                continue  # deliberate, see the docstring
            if family not in loaded:
                continue  # page never loads this family - out of scope
            if not _weight_loaded(loaded[family], weight):
                failures.append(
                    f"{p}: {family} weight {weight} used but only "
                    f"{_describe_loaded(loaded[family])} loaded"
                )
    return failures


# Page-content checks: the 21 hand-written pages carrying real copy.
CHECKS = [
    ("Canonical URLs", check_canonicals),
    ("Analytics scripts (anchor + Umami + Ahrefs)", check_analytics),
    ("Meta description length (80-160)", check_meta_description_length),
    ("Single <h1> per page", check_single_h1),
    ("Machine-facing campaigns contract (openapi + discovery docs)", check_machine_surfaces),
    ("Machine-facing /v1/ioc archive contract (openapi + discovery docs)", check_ioc_archive_surfaces),
    ("API surface parity (openapi.yaml paths vs discovery docs)", check_api_surface_parity),
]

# Shell checks run over EVERY html page, not just MAIN_PAGES. The shell is on
# all of them, and the 25 tag pages, 10 campaign pages, tags/, ioc-types/ and
# 404.html previously had no nav validation at all.
SHELL_CHECKS = [
    ("Nav matches site_ia (desktop + More + right + mobile)", check_nav_order),
    ("Dropdown menu count (exactly 2)", check_dropdown_menu_count),
    ("Dividers are <hr>, not <div>", check_no_div_divider),
    ("Footer pattern (desktop + mobile)", check_footers),
    ("Footer links match site_ia", check_footer_parity),
    ("Footer column headings present", check_footer_headings),
    ("Nav/footer links resolve", check_links_resolve),
    ("Docs sidebar matches site_ia", check_docs_sidebar),
    ("Feedback CTA (button, direct template link)", check_feedback_cta),
    ("Font weights used are weights the page's Google Fonts <link> loads", check_font_weights_loaded),
    ("Duplicate HTML ids", check_duplicate_ids),
]


# Classes whose NAME is built at runtime from the data, so they never appear as
# a literal `class="..."` anywhere and no static audit can see them.
RUNTIME_APPLIED_CLASSES = {
    "css/tweetfeed.css": [".url", ".domain", ".ip", ".sha256", ".md5"],
}


def check_runtime_applied_classes() -> list[str]:
    """The IOC-table row tints are applied by jQuery from the Type column's
    text - index.html:775 and search/index.html:1263 call toggleClass() with it
    on the first draw, and lines 719 / 1215 call addClass(type) on the rows the
    poller appends. Nothing ever writes class="url" into the HTML.

    That makes them invisible to a "which selectors does the markup use" grep.
    On 2026-08-22 exactly that audit called all five dead and removed them, the
    home and /search/ tables went white, and no other check noticed: the served
    HTML was still correct and the breakage only existed once the page painted.

    This check exists so the next person cannot repeat it. If a rule here is
    genuinely obsolete, delete it from this list in the same commit and say why."""
    failures: list[str] = []
    for css_file, selectors in RUNTIME_APPLIED_CLASSES.items():
        text = CSS_COMMENT_RE.sub("", read(css_file))
        for sel in selectors:
            if not re.search(rf"^\s*{re.escape(sel)}\s*(,|\{{)", text, re.M):
                failures.append(
                    f"{css_file}: `{sel}` is missing. It is applied at runtime "
                    f"(see this check's docstring); a grep for class=\"{sel[1:]}\" "
                    f"will never find it, so do not conclude it is unused."
                )
    return failures


# Whole-repo invariants that take no page list.

# ─────────────────────────────────────────────────────────────────────────────
# Hardcoded "past year" counts in meta/og/twitter descriptions
# ─────────────────────────────────────────────────────────────────────────────
# Measured 2026-08-22: three of the four pages that quote a year-window count
# were OVERSTATING it in the SERP snippet. /malicious-ips/ claimed "20k+ past
# year" against a real 9,625; MD5 claimed 3.4k+ against 2,486; URLs claimed
# 58k+ against 53,667. SHA-256 was stale the other way (1.3k+ vs 2,675).
# Nobody noticed because the numbers were typed by hand once and the feed kept
# moving. A threat feed overstating its own corpus in a search result is the
# kind of error that costs more than it gains, so it gets a gate.
#
# Deliberately tolerant in one direction only: understating is allowed (it is
# merely stale), overstating fails. Network failure SKIPS rather than fails,
# so an offline local run of this script stays useful.
#
# The feed URL, the page->type map and the claim regex moved to
# scripts/year_counts.py on 2026-08-23, so bake_year_counts.py generates the
# copy from EXACTLY what this gate reads. They used to be duplicated, which is
# the general shape of the bug that took the daily workflow down that morning:
# a number produced by one code path and judged by another.
def check_year_counts() -> list[str]:
    real = fetch_year_counts()
    if real is None:
        print("  (skipped: year.csv unreachable, offline run)")
        return []
    failures: list[str] = []
    for page, ioc_type in YEAR_CLAIM_PAGES.items():
        html = read(page)
        claims = {m.group(1) for m in YEAR_CLAIM_RE.finditer(html)}
        if not claims:
            failures.append(f"{page}: no 'Nk+ ... past year' claim found; the check has drifted from the copy")
            continue
        actual = real.get(ioc_type, 0)
        for c in claims:
            claimed = int(float(c) * 1000)
            if claimed > actual:
                failures.append(
                    f"{page}: claims {c}k+ {ioc_type} in the past year, real count is {actual:,}"
                )
    return failures


def check_integration_anchors() -> list[str]:
    """Every internal INTEGRATIONS/INTEGRATIONS_MORE href that carries a
    #fragment must resolve: the target file must exist AND contain that
    literal id="...".

    The "Integrated in" band used to be hardcoded HTML on the home page, with
    nothing checking that its links still pointed at a real heading. Once
    OpenCTI/IntelOwl started pointing at our own /hunt/ recipes instead of
    third-party URLs (2026-09-03), a renamed or removed id="stack-..." would
    have rotted the link silently - the band still renders, it just points at
    nothing. This check makes that impossible to ship unnoticed."""
    failures: list[str] = []
    entries = [(i.name, i.href) for i in ia.INTEGRATIONS]
    entries += [(l.label, l.href) for l in ia.INTEGRATIONS_MORE]
    for name, href in entries:
        if href.startswith(("http://", "https://")) or "#" not in href:
            continue
        path, frag = href.split("#", 1)
        target = Path(path) if path.endswith(".html") else Path(path) / "index.html"
        if not (REPO_ROOT / target).is_file():
            failures.append(f"{name} ({href}): target file {target} does not exist")
            continue
        if f'id="{frag}"' not in read(str(target)):
            failures.append(f'{name} ({href}): {target} has no id="{frag}"')
    return failures


GLOBAL_CHECKS = [
    ("Runtime-applied CSS classes still exist", check_runtime_applied_classes),
    ("No orphan pages (reachable from nav or footer)", check_orphan_pages),
    ("Cache-bust uniform (every versioned local asset)", check_cachebust_uniform),
    ("Templates include the shell partials", check_templates_include_shell),
    ("Year-window counts in descriptions are not overstated", check_year_counts),
    ("Agent Skills index.json digests match SKILL.md files on disk", check_agent_skill_digests),
    ("Integration band anchors resolve (site_ia hrefs -> real id=\"...\")", check_integration_anchors),
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
    # Exclude the shell partials: they are fragments included into templates,
    # with no <head> of their own.
    pages = [p for p in pages if not Path(p).name.startswith("_")]
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

    shell_pages = all_html_pages()
    for label, fn in SHELL_CHECKS:
        failures = fn(shell_pages)
        if not failures:
            print(f"[PASS] {label}: all {len(shell_pages)} pages OK")
        else:
            print(f"[FAIL] {label}: {len(failures)} issue(s)")
            for f in failures:
                print(f"  - {f}")
            total_failures += len(failures)

    for label, fn in GLOBAL_CHECKS:
        failures = fn()
        if not failures:
            print(f"[PASS] {label}: OK")
        else:
            print(f"[FAIL] {label}: {len(failures)} issue(s)")
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

    pages_css = sorted(set(pages_all) | set(landing_pages()))
    failures = check_stylesheet_present(pages_css)
    if not failures:
        print(f"[PASS] Stylesheet link (site-wide): all {len(pages_css)} pages OK")
    else:
        print(f"[FAIL] Stylesheet link (site-wide): {len(failures)} issue(s)")
        for f in failures:
            print(f"  - {f}")
        total_failures += len(failures)

    # Full-site scan (not just MAIN_PAGES/landing_pages): the chooser link
    # must not reappear anywhere, including stray hub pages no other check
    # covers yet (see MAIN_PAGES comment above on 404.html/tos/malicious-*).
    failures = check_no_chooser_link(pages_all)
    if not failures:
        print(f"[PASS] No issue-chooser links (site-wide): all {len(pages_all)} pages OK")
    else:
        print(f"[FAIL] No issue-chooser links (site-wide): {len(failures)} issue(s)")
        for f in failures:
            print(f"  - {f}")
        total_failures += len(failures)

    # Feed-derived handles must be validated before they reach a URL or an
    # attribute. Site-wide because the same avatar markup is duplicated across
    # index.html, search/ and researchers/.
    failures = check_no_raw_user_interpolation(pages_all)
    if not failures:
        print(f"[PASS] No raw feed handle in a URL/attribute (site-wide): all {len(pages_all)} pages OK")
    else:
        print(f"[FAIL] No raw feed handle in a URL/attribute (site-wide): {len(failures)} issue(s)")
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
