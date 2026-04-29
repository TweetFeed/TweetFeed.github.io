#!/usr/bin/env python3
"""Regenerate tag landing pages under tag/<slug>/index.html.

Reads tag_metadata.yaml + counts.json (data repo) + samples from api.tweetfeed.live,
renders templates/tag_page.html.j2 with baked counts and 10 most recent IOCs.

Designed to run daily via .github/workflows/regen-landing-pages.yml. Skips a tag
silently on transient API errors so a single bad tag does not fail the workflow.
"""
import datetime
import json
import sys
from pathlib import Path

import requests
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TAG_DIR = REPO_ROOT / "tag"
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


def fetch_samples(slug):
    url = f"{API_BASE}/month/{slug}"
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        return []
    data = resp.json()
    if not isinstance(data, list):
        return []
    data.sort(key=lambda r: r.get("date", ""), reverse=True)
    return data[:SAMPLE_LIMIT]


def format_sample(r):
    try:
        ts = datetime.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
        date_short = ts.strftime("%b %d, %H:%M")
    except (ValueError, KeyError):
        date_short = r.get("date", "")
    color, text_color = TYPE_COLORS.get(r.get("type", ""), ("#737373", "white"))
    val = r.get("value", "")
    val_display = val[:60] + "..." if len(val) > 60 else val
    return {
        "date_short": date_short,
        "type": r.get("type", ""),
        "type_color": color,
        "type_text_color": text_color,
        "value_full": val,
        "value_display": val_display,
        "user": r.get("user", ""),
    }


def _dumps_tab_indented(payload):
    """JSON dump with tab indent + leading tab on continuation lines so the
    rendered block lines up with the surrounding tab-indented HTML."""
    s = json.dumps(payload, indent="\t", ensure_ascii=False)
    lines = s.split("\n")
    return "\n".join([lines[0]] + ["\t" + line for line in lines[1:]])


def build_webpage_jsonld(m):
    payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": m["webpage_name"],
        "url": f"https://tweetfeed.live/tag/{m['slug']}/",
        "description": m["webpage_description"],
        "isPartOf": {"@id": "https://tweetfeed.live/#organization"},
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
        webpage_jsonld=build_webpage_jsonld(m),
        faq_jsonld=build_faq_jsonld(m),
    )


def main():
    metadata_path = SCRIPT_DIR / "tag_metadata.yaml"
    with open(metadata_path) as f:
        all_meta = yaml.safe_load(f)

    counts = fetch_counts()
    today_str = datetime.date.today().isoformat()

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

    print(f"\nWrote {written}/{len(tags)} tag pages ({skipped} skipped).")
    return 0 if written > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
