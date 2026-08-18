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


# Desktop lays the columns out left to right; the mobile footer is a 2-column
# grid whose DOM order therefore reads down column 1 (DATA, DEVELOPERS) and
# then column 2 (EXPLORE, PROJECT). Both orders are declared so the gate can
# check each surface against what it should actually contain.
FOOTER_MOBILE_COLUMN_ORDER = (0, 2, 1, 3)


def footer_links():
    return [l for _, links in FOOTER_COLUMNS for l in links]


def footer_links_mobile():
    return [l for i in FOOTER_MOBILE_COLUMN_ORDER for l in FOOTER_COLUMNS[i][1]]


def internal_footer_targets():
    return {l.href for l in footer_links() if not l.external}


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
