#!/usr/bin/env python3
"""Regression test: feed-derived fields must be HTML-escaped before landing
in tag_page.html.j2 (rendered with Jinja autoescape OFF - see regen_tag_pages.py
docstring in format_sample()). Guards the gap flagged 2026-07-18: an IOC
value/user handle/date pulled from the TweetFeed API is feed-controlled data,
and a literal `"` in it would break the title="..."/data-copy="..." attributes
it's interpolated into; `<`/`&` would break the surrounding markup.

No network access required (fetch_samples is monkeypatched). Run:
    python3 scripts/test_html_escaping.py
"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import yaml  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

import regen_tag_pages as rtp  # noqa: E402

# A single malicious sample exercising every feed-derived field format_sample()
# touches: value (used in title=/data-copy=/href=/text), user (used in
# href=/text), type (used in text), date (used in text, via the parse-failure
# fallback path so the raw feed string flows through unmodified).
MALICIOUS_SAMPLE = {
    "date": "not-a-real-date\" onmouseover=alert(1) x=\"",
    "type": '<b>url</b>',
    "value": "https://evil.example/path?a=1&b=2\"><script>alert(1)</script>'x",
    "user": "evil\"><img src=x onerror=alert(1)>",
}

DANGEROUS_CHARS = ('"', "<", ">")


def check_format_sample():
    """format_sample() output must never contain a raw HTML metacharacter -
    every feed-derived field goes through html.escape(quote=True)."""
    failures = []
    s = rtp.format_sample(MALICIOUS_SAMPLE)
    for key in ("date_short", "type", "value_full", "value_display", "value_query", "user"):
        v = s[key]
        for ch in DANGEROUS_CHARS:
            if ch in v:
                failures.append(
                    f"format_sample()['{key}'] leaks raw '{ch}': {v!r}"
                )
    return failures


def check_full_render():
    """Render an actual tag page (real metadata entry + real templates) with
    the malicious sample injected as the sole API result, and confirm the
    dangerous payload never appears unescaped in the output HTML."""
    all_meta = yaml.safe_load((SCRIPT_DIR / "tag_metadata.yaml").read_text())
    m = all_meta["tags"][0]
    counts = {"windows": {w: {"tags": {}} for w in ("today", "week", "month", "year")}}

    env = Environment(
        loader=FileSystemLoader(SCRIPT_DIR / "templates"),
        autoescape=select_autoescape([]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters["format_num"] = lambda n: f"{int(n):,}"

    original_fetch_samples = rtp.fetch_samples
    rtp.fetch_samples = lambda slug: [MALICIOUS_SAMPLE]
    try:
        out = rtp.render_tag(m, env, counts, "2026-07-18")
    finally:
        rtp.fetch_samples = original_fetch_samples

    failures = []
    if "<script>alert(1)</script>" in out:
        failures.append("raw <script>alert(1)</script> leaked into rendered HTML")
    if "<img src=x onerror=alert(1)>" in out:
        failures.append("raw <img onerror=...> tag leaked into rendered HTML")
    if '" onmouseover=alert(1) x="' in out:
        failures.append("raw onmouseover attribute-injection leaked into rendered HTML")

    # Direct proof the raw quote from the IOC value never appears bare next
    # to the attribute boundary (which would truncate the attribute early).
    if 'title="https://evil.example/path?a=1&b=2">' in out:
        failures.append("title attribute truncated by unescaped '\"' in IOC value")
    if 'data-copy="https://evil.example/path?a=1&b=2">' in out:
        failures.append("data-copy attribute truncated by unescaped '\"' in IOC value")

    # The escaped forms must actually be present (proves escaping ran, not
    # that the field was dropped/emptied).
    if "&lt;script&gt;alert(1)&lt;/script&gt;" not in out:
        failures.append("expected escaped &lt;script&gt; form not found - did escaping run?")
    if "&quot;" not in out and "&#34;" not in out:
        failures.append("expected escaped quote entity not found in output")

    return failures


def main():
    failures = check_format_sample() + check_full_render()
    if failures:
        print("[FAIL] HTML escaping regression test:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[PASS] HTML escaping regression test: feed-derived fields escaped correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
