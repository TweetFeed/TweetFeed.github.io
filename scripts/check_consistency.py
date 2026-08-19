#!/usr/bin/env python3
"""Consistency checks across the 21 main pages of TweetFeed.

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

import os
import re
import sys
from collections import Counter
from pathlib import Path

# The 21 user-facing main pages - the ones that share nav, footer, analytics,
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
    and /malicious-hashes-sha256/ sitting in no footer at all."""
    reachable = set(ia.internal_footer_targets())
    reachable |= {l.href for l in ia.NAV_PRIMARY}
    reachable |= {l.href for l in ia.nav_more_links() if not l.external}
    reachable |= {ia.SEARCH.href, ia.DOCS.href, ""}
    failures: list[str] = []
    for path in sorted(REPO_ROOT.glob("*/index.html")):
        d = path.parent.name + "/"
        if d in reachable:
            continue
        # tag/ and campaigns/ subtrees are reached through their hub pages.
        if d in ("tag/",):
            continue
        failures.append(f"/{d} exists but is linked from neither the nav nor the footer")
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


# Files describing the /v1/campaigns machine-facing contract (schema +
# discovery docs). Kept in sync by hand - added 2026-08-16 after the
# 2026-08-13 window change (7d -> 30d) shipped in the API but left these
# stale.
MACHINE_SURFACE_FILES = [
    "openapi.yaml",
    ".well-known/mcp/server-card.json",
    ".well-known/agent-skills/index.json",
    "AGENTS.md",
    "llms.txt",
    "llms-full.txt",
]


def check_machine_surfaces(pages: list[str]) -> list[str]:
    """The /v1/campaigns contract must stay in sync across openapi.yaml and
    the machine-facing discovery docs: (1) the Campaigns `window` enum must
    be exactly `month` (it was `week` before 2026-08-13); (2) the Campaign
    schema must expose the per-window `ioc_count_1d/7d/30d` activity fields;
    (3) no campaign-related line may still claim a 7-day window - scoped to
    lines mentioning 'campaign' so the legitimate 7-day /v1/week endpoint
    docs are left alone. Offline, regex/line-scan based (no yaml import,
    matching the rest of this file - openapi.yaml is not valid enough JSON
    to abuse a JSON parser on, and a real YAML parser is not a stdlib dep)."""
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
    for field in ("ioc_count_1d", "ioc_count_7d", "ioc_count_30d"):
        if not re.search(rf"^        {field}:", campaign_schema, re.MULTILINE):
            failures.append(f"openapi.yaml: Campaign schema missing `{field}` property")

    seven_day_re = re.compile(r"7[- ]day", re.IGNORECASE)
    for name in MACHINE_SURFACE_FILES:
        for i, line in enumerate(read(name).splitlines(), start=1):
            if "campaign" in line.lower() and seven_day_re.search(line):
                failures.append(f"{name}:{i}: still claims a 7-day window: {line.strip()}")

    return failures


# Page-content checks: the 21 hand-written pages carrying real copy.
CHECKS = [
    ("Canonical URLs", check_canonicals),
    ("Analytics scripts (anchor + Umami + Ahrefs)", check_analytics),
    ("Meta description length (80-160)", check_meta_description_length),
    ("Single <h1> per page", check_single_h1),
    ("Machine-facing campaigns contract (openapi + discovery docs)", check_machine_surfaces),
]

# Shell checks run over EVERY html page, not just MAIN_PAGES. The shell is on
# all of them, and the 22 tag pages, 10 campaign pages, tags/, ioc-types/ and
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
]

# Whole-repo invariants that take no page list.
GLOBAL_CHECKS = [
    ("No orphan pages (reachable from nav or footer)", check_orphan_pages),
    ("Cache-bust uniform (every versioned local asset)", check_cachebust_uniform),
    ("Templates include the shell partials", check_templates_include_shell),
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

    print()
    if total_failures == 0:
        print(f"All checks passed across {len(MAIN_PAGES)} pages.")
        return 0
    print(f"Total: {total_failures} consistency issue(s) across {len(MAIN_PAGES)} pages.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
