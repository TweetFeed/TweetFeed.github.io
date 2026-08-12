#!/usr/bin/env python3
"""Rewrite render-blocking FontAwesome/Google Fonts <link> tags to preload+swap.

Why: PSI investigation (2026-08-12) confirmed the render-blocking <head>
stylesheet chain as the direct cause of the FCP/LCP delay on stage (home
0.71, dashboard 0.77 mobile perf). Of the 10 render-blocking stylesheets,
FontAwesome (cdnjs) + the 2 Google Fonts CSS requests alone account for
~2705ms of Lighthouse's estimated savings - the single largest addressable
slice, and external hosts (unlike the local vendor CSS) get zero benefit
from being blocking since they can't affect in-repo layout timing.

Fix: swap each matching <link rel="stylesheet" ...> for the standard
preload+swap pattern (fetch at high priority without blocking first paint,
promote to an active stylesheet on load, <noscript> fallback for JS-off
clients). Every repo-visible attribute already on the tag (href, integrity,
crossorigin, referrerpolicy) is preserved verbatim on the preload link.

Every page in this repo hand-copies the same <head> boilerplate (no
templating - see scripts/check_consistency.py's docstring), so this script
finds-and-replaces the exact matching tags across every .html file instead
of hand-editing 56 files.

Idempotent: matches only the still-blocking <link rel="stylesheet"> form,
so re-running after conversion is a no-op (0 files changed).

Usage:
    python3 scripts/preload_swap_fonts.py          # apply
    python3 scripts/preload_swap_fonts.py --check  # dry-run, exit 1 if any file would change
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exact tags as they appear today (confirmed identical across all 56 files
# via grep - see investigation). Matched literally, not attribute-order-
# tolerant, on purpose: if a page ever drifts from this exact tag,
# check_consistency.py-style silent drift is worse than this script
# skipping it and leaving it visibly unconverted for a human to look at.
FONT_AWESOME_OLD = (
    '<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" '
    'rel="stylesheet" '
    'integrity="sha512-1ycn6IcaQQ40/MKBW2W4Rhis/DbILU74C1vSrLJxCq57o941Ym01SwNsOMqvEBFlcgUa6xLiPY/NS5R+E6ztJQ==" '
    'crossorigin="anonymous" referrerpolicy="no-referrer">'
)
FONT_AWESOME_NEW = (
    '<link rel="preload" '
    'href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" '
    'as="style" '
    'integrity="sha512-1ycn6IcaQQ40/MKBW2W4Rhis/DbILU74C1vSrLJxCq57o941Ym01SwNsOMqvEBFlcgUa6xLiPY/NS5R+E6ztJQ==" '
    'crossorigin="anonymous" referrerpolicy="no-referrer" '
    'onload="this.onload=null;this.rel=\'stylesheet\'">\n'
    '\t<noscript><link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" '
    'rel="stylesheet" '
    'integrity="sha512-1ycn6IcaQQ40/MKBW2W4Rhis/DbILU74C1vSrLJxCq57o941Ym01SwNsOMqvEBFlcgUa6xLiPY/NS5R+E6ztJQ==" '
    'crossorigin="anonymous" referrerpolicy="no-referrer"></noscript>'
)

ALEGREYA_OLD = '<link href="https://fonts.googleapis.com/css2?family=Alegreya+Sans+SC&display=swap" rel="stylesheet">'
ALEGREYA_NEW = (
    '<link rel="preload" href="https://fonts.googleapis.com/css2?family=Alegreya+Sans+SC&display=swap" '
    'as="style" onload="this.onload=null;this.rel=\'stylesheet\'">\n'
    '\t<noscript><link href="https://fonts.googleapis.com/css2?family=Alegreya+Sans+SC&display=swap" '
    'rel="stylesheet"></noscript>'
)

RUBIK_OLD = '<link href="https://fonts.googleapis.com/css2?family=Rubik&display=swap" rel="stylesheet">'
RUBIK_NEW = (
    '<link rel="preload" href="https://fonts.googleapis.com/css2?family=Rubik&display=swap" '
    'as="style" onload="this.onload=null;this.rel=\'stylesheet\'">\n'
    '\t<noscript><link href="https://fonts.googleapis.com/css2?family=Rubik&display=swap" '
    'rel="stylesheet"></noscript>'
)

REPLACEMENTS = [
    (FONT_AWESOME_OLD, FONT_AWESOME_NEW),
    (ALEGREYA_OLD, ALEGREYA_NEW),
    (RUBIK_OLD, RUBIK_NEW),
]

# node_modules is a local dev dependency (browser-sync etc.), not a site page.
SKIP_DIR_PARTS = {"node_modules", ".git"}


def find_html_files() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.html")
        if not SKIP_DIR_PARTS & set(p.relative_to(REPO_ROOT).parts)
    )


def convert(text: str) -> tuple[str, int]:
    """Apply each (old, new) replacement once, skipping ones already applied.

    Idempotency note: NEW's <noscript> fallback deliberately contains OLD
    verbatim (same tag, still blocking, but only for the no-JS case) - so a
    plain `old in text` check would keep matching inside an already-converted
    page's <noscript> block forever. Checking `new in text` first is what
    makes re-running this script on an already-converted file a true no-op.
    """
    changed = 0
    for old, new in REPLACEMENTS:
        if new in text:
            continue
        if old in text:
            text = text.replace(old, new)
            changed += 1
    return text, changed


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    files = find_html_files()
    touched: list[str] = []
    would_touch: list[str] = []

    for path in files:
        original = path.read_text(encoding="utf-8")
        updated, n = convert(original)
        if n == 0:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        if check_only:
            would_touch.append(rel)
            continue
        path.write_text(updated, encoding="utf-8")
        touched.append(rel)

    if check_only:
        if would_touch:
            print(f"Would convert {len(would_touch)} file(s):")
            for f in would_touch:
                print(f"  {f}")
            return 1
        print("No render-blocking FontAwesome/Google Fonts tags found (already converted).")
        return 0

    print(f"Converted {len(touched)} file(s).")
    for f in touched:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
