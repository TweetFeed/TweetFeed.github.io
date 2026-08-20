#!/usr/bin/env python3
"""Render the site shell (navbar + footer) into every page and template.

Why this exists
---------------
TweetFeed is a static site with no build step: the nav and footer used to be
copy-pasted verbatim into 56 HTML pages AND hand-maintained inside 3 Jinja2
templates. That produced 4 divergent footer variants, left /malicious-urls/ and
both hash landing pages linked from no footer at all, and made the 2026-06-28
`d-md-block` fix regress the next morning (only the rendered pages were
patched, so the daily regen re-stamped the bug from the templates).

Now scripts/site_ia.py holds the information architecture as data,
scripts/templates/_nav.html.j2 and _footer.html.j2 hold the markup, and this
script stamps them everywhere. scripts/check_consistency.py imports site_ia and
asserts the result still matches, so the gate verifies intent.

Usage
-----
    python3 scripts/render_shell.py --check          # diff only, exit 1 on drift
    python3 scripts/render_shell.py --apply          # write
    python3 scripts/render_shell.py --apply --only 'about/*'
    python3 scripts/render_shell.py --bump-css 30    # rewrite tweetfeed.css?v=N

`--apply` then `--check` must be a no-op. That idempotency is the proof the
migration is correct.
"""

import argparse
import fnmatch
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_ia as ia  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "scripts" / "templates"
# Only the prod repo (TweetFeed.github.io) carries a CNAME. The stage clone is
# served from a subpath, so its 404 needs absolute /tweetfeed-stage/ hrefs.
REPO_IS_PROD = (REPO_ROOT / "CNAME").is_file()
STAGE_PREFIX = "/tweetfeed-stage/"

# Shell templates render at a fixed depth inside the pages they are included
# from, so the generators must pass the matching depth.
TEMPLATE_DEPTH = {
    "tag_page.html.j2": 2,
    "tags_index.html.j2": 1,
    "campaign_page.html.j2": 2,
}


# --------------------------------------------------------------------------
# Jinja environment
# --------------------------------------------------------------------------
def _add_svg_class(svg_html, extra_class):
    """Merge `extra_class` into the <svg>'s class attribute, creating one if
    absent. Only the first <svg ...> opening tag is touched (each icon SVG
    here has exactly one), and merging (not blind replace) keeps this safe
    even if the source SVG ever ships its own `class`."""
    if not extra_class:
        return svg_html

    def merge(m):
        tag = m.group(0)
        cm = re.search(r'class="([^"]*)"', tag)
        if cm:
            merged = (cm.group(1) + " " + extra_class).strip()
            return tag[: cm.start()] + f'class="{merged}"' + tag[cm.end():]
        return re.sub(r"^<svg\b", f'<svg class="{extra_class}"', tag)

    return re.sub(r"<svg\b[^>]*>", merge, svg_html, count=1)


def _icon_html(link, extra_class=""):
    """Render a site_ia.Link's icon. Font Awesome is 5.15.4, not 6."""
    if not link or not link.icon:
        return Markup("")
    cls = (" " + extra_class).rstrip()
    if link.icon == "svg:spark":
        return Markup(_add_svg_class(ia.SPARK_SVG, extra_class))
    if link.icon == "svg:x":
        return Markup(_add_svg_class(ia.X_SVG, extra_class))
    family = "fab" if link.icon in ("fa-github",) else "fas"
    return Markup(f'<i class="{family} {link.icon}{cls}" aria-hidden="true"></i>')


def _column_html(column, mobile=False, indent=None):
    """Render one footer column. `indent` is the leading whitespace the
    template places the {{ column(...) }} call at, so the emitted rows line up
    with the surrounding markup instead of collapsing to column 0."""
    heading, links = column
    head_cls = "tf-mfoot-head" if mobile else "tf-foot-head"
    link_cls = "tf-mfoot-link" if mobile else "tf-foot-link"
    if indent is None:
        indent = "\t" * (4 if mobile else 5)
    out = [f'<p class="{head_cls}">{heading}</p>']
    for link in links:
        ext = ' target="_blank" rel="noopener noreferrer"' if link.external else ""
        arrow = ' <i class="fas fa-external-link-alt tf-foot-ext" aria-hidden="true"></i>' if link.external else ""
        # External links are absolute: never prefix them with the depth base.
        href = link.href if link.external else f"{{{{HREF:{link.href}}}}}"
        out.append(f'<a class="{link_cls}" href="{href}"{ext}>{link.label}{arrow}</a>')
    return Markup(("\n" + indent).join(out))


def _env():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=False,
    )
    return env


def shell_context(depth=0, active_key=None, link_base=None, indent=None, docs_active=None):
    """Build the template context for one page depth.

    depth      0 for /index.html, 1 for /about/index.html, 2 for /tag/apt/...
    active_key site_ia key to light up, or None
    link_base  override the relative prefix (used by 404.html)
    indent     when set, also return `shell_nav` / `shell_footer` already
               rendered and indented by this prefix. The Jinja generators use
               those instead of {% include %}: an include drops the partial in
               at column 0 for every line after the first, which would make the
               generated pages differ from --apply by whitespace alone and
               break the idempotency proof.
    """
    base = link_base if link_base is not None else ("../" * depth)

    def url(link):
        if link.external:
            return link.href
        return base + link.href

    home_href = base if base else "./"

    def column(col, mobile=False, indent=None):
        html = str(_column_html(col, mobile, indent))
        # Resolve the href placeholders now that `base` is known.
        return Markup(re.sub(r"\{\{HREF:([^}]*)\}\}", lambda m: base + m.group(1), html))

    ctx = {
        "home_href": home_href,
        "url": url,
        "icon": _icon_html,
        "column": column,
        "active_key": active_key,
        "active_in_more": active_key in ia.MORE_KEYS if active_key is not None else False,
        "HOME": ia.HOME,
        "NAV_PRIMARY": ia.NAV_PRIMARY,
        "NAV_MORE": ia.NAV_MORE,
        "NAV_MOBILE": ia.nav_mobile(),
        "SEARCH": ia.SEARCH,
        "DOCS": ia.DOCS,
        "FEEDBACK_URL": ia.FEEDBACK_URL,
        "FOOTER_COLUMNS": ia.FOOTER_COLUMNS,
        "DOCS_SIDEBAR": ia.DOCS_SIDEBAR,
        "DOCS_SIDEBAR_CHILDREN": ia.DOCS_SIDEBAR_CHILDREN,
        "docs_active": docs_active,
        "FOOTER_MOBILE_COLUMNS": ia.FOOTER_MOBILE_COLUMNS,
        "FOOTER_MOBILE_LEGAL": ia.FOOTER_MOBILE_LEGAL,
        "FOOTER_SOCIAL": ia.FOOTER_SOCIAL,
        "FOOTER_TAGLINE": ia.FOOTER_TAGLINE,
        "FOOTER_BYLINE": ia.FOOTER_BYLINE,
        "FOOTER_MADE_IN": ia.FOOTER_MADE_IN,
        "FOOTER_COPYRIGHT": ia.FOOTER_COPYRIGHT,
    }
    if indent is not None:
        ctx["shell_nav"] = Markup(reindent(render_partial("_nav.html.j2", ctx), indent))
        ctx["shell_footer"] = Markup(reindent(render_partial("_footer.html.j2", ctx), indent))
        ctx["shell_docs_sidebar"] = Markup(
            reindent(render_partial("_docs_sidebar.html.j2", ctx), indent)
        )
    return ctx


def render_partial(name, ctx):
    return _env().get_template(name).render(**ctx)


# --------------------------------------------------------------------------
# Locating the shell regions
# --------------------------------------------------------------------------
# Anchor on the tag signature, never on marker comments (4 pages ship without
# them) and never on ordinal position (feeds/ has 3 <nav>, hunt/ has 6 because
# of content-level nav.page-toc elements).
REGION_ANCHORS = {
    "sidebar_start": re.compile(r'<aside\b[^>]*\bdocs-sidebar\b[^>]*>', re.I),
    "nav_start": re.compile(r'<nav\b[^>]*\bnavbar-expand-lg\b[^>]*\bfixed-top\b[^>]*>', re.I),
    "nav_end": re.compile(r'<nav\b(?![^>]*\bnavbar-expand-lg\b)[^>]*\bnavbar-expand\b[^>]*\bd-lg-none\b[^>]*>', re.I),
    "foot_start": re.compile(r'<footer\b[^>]*\bd-none\b[^>]*\bd-lg-block\b[^>]*>', re.I),
    "foot_end": re.compile(r'<footer\b[^>]*\bsticky-footer\b[^>]*\bd-lg-none\b[^>]*>', re.I),
}

# Structural marker comments are normalized away before each rewrite and
# re-emitted by the partials, so every page ends up with exactly one of each.
# Absorbing them by adjacency instead was NOT idempotent: on the 43
# docs-sidebar pages the original `<!-- Footer -->` sat above `</main></div>`,
# two lines away from the <footer> it labelled, so it survived the rewrite and
# the freshly emitted marker duplicated it on every run.
MARKER_LINE_RE = re.compile(
    r'^[ \t]*<!--\s*(?:Top bar end|Top bar|End of Footer|Footer|MOBILE)\s*-->[ \t]*(?:\r?\n|$)',
    re.M | re.I,
)


def close_element(html, start, tag):
    """Return the index just past the balanced closing tag for the element
    that opens at `start`. A non-greedy `.*?</tag>` is not safe here: this
    codebase already nests <nav> inside content, and a scanner keeps the tool
    correct if the shell ever gains a nested element."""
    open_re = re.compile(r"<" + tag + r"\b", re.I)
    close_re = re.compile(r"</" + tag + r"\s*>", re.I)
    depth = 0
    i = start
    while True:
        m_open = open_re.search(html, i)
        m_close = close_re.search(html, i)
        if m_close is None:
            raise ValueError(f"unbalanced <{tag}> starting at offset {start}")
        if m_open is not None and m_open.start() < m_close.start():
            depth += 1
            i = m_open.end()
        else:
            depth -= 1
            i = m_close.end()
            if depth == 0:
                return i


def find_region(html, kind):
    """Return (start, end) covering both blocks of a region plus its markers."""
    if kind == "sidebar":
        # Unlike nav and footer, this region is ONE element, not a pair.
        m = REGION_ANCHORS["sidebar_start"].search(html)
        if not m:
            raise ValueError("no docs sidebar found")
        end = close_element(html, m.start(), "aside")
        return html.rfind("\n", 0, m.start()) + 1, end
    if kind == "nav":
        first, second, tag = REGION_ANCHORS["nav_start"], REGION_ANCHORS["nav_end"], "nav"
    else:
        first, second, tag = REGION_ANCHORS["foot_start"], REGION_ANCHORS["foot_end"], "footer"

    m1 = first.search(html)
    if not m1:
        raise ValueError(f"no {kind} desktop block found")
    end1 = close_element(html, m1.start(), tag)

    m2 = second.search(html, end1)
    if not m2:
        raise ValueError(f"no {kind} mobile block found after the desktop one")
    between = html[end1:m2.start()]
    if re.sub(r"\s+|<!--.*?-->", "", between, flags=re.S):
        raise ValueError(
            f"{kind}: unexpected content between the desktop and mobile blocks: {between[:120]!r}"
        )
    end2 = close_element(html, m2.start(), tag)

    # Start at the beginning of the opening tag's line so its indentation is
    # replaced rather than doubled.
    start = html.rfind("\n", 0, m1.start()) + 1
    return start, end2


def indent_of(html, start):
    """Leading whitespace of the line the region starts on."""
    line_start = html.rfind("\n", 0, start) + 1
    m = re.match(r"[ \t]*", html[line_start:])
    return m.group(0)


def reindent(block, prefix):
    """Indent a rendered block, converting tabs to spaces when the host file
    is space-indented (404.html uses 4 spaces; everything else uses tabs)."""
    use_spaces = "\t" not in prefix and prefix != ""
    lines = []
    for line in block.split("\n"):
        if not line.strip():
            lines.append("")
            continue
        if use_spaces:
            stripped = line.lstrip("\t")
            line = "    " * (len(line) - len(stripped)) + stripped
        lines.append(prefix + line)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Page enumeration
# --------------------------------------------------------------------------
def html_pages():
    return sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*.html")
        if not any(part in (".git", "node_modules", "vendor") for part in p.parts)
    )


def page_params(page):
    """(depth, link_base, active_key) for a page path."""
    depth = page.count("/")
    link_base = None
    if page == "404.html":
        link_base = STAGE_PREFIX if not REPO_IS_PROD else "/"
    return depth, link_base, ia.active_key_for(page)


def render_for(page):
    depth, link_base, active = page_params(page)
    docs_active = ia.docs_sidebar_active_for(page)
    ctx = shell_context(
        depth=depth, active_key=active, link_base=link_base, docs_active=docs_active
    )
    sidebar = render_partial("_docs_sidebar.html.j2", ctx) if docs_active else None
    return (
        render_partial("_nav.html.j2", ctx),
        render_partial("_footer.html.j2", ctx),
        sidebar,
    )


def rewrite(html, page):
    nav, foot, sidebar = render_for(page)
    html = MARKER_LINE_RE.sub("", html)
    if sidebar is not None and REGION_ANCHORS["sidebar_start"].search(html):
        start, end = find_region(html, "sidebar")
        # The region ends exactly at </aside> with no trailing newline, so the
        # rendered block must not carry one either: otherwise every --apply
        # inserted one more blank line and the run never converged.
        html = (
            html[:start]
            + reindent(sidebar.rstrip("\n"), indent_of(html, start))
            + html[end:]
        )
    for kind, block in (("nav", nav), ("foot", foot)):
        start, end = find_region(html, kind)
        prefix = indent_of(html, start)
        html = html[:start] + reindent(block, prefix) + html[end:]
    return html


# --------------------------------------------------------------------------
# Templates: swap the shell for an {% include %}
# --------------------------------------------------------------------------
# Emitted at column 0 on purpose: shell_context(indent=...) hands the
# generator a block that is already indented on every line, first one included.
INCLUDE_NAV = "{{ shell_nav }}"
INCLUDE_FOOT = "{{ shell_footer }}"
INCLUDE_SIDEBAR = "{{ shell_docs_sidebar }}"


def rewrite_template(text):
    text = MARKER_LINE_RE.sub("", text)
    for kind, inc in (("sidebar", INCLUDE_SIDEBAR), ("nav", INCLUDE_NAV), ("foot", INCLUDE_FOOT)):
        try:
            start, end = find_region(text, kind)
        except ValueError:
            continue  # already converted to an include
        text = text[:start] + inc + text[end:]
    return text


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
# Both files are versioned together. index.css shipped for years with NO
# cache-bust at all, which meant a change to it simply never reached anyone
# with a warm cache: the hover fix of 2026-08-18 landed on the origin and the
# live site kept the old behaviour until this was added.
CSS_BUST_FILES = ("tweetfeed.css", "index.css")


def bump_css(version, apply_):
    pat = re.compile(r"((?:" + "|".join(f.replace(".", r"\.") for f in CSS_BUST_FILES) + r")\?v=)(\d+)")
    # Adds the parameter where it is missing (index.css had none).
    add = re.compile(r'(href="[^"]*(?:' + "|".join(f.replace(".", r"\.") for f in CSS_BUST_FILES) + r'))"')
    changed = []
    targets = [REPO_ROOT / p for p in html_pages()]
    targets += sorted(TEMPLATE_DIR.glob("*.j2"))
    for path in targets:
        text = path.read_text(encoding="utf-8")
        new = add.sub(lambda m: m.group(1) + f'?v={version}"', text)
        new = pat.sub(lambda m: m.group(1) + str(version), new)
        if new != text:
            changed.append(str(path.relative_to(REPO_ROOT)))
            if apply_:
                path.write_text(new, encoding="utf-8")
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default=None, help="glob over repo-relative page paths")
    ap.add_argument("--bump-css", type=int, default=None)
    args = ap.parse_args()

    if args.bump_css is not None:
        changed = bump_css(args.bump_css, args.apply)
        verb = "bumped" if args.apply else "would bump"
        print(f"{verb} tweetfeed.css?v={args.bump_css} in {len(changed)} file(s)")
        if not args.apply and changed:
            return 1
        return 0

    if not (args.check or args.apply):
        ap.error("pass --check or --apply")

    pages = html_pages()
    if args.only:
        pages = [p for p in pages if fnmatch.fnmatch(p, args.only)]

    drift, errors = [], []
    for page in pages:
        path = REPO_ROOT / page
        text = path.read_text(encoding="utf-8")
        try:
            new = rewrite(text, page)
        except ValueError as exc:
            errors.append(f"{page}: {exc}")
            continue
        if new != text:
            drift.append(page)
            if args.apply:
                path.write_text(new, encoding="utf-8")

    tpl_drift = []
    if not args.only:
        for tpl in sorted(TEMPLATE_DIR.glob("*.j2")):
            if tpl.name.startswith("_"):
                continue
            text = tpl.read_text(encoding="utf-8")
            new = rewrite_template(text)
            if new != text:
                tpl_drift.append(tpl.name)
                if args.apply:
                    tpl.write_text(new, encoding="utf-8")

    for e in errors:
        print(f"[ERROR] {e}", file=sys.stderr)
    verb = "rewrote" if args.apply else "drift in"
    print(f"{verb} {len(drift)} page(s), {len(tpl_drift)} template(s); {len(pages)} scanned")
    if drift and not args.apply:
        for p in drift[:80]:
            print(f"  - {p}")
    if errors:
        return 2
    if (drift or tpl_drift) and not args.apply:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
