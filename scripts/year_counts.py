#!/usr/bin/env python3
"""Single source of truth for the "Nk+ ... past year" claims on the five
/malicious-<type>/ pages: where the real number comes from, which pages
carry a claim, and how a claim is parsed out of the HTML.

Why this module exists
----------------------
On 2026-08-22 the four year-window counts were corrected by hand and a gate
(check_consistency.check_year_counts) was added so an overstated count could
never reach a SERP snippet again. The next morning the daily workflow died:

    [FAIL] Year-window counts in descriptions are not overstated
      - malicious-ips/index.html: claims 9.6k+ ip in the past year,
        real count is 9,569

Nothing was wrong with the page. `9.6k+` had been typed from a real 9,625 the
day before, and the 365-day window is ROLLING - it shrinks whenever a day
with many rows falls off the back. A hand-typed number measured against a
moving target is a scheduled failure, and because the gate runs inside
regen-landing-pages.yml it took the whole daily commit down with it: tag
pages, freshness bake and sitemap lastmod all stopped being pushed.

So the number stopped being hand-typed (see bake_year_counts.py) and the
definitions moved here, imported by BOTH the baker and the gate. That is the
point: a generator and a checker that read the same feed through different
code eventually disagree, and the disagreement surfaces as a red build with
no bug behind it.

Deliberately NOT here: the tolerance policy. The gate only refuses
overstatement (understating is merely stale); the baker keeps a wider safety
band so it does not have to rewrite the copy every day. Those are different
questions and they live with their own callers.
"""
from __future__ import annotations

import re
import urllib.request
from collections import Counter

# The rolling 365-day feed, straight from the public data repo. This is the
# same file the site's own "past year" figures describe, so it is the
# authority - not an API window that merely resembles it.
YEAR_CSV = "https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/year.csv"

# page -> the IOC type whose row count its claim describes.
YEAR_CLAIM_PAGES = {
    "malicious-domains/index.html": "domain",
    "malicious-urls/index.html": "url",
    "malicious-ips/index.html": "ip",
    "malicious-hashes-md5/index.html": "md5",
    "malicious-hashes-sha256/index.html": "sha256",
}

# Matches `38k+ unique domains in the past year`, `9.6k+ past year`, and the
# other phrasings in use. Group 1 is the number as written, which is what
# both callers need: the gate compares it, the baker substitutes it. The
# [^"<] class keeps a match inside one attribute value or text node.
YEAR_CLAIM_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)k\+[^\"<]{0,24}past year")


def fetch_year_counts() -> Counter | None:
    """Rows per IOC type in the rolling year feed, or None if unreachable.

    None (not an exception, not an empty Counter) so both callers can treat
    "no network" as "skip", which keeps an offline local run useful.
    """
    try:
        req = urllib.request.Request(YEAR_CSV, headers={"User-Agent": "tweetfeed-year-counts"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    counts: Counter = Counter()
    for line in body.splitlines():
        parts = line.split(",")
        if len(parts) > 2:
            counts[parts[2].strip()] += 1
    return counts or None
