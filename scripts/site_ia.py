"""Single source of truth for the TweetFeed site shell (navbar + footer).

Before 2026-08-18 the nav and footer were copy-pasted verbatim into every HTML
page and additionally hand-maintained inside the Jinja2 templates. That is how
the footer silently drifted into 4 variants and how /malicious-urls/ and both
hash landing pages ended up linked from no footer at all.

Now the information architecture lives here as data. `render_shell.py` renders
it into every page and template; `check_consistency.py` imports it and asserts
the rendered HTML still matches. The gate therefore verifies *intent*, not just
uniformity across pages (a bulk edit that wrote the same mistake everywhere
used to pass, because check_nav_order derived its baseline by majority vote).

Icons: Font Awesome **5.15.4** (see the CDN link in every <head>). Do NOT use
FA6-only names here (fa-location-dot, fa-clock-rotate-left, fa-arrow-trend-up,
fa-shield-halved); they render as empty boxes.
"""

from typing import NamedTuple

FEEDBACK_URL = "https://github.com/0xDanielLopez/TweetFeed/issues/new?template=feedback.yml"
X_LIST_URL = "https://x.com/i/lists/1423693426437001224"
PHISHUNT_URL = "https://phishunt.io/"
X_PROFILE_URL = "https://x.com/0xDanielLopez"
GITHUB_URL = "https://github.com/0xDanielLopez/TweetFeed"

# The 4-point spark, reused from .tf-agent-pill-spark on the homepage and from
# phishunt's own Agents nav item. Kept inline so it needs no icon font.
SPARK_SVG = (
    '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" '
    'aria-hidden="true" style="vertical-align:-2px"><path d="M12 2L15 9L22 12L15 15L12 22L9 15L2 12L9 9Z"/></svg>'
)

X_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1227" width="1em" height="1em" '
    'fill="currentColor" aria-hidden="true" style="vertical-align:-2px"><path d="M714.163 519.284 '
    '1160.89 0h-105.86L667.137 450.887 357.328 0H0l468.492 681.821L0 1226.37h105.866l409.625-476.152'
    ' 327.181 476.152H1200L714.137 519.284h.026ZM569.165 687.828l-47.468-67.894-377.686-540.24h162.604'
    'l304.797 435.991 47.468 67.894 396.2 566.721H892.476L569.165 687.854v-.026Z"/></svg>'
)


class Link(NamedTuple):
    label: str
    href: str          # site-relative ("campaigns/") or absolute (external)
    icon: str = ""     # FA5 class name, or "svg:spark" / "svg:x"
    external: bool = False

    @property
    def key(self) -> str:
        """Stable identity used for active-state matching and gate comparison."""
        return self.href


# Home is special: its href is pure depth prefix, so it normalizes to "".
# No icon by design (operator's call, 2026-08-18): the wordmark carries the
# brand on its own. SPARK_SVG is still used by the Agents nav item.
HOME = Link("TweetFeed", "", icon="")

# --- Navbar ----------------------------------------------------------------
# Visible on the desktop bar, in order. Agents leads (operator's call), then
# Campaigns: the site's differentiator, which measured ~0 internal navigation
# while it lived in the footer only (CF RUM 30d, 2026-08-18).
NAV_PRIMARY = [
    Link("Agents", "agents/", "svg:spark"),
    Link("Campaigns", "campaigns/", "fa-project-diagram"),
    Link("Dashboard", "dashboard/", "fa-th"),
    Link("Hunt", "hunt/", "fa-bullseye"),
    Link("Feeds", "feeds/", "fa-rss"),
    Link("API", "api/", "fa-code"),
]

# The "More" menu. None marks a group separator (rendered as <hr>, never as a
# <div class="dropdown-divider"> -- see check_consistency.extract_mobile_dropdown).
NAV_MORE = [
    Link("Graphs", "graphs/", "fa-chart-pie"),
    Link("Trends", "trends/", "fa-chart-line"),
    Link("Researchers", "researchers/", "fa-users"),
    None,
    Link("Tags", "tags/", "fa-hashtag"),
    Link("IOC types", "ioc-types/", "fa-list"),
    None,
    Link("Bad domains list", "malicious-domains/", "fa-globe"),
    Link("Bad IPs list", "malicious-ips/", "fa-map-marker-alt"),
    None,
    Link("About", "about/", "fa-question-circle"),
    Link("Changelog", "changelog/", "fa-history"),
    None,
    Link("X List", X_LIST_URL, "svg:x", external=True),
    Link("phishunt.io", PHISHUNT_URL, "fa-fish", external=True),
]

SEARCH = Link("Search", "search/", "fa-search")
DOCS = Link("Docs", "docs/", "fa-book")
FEEDBACK = Link("Feedback", FEEDBACK_URL, "fa-comment-dots", external=True)

NAV_RIGHT = [SEARCH, DOCS, FEEDBACK]


def nav_more_links():
    return [l for l in NAV_MORE if l is not None]


def nav_mobile():
    """Mobile hamburger order: primaries + Search, the More tail, then utility.

    None entries are group separators, rendered as <hr class="dropdown-divider">
    exactly like the desktop More menu."""
    return NAV_PRIMARY + [SEARCH] + [None] + nav_more_links() + [None] + [DOCS, FEEDBACK]


def nav_mobile_links():
    return [l for l in nav_mobile() if l is not None]


# --- Footer ----------------------------------------------------------------
FOOTER_COLUMNS = [
    ("DATA", [
        Link("IOC feeds", "feeds/"),
        Link("Bad domains list", "malicious-domains/"),
        Link("Bad IPs list", "malicious-ips/"),
        Link("Malicious URLs", "malicious-urls/"),
        Link("MD5 hashes", "malicious-hashes-md5/"),
        Link("SHA-256 hashes", "malicious-hashes-sha256/"),
        Link("Tags", "tags/"),
        Link("IOC types", "ioc-types/"),
    ]),
    ("EXPLORE", [
        Link("Dashboard", "dashboard/"),
        Link("Hunt", "hunt/"),
        Link("Search", "search/"),
        Link("Campaigns", "campaigns/"),
        Link("Trends", "trends/"),
        Link("Graphs", "graphs/"),
        Link("Researchers", "researchers/"),
    ]),
    ("DEVELOPERS", [
        Link("API", "api/"),
        Link("Agents (MCP)", "agents/"),
        Link("Docs", "docs/"),
        Link("Changelog", "changelog/"),
    ]),
    ("PROJECT", [
        Link("About", "about/"),
        Link("Guide", "threat-intelligence-guide/"),
        Link("Terms of Service", "tos/"),
        Link("Feedback", FEEDBACK_URL, external=True),
    ]),
]

FOOTER_SOCIAL = [
    Link("X @0xDanielLopez", X_PROFILE_URL, "svg:x", external=True),
    Link("GitHub", GITHUB_URL, "fa-github", external=True),
]

FOOTER_TAGLINE = "IOCs shared by the infosec community on Twitter/X."
FOOTER_BYLINE = "By Daniel López"
FOOTER_MADE_IN = "Made with ❤ in Andalucía, Spain"
FOOTER_COPYRIGHT = "© 2026 TweetFeed.live"


# The mobile footer is deliberately NOT a copy of the desktop one. Measured
# 2026-08-18: repeating all 23 desktop links made it 849px tall, a full phone
# screen, while 18 of those 23 were already one tap away in the hamburger. So
# mobile carries only what the menu does not: the three list pages, the guide,
# and the legal row. The desktop <footer> block stays in the markup at every
# viewport, so internal linking for crawlers is unaffected.
FOOTER_MOBILE_COLUMNS = [
    ("REFERENCE", [
        Link("Malicious URLs", "malicious-urls/"),
        Link("MD5 hashes", "malicious-hashes-md5/"),
        Link("SHA-256 hashes", "malicious-hashes-sha256/"),
        Link("Guide", "threat-intelligence-guide/"),
    ]),
]

FOOTER_MOBILE_LEGAL = [
    Link("Terms of Service", "tos/"),
    Link("Feedback", FEEDBACK_URL, external=True),
]


def footer_links():
    return [l for _, links in FOOTER_COLUMNS for l in links]


def footer_links_mobile():
    return [l for _, links in FOOTER_MOBILE_COLUMNS for l in links] + FOOTER_MOBILE_LEGAL


def internal_footer_targets():
    return {l.href for l in footer_links() if not l.external}


# --- Docs sidebar ----------------------------------------------------------
# The left-hand nav on the 43 pages that use `.docs-wrap`. It used to be
# copy-pasted, and had drifted into SEVEN divergent variants with no partial
# and no check to catch it: on all five malicious-* pages `class="active"` sat
# on ../ioc-types/ instead of the page's own link, because the whole block had
# been copied from ioc-types/. Declaring it here makes the active state a
# function of the page path instead of something a human has to remember.
#
# `child=True` renders the item indented one level under the entry above it.
# That used to be an inline style="padding-left:26px", which the mobile chip
# row could not neutralise, so the chips came out lopsided.
DOCS_SIDEBAR = [
    ("Overview", [
        Link("Docs home", "docs/"),
    ]),
    ("Concepts", [
        Link("Threat Intelligence guide", "threat-intelligence-guide/"),
    ]),
    ("Browse the data", [
        Link("Tag index", "tags/"),
        Link("IOC types", "ioc-types/"),
        Link("Malicious URLs", "malicious-urls/"),
        Link("Malicious domains", "malicious-domains/"),
        Link("Malicious IPs", "malicious-ips/"),
        Link("MD5 hashes", "malicious-hashes-md5/"),
        Link("SHA-256 hashes", "malicious-hashes-sha256/"),
        Link("AI Campaigns", "campaigns/"),
    ]),
    ("Other", [
        Link("Changelog", "changelog/"),
    ]),
]

# Items rendered as indented children of the entry above them.
DOCS_SIDEBAR_CHILDREN = {
    "malicious-urls/",
    "malicious-domains/",
    "malicious-ips/",
    "malicious-hashes-md5/",
    "malicious-hashes-sha256/",
}


def docs_sidebar_links():
    return [l for _, links in DOCS_SIDEBAR for l in links]


def docs_sidebar_active_for(page: str):
    """Which sidebar entry a page should highlight, or None if the page has no
    sidebar. A tag page highlights the tag index; a campaign permalink
    highlights AI Campaigns."""
    if page.startswith("tag/"):
        return "tags/"
    if page.startswith("campaigns/tfc-"):
        return "campaigns/"
    own = page[: -len("index.html")] if page.endswith("index.html") else page
    hrefs = {l.href for l in docs_sidebar_links()}
    return own if own in hrefs else None


# --- Active state ----------------------------------------------------------
# Exactly one item lights up per page. A page that lives inside the More menu
# lights up the *trigger* (so the bar always shows one pill) and additionally
# marks the item inside the menu with aria-current.
ACTIVE_BY_PAGE = {
    "index.html": "",
    "campaigns/index.html": "campaigns/",
    "dashboard/index.html": "dashboard/",
    "hunt/index.html": "hunt/",
    "feeds/index.html": "feeds/",
    "api/index.html": "api/",
    "agents/index.html": "agents/",
    "search/index.html": "search/",
    "docs/index.html": "docs/",
    # Sub-pages of the Docs section keep marking Docs, as they did before.
    "threat-intelligence-guide/index.html": "docs/",
    "graphs/index.html": "graphs/",
    "trends/index.html": "trends/",
    "researchers/index.html": "researchers/",
    "tags/index.html": "tags/",
    "ioc-types/index.html": "ioc-types/",
    "malicious-domains/index.html": "malicious-domains/",
    "malicious-ips/index.html": "malicious-ips/",
    "about/index.html": "about/",
    "changelog/index.html": "changelog/",
}

# Pages with no nav home of their own: the three list pages that live in the
# footer only, plus legal and the error page.
NO_ACTIVE = {
    "malicious-urls/index.html",
    "malicious-hashes-md5/index.html",
    "malicious-hashes-sha256/index.html",
    "tos/index.html",
    "404.html",
}


def active_key_for(page: str):
    """Return the nav key to mark active for a page path, or None."""
    if page in NO_ACTIVE:
        return None
    if page in ACTIVE_BY_PAGE:
        return ACTIVE_BY_PAGE[page]
    if page.startswith("tag/"):
        return "tags/"                 # a tag page is a child of the tag index
    if page.startswith("campaigns/tfc-"):
        return "campaigns/"            # campaign permalink -> Campaigns
    return None


MORE_KEYS = {l.href for l in nav_more_links()}
PRIMARY_KEYS = {l.href for l in NAV_PRIMARY}
