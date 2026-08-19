#!/usr/bin/env python3
"""Regression test: a tag page's sample table must only show IOCs that really
carry that tag.

The API's path filter is a substring match while the count cards come from
counts.json (exact match), so /tag/scam/ used to print "111" and then list rows
from a 510-row superset in which 399 were #cryptoscam. "apt" was the worst
case: it matched #AdaptixC2 and #FakeCaptcha.

No network access required. Run:
    python3 scripts/test_tag_samples.py
"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import regen_tag_pages as rtp  # noqa: E402

# Real contamination observed on the month window, 2026-08-20.
CASES = [
    ("scam",    ["#cryptoscam"],                  ["#scam"]),
    ("apt",     ["#AdaptixC2"],                   ["#APT"]),
    ("apt",     ["#FakeCaptcha"],                 ["#apt"]),
    ("c2",      ["#AdaptixC2"],                   ["#C2"]),
    ("remcos",  ["#RemcosRAT"],                   ["#Remcos"]),
    ("stealer", ["#SalatStealer", "#infostealer"], ["#stealer"]),
]


def check_carries_tag():
    failures = []
    for slug, contaminating, genuine in CASES:
        for tags in ([t] for t in contaminating):
            if rtp.carries_tag({"tags": tags}, slug):
                failures.append(f"{slug!r}: accepted a row tagged {tags} (substring match)")
        for tags in ([t] for t in genuine):
            if not rtp.carries_tag({"tags": tags}, slug):
                failures.append(f"{slug!r}: rejected a row tagged {tags} (should match, case-insensitively)")
    # a row carrying both must still be kept - it genuinely has the tag
    if not rtp.carries_tag({"tags": ["#cryptoscam", "#scam"]}, "scam"):
        failures.append("scam: rejected a row carrying BOTH #cryptoscam and #scam")
    # defensive shapes
    for row in ({}, {"tags": None}, {"tags": []}, {"tags": [None]}):
        if rtp.carries_tag(row, "scam"):
            failures.append(f"scam: accepted malformed row {row!r}")
    return failures


def check_fetch_samples_filters(monkey_rows, slug):
    """fetch_samples must drop substring-only rows before slicing, or the
    SAMPLE_LIMIT window fills up with rows that do not carry the tag."""
    class _Resp:
        status_code = 200
        @staticmethod
        def json(): return monkey_rows
    original = rtp.requests.get
    rtp.requests.get = lambda *a, **k: _Resp()
    try:
        return rtp.fetch_samples(slug)
    finally:
        rtp.requests.get = original


def main():
    failures = check_carries_tag()

    rows = ([{"date": f"2026-08-19 10:00:{i:02d}", "tags": ["#cryptoscam"], "value": f"c{i}"} for i in range(30)]
            + [{"date": "2026-08-19 09:00:00", "tags": ["#scam"], "value": "real"}])
    out = check_fetch_samples_filters(rows, "scam")
    if any("#cryptoscam" in (r.get("tags") or []) and "#scam" not in (r.get("tags") or []) for r in out):
        failures.append("fetch_samples() still returns substring-only rows")
    if not any(r["value"] == "real" for r in out):
        failures.append("fetch_samples() dropped the genuinely tagged row")

    if failures:
        print("[FAIL] Tag sample exact-match test:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[PASS] Tag sample exact-match test: samples carry the tag their page claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
