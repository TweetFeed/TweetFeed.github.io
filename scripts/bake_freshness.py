#!/usr/bin/env python3
"""Bake a real IOC count and generation timestamp into the /malicious-*/
pages, and the last build's generated_at into /trends/.

Why this exists
----------------
The 5 /malicious-<type>/ pages carried a daily <lastmod> in sitemap.xml
while nothing about their content ever changed: no baked count, no
generation timestamp, same static HTML since the last hand edit. Now that
bump_sitemap_lastmod.py derives <lastmod> from real content changes (see
its docstring), a page that never changes correctly stops being dated
"today". This script is what makes "today" true for these pages: it writes
a real, current IOC count and a real generation timestamp into each, plus
"dateModified" on the page's existing Dataset JSON-LD object.

/trends/ already renders a live "Last updated" line client-side, after
fetching /v1/trends in the browser - invisible to any crawler that does not
run JS. This script additionally bakes that same generated_at into the
served HTML: the initial content of #trendsGeneratedLine, and a small
WebPage JSON-LD block (trends has no WebPage/Dataset object to extend) with
"dateModified". The client-side fetch still overwrites both on load; this
only fixes what a non-JS crawler sees on first paint.

Data source
-----------
https://api.tweetfeed.live/v1/trends: one ~4KB request returns generated_at
plus a 31-day daily series broken out by IOC type (url/domain/ip/sha256/
md5). Summed per type, that is the count already labelled "last 30 days" by
the neighbouring "Month" card and its tooltip on each malicious-* page (the
series covers 31 calendar days including a partial "today", the same
off-by-one the existing tooltip copy already lives with).

Verified 2026-08-22: /v1/trends' 31-day domain sum (4,987) matched the
X-Result-Count response header of a live GET to /v1/month/domain (also
4,987) exactly, so the two sources agree. /v1/trends is one ~4KB request;
the typed endpoint alone downloaded 1.3MB for that single type and would
need 5 separate requests (one per IOC type) to cover this script's job. So
/v1/trends is the cheaper choice, confirmed truthful against the header.

Idempotency
-----------
The visible count line (and, on /trends/, the WebPage JSON-LD block and the
baked line) are written between <!-- freshness:<name>:start --> /
<!-- freshness:<name>:end --> marker comments, seeded once by hand. Re-running
this script replaces only the region between a marker pair, so a human
editing the page around it is never clobbered, and running it twice with
unchanged source data produces an unchanged file. Markers live OUTSIDE any
<script type="application/ld+json"> tag - a comment inside one breaks the
JSON.

dateModified on the malicious-* pages' Dataset object has no bracket to sit
in (the Dataset JSON-LD predates this script and is otherwise hand-authored
data), so it is upserted by key instead: replace the value if
"dateModified" is already present, otherwise insert the key right after
"@context" in that specific script block. Both paths leave the rest of the
block, and the rest of the file, untouched.

Run by regen-landing-pages.yml after regen_tag_pages.py and before
bump_sitemap_lastmod.py, so the sitemap step sees the final, freshly-baked
content when it decides which pages are "dirty" today.
"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
TRENDS_URL = "https://api.tweetfeed.live/v1/trends"
HTTP_TIMEOUT = 30

# dirname -> (label used in the existing "malicious <label>" card text,
# noun used in the new freshness line)
MALICIOUS_PAGES = {
    "domain": ("malicious-domains", "malicious domains"),
    "ip": ("malicious-ips", "malicious IPs"),
    "url": ("malicious-urls", "malicious URLs"),
    "md5": ("malicious-hashes-md5", "MD5 hashes"),
    "sha256": ("malicious-hashes-sha256", "SHA-256 hashes"),
}

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_date_long(dt: datetime) -> str:
    """Mirror js/utils.js formatDateLong() so the baked text on /trends/
    matches, digit for digit, what the client-side fetch renders once JS
    takes over - no visible flash between the baked and live values."""
    return (
        f"{MONTHS[dt.month - 1]} {dt.day}{_ordinal(dt.day)}, {dt.year} "
        f"{dt:%H:%M:%S} UTC"
    )


def fetch_trends() -> dict:
    resp = requests.get(TRENDS_URL, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def parse_generated_at(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def set_between_markers(text: str, name: str, new_inner: str) -> str:
    """Replace everything between a <!-- freshness:<name>:start/end -->
    marker pair with new_inner. The markers must already exist in the file
    (seeded once by hand); this never inserts a marker pair itself, so a
    missing pair fails loudly instead of silently landing content in the
    wrong place."""
    start = f"<!-- freshness:{name}:start -->"
    end = f"<!-- freshness:{name}:end -->"
    # Capture the start marker's own indentation and reuse it for both marker
    # lines, so a re-run can't ratchet the end marker (or anything after it)
    # left against the margin - seen once already, see git diff before this
    # comment was written.
    pattern = re.compile(r"([ \t]*)" + re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    m = pattern.search(text)
    if not m:
        raise ValueError(f"marker pair {name!r} not found in file; seed it by hand first")
    indent = m.group(1)
    block = f"{indent}{start}\n{new_inner}\n{indent}{end}"
    return text[: m.start()] + block + text[m.end() :]


def upsert_jsonld_field(html_text: str, block_marker: str, key: str, value: str) -> str:
    """Set html_text's `key` field to `value` inside the single JSON-LD
    <script> block whose body contains block_marker (e.g. '"@type":
    "Dataset"'). Replaces the value if the key is already present,
    otherwise inserts it right after "@context" in that block only."""
    block_re = re.compile(r'(<script type="application/ld\+json">\n)(.*?)(\n\t</script>)', re.DOTALL)

    def _repl(m):
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        if block_marker not in body:
            return m.group(0)
        key_re = re.compile(r'"' + re.escape(key) + r'"\s*:\s*"[^"]*"')
        if key_re.search(body):
            body = key_re.sub(f'"{key}": "{value}"', body, count=1)
        else:
            body = body.replace(
                '"@context": "https://schema.org",',
                f'"@context": "https://schema.org",\n\t\t"{key}": "{value}",',
                1,
            )
        return open_tag + body + close_tag

    new_text, n = block_re.subn(_repl, html_text)
    if n == 0:
        raise ValueError(f"no JSON-LD block matched {block_marker!r}")
    return new_text


def bake_malicious_page(dirname: str, noun: str, count: int, generated_dt: datetime) -> str:
    path = REPO_ROOT / dirname / "index.html"
    text = path.read_text(encoding="utf-8")
    iso_ts = generated_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str = generated_dt.strftime("%Y-%m-%d %H:%M UTC")

    # Worth keeping even though the stats row right above appears to say the
    # same thing to a human: that row is a literal `-` placeholder in the
    # served HTML (class mu-today/mu-week/... filled by JS on load), so a
    # crawler sees NO number on this page at all. This line is the only
    # machine-visible count, which is the whole point of baking it.
    #
    # No negative margin. The first version used margin-top:-0.5rem and the
    # line rendered 8px INSIDE the preceding .row (measured on stage: line
    # top 906 against the row's bottom 914), which is the same
    # "a card sitting on another" spacing fault this repo already fixed once.
    # font-family is not set either: body is already Rubik, so it was a
    # redundant third copy of a value defined in the stylesheet.
    line = (
        '\t\t\t\t<p style="color:#737373; font-size:13px; margin-top:0.75rem; margin-bottom:1.5rem;">'
        f"Currently tracking {count:,} {noun} reported in the last 30 days. "
        f"Data generated {date_str}.</p>"
    )
    text = set_between_markers(text, "count", line)
    text = upsert_jsonld_field(text, '"@type": "Dataset"', "dateModified", iso_ts)

    path.write_text(text, encoding="utf-8")
    return iso_ts


def bake_trends_page(generated_dt: datetime) -> str:
    path = REPO_ROOT / "trends" / "index.html"
    text = path.read_text(encoding="utf-8")
    iso_ts = generated_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    long_date = format_date_long(generated_dt)

    jsonld = (
        '\t<script type="application/ld+json">\n'
        "\t{\n"
        '\t\t"@context": "https://schema.org",\n'
        '\t\t"@type": "WebPage",\n'
        '\t\t"name": "IOC Trends",\n'
        '\t\t"url": "https://tweetfeed.live/trends/",\n'
        '\t\t"isPartOf": {"@id": "https://tweetfeed.live/#organization"},\n'
        f'\t\t"dateModified": "{iso_ts}",\n'
        '\t\t"inLanguage": "en"\n'
        "\t}\n"
        "\t</script>"
    )
    text = set_between_markers(text, "jsonld", jsonld)

    line = f'\t\t\t\t\t\t\t\t\t<p class="trd-generated-line" id="trendsGeneratedLine">Last updated: {long_date}</p>'
    text = set_between_markers(text, "count", line)

    path.write_text(text, encoding="utf-8")
    return iso_ts


def main() -> int:
    data = fetch_trends()
    generated_dt = parse_generated_at(data["generated_at"])
    types = data.get("daily", {}).get("types", {})

    for ioc_type, (dirname, noun) in MALICIOUS_PAGES.items():
        series = types.get(ioc_type, [])
        count = sum(series)
        iso_ts = bake_malicious_page(dirname, noun, count, generated_dt)
        print(f"  [ok]   {dirname}/: {count:,} {noun} in last 30 days, dateModified={iso_ts}")

    trends_iso = bake_trends_page(generated_dt)
    print(f"  [ok]   trends/: dateModified={trends_iso}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
