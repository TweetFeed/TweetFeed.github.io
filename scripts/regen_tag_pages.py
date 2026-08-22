#!/usr/bin/env python3
"""Regenerate tag landing pages under tag/<slug>/index.html.

Reads tag_metadata.yaml + counts.json (data repo) + samples from api.tweetfeed.live,
renders templates/tag_page.html.j2 with baked counts and 10 most recent IOCs.

Designed to run daily via .github/workflows/regen-landing-pages.yml. Skips a tag
silently on transient API errors so a single bad tag does not fail the workflow.
"""
import datetime
import html
import json
import sys
from pathlib import Path
from urllib.parse import quote

import requests
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

SCRIPT_DIR = Path(__file__).resolve().parent
from render_shell import shell_context

REPO_ROOT = SCRIPT_DIR.parent
TAG_DIR = REPO_ROOT / "tag"
# Stage repo has no CNAME file; prod (tweetfeed.live) does. Stage output gets
# a per-page noindex meta (robots.txt allows crawling there so the meta must
# do the blocking; see check_consistency.check_noindex_polarity).
IS_STAGE = not (REPO_ROOT / "CNAME").is_file()
COUNTS_URL = "https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/counts.json"
API_BASE = "https://api.tweetfeed.live/v1"
SAMPLE_LIMIT = 10
HTTP_TIMEOUT = 30

TYPE_COLORS = {
    "url": ("#0026E6", "white"),
    "domain": ("#3399FF", "white"),
    "ip": ("#02bf0f", "white"),
    "sha256": ("#FFC34D", "#1c1c1c"),
    "md5": ("#FFC34D", "#1c1c1c"),
}


def fetch_counts():
    return requests.get(COUNTS_URL, timeout=HTTP_TIMEOUT).json()


def carries_tag(row, slug):
    """True only if the row really carries this exact tag.

    The API's path filter is a SUBSTRING match, while the count cards on the
    same page come from counts.json, which is an exact tag match. That made the
    table contradict the number printed directly above it and, worse, publish
    IOCs under a tag they do not carry. Measured 2026-08-20 on the month
    window: /v1/month/scam returned 510 rows of which 111 carried #scam (399
    were #cryptoscam); apt was contaminated by #AdaptixC2 and #FakeCaptcha
    ("apt" sits inside both), c2 by #AdaptixC2, remcos by #RemcosRAT, and
    stealer by #SalatStealer and #infostealer.

    Tags arrive from the API with a "#" prefix and are compared case-insensitively,
    because tags.yaml uses PascalCase for malware families (#CobaltStrike) and
    lowercase for generic ones while the slug in the URL is always lowercase.
    """
    want = f"#{slug}".lower()
    return any((t or "").lower() == want for t in (row.get("tags") or []))


def fetch_samples(slug):
    url = f"{API_BASE}/month/{slug}"
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        return []
    data = resp.json()
    if not isinstance(data, list):
        return []
    data = [r for r in data if carries_tag(r, slug)]
    data.sort(key=lambda r: r.get("date", ""), reverse=True)
    return data[:SAMPLE_LIMIT]


def js_encode_uri_component(s):
    """Mirror JS encodeURIComponent() exactly: percent-encode everything
    except A-Z a-z 0-9 - _ . ! ~ * ' ( ). Used to build the 365-day IOC
    lookup link (search/?q=<value>) so the query string matches what the
    client-side encodeURIComponent(value) calls produce elsewhere on the
    site (index.html, search.html, malicious-*.html, campaigns.html)."""
    return quote(s, safe="!*'()~")


def format_sample(r):
    try:
        ts = datetime.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
        date_short = ts.strftime("%b %d, %H:%M")
    except (ValueError, KeyError):
        date_short = r.get("date", "")
    color, text_color = TYPE_COLORS.get(r.get("type", ""), ("#737373", "white"))
    val = r.get("value", "")
    val_display = val[:60] + "..." if len(val) > 60 else val
    # Everything below is feed-derived (IOC value/type/user/date come from the
    # TweetFeed API, ultimately from tweets), not repo-owned config, and gets
    # interpolated into tag_page.html.j2 with Jinja autoescape OFF - the
    # templates render intentional raw HTML elsewhere via `| safe` (bullets,
    # JSON-LD blobs), so turning on global autoescape isn't an option. A `"`
    # in an IOC value would otherwise break the title="..."/data-copy="..."
    # attributes it lands in; `<`/`&` would break surrounding markup/text.
    # html.escape(quote=True) covers both the attribute and text-node uses
    # of these fields. value_query is already percent-encoded (%22/%3C/%3E/
    # %26 for "<>&) by js_encode_uri_component, which also leaves a literal
    # `'` unescaped by design (matches JS encodeURIComponent); escaping it
    # here too is redundant but harmless (browsers decode the HTML entity
    # back to `'` before using the href) and keeps the four fields consistent.
    return {
        "date_short": html.escape(date_short, quote=True),
        "type": html.escape(r.get("type", ""), quote=True),
        "type_color": color,
        "type_text_color": text_color,
        "value_full": html.escape(val, quote=True),
        "value_display": html.escape(val_display, quote=True),
        "value_query": html.escape(js_encode_uri_component(val), quote=True),
        "user": html.escape(r.get("user", ""), quote=True),
    }


def _dumps_tab_indented(payload):
    """JSON dump with tab indent + leading tab on continuation lines so the
    rendered block lines up with the surrounding tab-indented HTML."""
    s = json.dumps(payload, indent="\t", ensure_ascii=False)
    lines = s.split("\n")
    return "\n".join([lines[0]] + ["\t" + line for line in lines[1:]])


def build_webpage_jsonld(m, date_modified):
    payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": m["webpage_name"],
        "url": f"https://tweetfeed.live/tag/{m['slug']}/",
        "description": m["webpage_description"],
        "isPartOf": {"@id": "https://tweetfeed.live/#organization"},
        "dateModified": date_modified,
        "about": {
            "@type": m["schema_about"]["type"],
            "name": m["schema_about"]["name"],
        },
        "inLanguage": "en",
    }
    if m["schema_about"].get("alternate_names"):
        payload["about"]["alternateName"] = m["schema_about"]["alternate_names"]
    if m["schema_about"].get("application_category"):
        payload["about"]["applicationCategory"] = m["schema_about"]["application_category"]
    if m["schema_about"].get("same_as"):
        payload["about"]["sameAs"] = m["schema_about"]["same_as"]
    return _dumps_tab_indented(payload)


def build_faq_jsonld(m):
    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": m["faq_q1"]["q"], "acceptedAnswer": {"@type": "Answer", "text": m["faq_q1"]["a"]}},
            {"@type": "Question", "name": m["faq_q2"]["q"], "acceptedAnswer": {"@type": "Answer", "text": m["faq_q2"]["a"]}},
            {"@type": "Question", "name": "How is this list updated?", "acceptedAnswer": {"@type": "Answer",
                "text": f"Every 15 minutes. The TweetFeed pipeline scrapes RSS feeds from public Twitter/X security researcher accounts and lists, extracts IOCs (URLs, domains, IPs, file hashes), tags them with the relevant malware family or threat actor, and republishes the result in CSV, JSON and RSS. {m['license_subject']}-tagged IOCs are surfaced on this page within the next 15-minute tick."}},
            {"@type": "Question", "name": "What is the license? Can I use this commercially?", "acceptedAnswer": {"@type": "Answer",
                "text": f"All TweetFeed IOC data, including this {m['license_subject']} subset, is released under CC0 1.0 Universal (Public Domain Dedication). No attribution required, no warranty. Commercial use is allowed. The TweetFeed website code and branding are not covered by CC0."}},
        ],
    }
    return _dumps_tab_indented(payload)


def render_tag(m, env, counts, today_str):
    slug = m["slug"]
    tag_counts = {
        "today": counts["windows"]["today"]["tags"].get(slug, 0),
        "week": counts["windows"]["week"]["tags"].get(slug, 0),
        "month": counts["windows"]["month"]["tags"].get(slug, 0),
        "year": counts["windows"]["year"]["tags"].get(slug, 0),
    }
    samples = [format_sample(r) for r in fetch_samples(slug)]
    template = env.get_template("tag_page.html.j2")

    # interpolate {year} placeholder in meta_description
    year_str = f"{tag_counts['year']:,}"
    meta_desc = m["meta_description"].replace("{year}", year_str)
    m_render = dict(m)
    m_render["meta_description"] = meta_desc

    return template.render(
        m=m_render,
        counts=tag_counts,
        samples=samples,
        today_str=today_str,
        webpage_jsonld=build_webpage_jsonld(m, today_str),
        faq_jsonld=build_faq_jsonld(m),
        noindex=IS_STAGE,
        # The nav/footer come from scripts/templates/_nav.html.j2 and
        # _footer.html.j2 via {% include %}. Passing the shell context here is
        # what keeps the generated pages identical to the static ones; before
        # 2026-08-18 the shell was inlined in this template and the daily regen
        # silently re-stamped whatever it happened to contain.
        **shell_context(depth=2, active_key="tags/", indent="\t\t\t",
                        docs_active="tags/"),
    )


def main():
    metadata_path = SCRIPT_DIR / "tag_metadata.yaml"
    with open(metadata_path) as f:
        all_meta = yaml.safe_load(f)

    counts = fetch_counts()
    # UTC, not local time: this date is now also the JSON-LD "dateModified"
    # (build_webpage_jsonld) as well as the visible "Counts as of" line, and
    # bump_sitemap_lastmod.py's <lastmod> for these pages is UTC-derived too
    # (git commit date, or today's UTC date for what this run just changed).
    today_str = datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    env = Environment(
        loader=FileSystemLoader(SCRIPT_DIR / "templates"),
        autoescape=select_autoescape([]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters["format_num"] = lambda n: f"{int(n):,}"

    tags = all_meta.get("tags", [])
    written = 0
    skipped = 0
    for m in tags:
        slug = m["slug"]
        try:
            html = render_tag(m, env, counts, today_str)
            out_dir = TAG_DIR / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text(html, encoding="utf-8")
            written += 1
            print(f"  [ok]   tag/{slug}/")
        except Exception as e:
            skipped += 1
            print(f"  [skip] tag/{slug}: {type(e).__name__}: {e}", file=sys.stderr)

    # Also write the /tags/ hub index.
    try:
        render_tags_index(tags, env, counts, today_str)
        print("  [ok]   tags/")
    except Exception as e:
        print(f"  [skip] tags/: {type(e).__name__}: {e}", file=sys.stderr)

    print(f"\nWrote {written}/{len(tags)} tag pages ({skipped} skipped).")
    return 0 if written > 0 else 1


CATEGORY_HEADINGS = {
    "apt-group": ("APT groups", "Threat-actor clusters tracked by attribution analysts. Each page collates the IOCs the public infosec community on Twitter/X has linked to that cluster."),
    "malware-family": ("Malware families &middot; C2 frameworks &middot; tools", "Specific malware identities (Cobalt Strike, AsyncRAT, NetSupportRAT, …) plus dual-use offensive tooling that surfaces in real-world intrusions."),
    "ttp": ("Tactics, techniques and infra labels", "Broader categories: phishing, C2 infrastructure, ransomware, infostealer, scam, opendir and the umbrella malware / APT labels."),
}


def render_tags_index(tags, env, counts, today_str):
    """Render /tags/index.html grouping all tag pages by category."""
    by_cat = {}
    for m in tags:
        cat = m.get("category", "ttp")
        slug = m["slug"]
        year_count = counts["windows"]["year"]["tags"].get(slug, 0)
        month_count = counts["windows"]["month"]["tags"].get(slug, 0)
        by_cat.setdefault(cat, []).append({
            "slug": slug,
            "display_tag": m["display_tag"],
            "subtitle": m["short_subtitle_mobile"],
            "year_count": f"{year_count:,}",
            "month_count": f"{month_count:,}",
        })

    # Order: apt-group, malware-family, ttp. Within each, order by year volume desc.
    cat_order = ["apt-group", "malware-family", "ttp"]
    categories = []
    for cat_key in cat_order:
        if cat_key not in by_cat:
            continue
        heading, blurb = CATEGORY_HEADINGS[cat_key]
        rows = sorted(by_cat[cat_key], key=lambda r: -int(r["year_count"].replace(",", "")))
        categories.append({"heading": heading, "blurb": blurb, "tags": rows})

    tags_flat = sorted([m for m in tags], key=lambda m: m["slug"])

    template = env.get_template("tags_index.html.j2")
    html = template.render(
        categories=categories,
        tag_count=len(tags),
        today_str=today_str,
        tags_flat=tags_flat,
        noindex=IS_STAGE,
        **shell_context(depth=1, active_key="tags/", indent="\t\t\t",
                        docs_active="tags/"),
    )
    out_dir = REPO_ROOT / "tags"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
