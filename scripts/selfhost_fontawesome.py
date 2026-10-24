#!/usr/bin/env python3
"""Point the Font Awesome <head> tags at the self-hosted copy under vendor/fontawesome/.

Why: every page pulled Font Awesome 5.15.4 from cdnjs (a render-blocking-ish
CSS file, then 79 KB + 78 KB + 14 KB of woff2 from a second origin), and PSI
put those fonts in the LCP path. The same library now lives under
vendor/fontawesome/, cut down to the glyphs the site draws
(scripts/subset_fontawesome.py), so the stylesheet and the fonts come from our
own origin, like Rubik / Alegreya (scripts/selfhost_fonts.py).

Per file the script rewrites the two FA tags

    <link rel="preload" href="<prefix>vendor/fontawesome/css/all.min.css?v=1" as="style" onload="this.onload=null;this.rel='stylesheet'">
    <noscript><link href="<prefix>vendor/fontawesome/css/all.min.css?v=1" rel="stylesheet"></noscript>

and drops integrity, crossorigin and referrerpolicy: the file is same origin
now, and a crossorigin mismatch between the preload and the stylesheet makes
the browser download it twice. <prefix> is copied from the page's own
css/tweetfeed.css link ('', '../', '../../', or 404.html's '/tweetfeed-stage/'),
so every depth works. It also removes <link rel="preconnect"
href="https://cdnjs.cloudflare.com" crossorigin> from every page that no
longer loads anything from cdnjs (hunt/ still loads highlight.js from there,
so it keeps the preconnect). Covers every .html file plus the Jinja
templates, so the next regen of tag/ and campaigns/ stays cdnjs-free for FA.

Bump FA_CSS_VERSION and rerun with --apply when vendor/fontawesome/css/all.min.css
changes: every page moves to the new ?v=N (check_consistency.py demands one N
everywhere). The woff2 files are fetched through the CSS, so a new subset
(scripts/subset_fontawesome.py) that only changes a woff2 keeps the old URL; bump
then too, or the browser cache keeps the old glyph set until it expires.

Idempotent: a second run changes nothing. A page that still carries a cdnjs
Font Awesome reference in a shape the script does not know stops the run.

Usage:
    python3 scripts/selfhost_fontawesome.py          # dry-run, exit 1 if any file would change
    python3 scripts/selfhost_fontawesome.py --apply  # write
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "scripts" / "templates"

FA_CSS_PATH = "vendor/fontawesome/css/all.min.css"
FA_CSS_VERSION = 1
FA_CDN_PATH = "cdnjs.cloudflare.com/ajax/libs/font-awesome/"
FA_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"

CSS_LINK_RE = re.compile(r'href="([^"]*?)css/tweetfeed\.css\?v=\d+"')
# One whole line each (leading whitespace, tag, trailing whitespace).
# The cdnjs href, or an already self-hosted one at any ?v=N: a rerun rewrites both to FA_CSS_VERSION.
FA_HREF = "(?:" + re.escape(FA_CDN_URL) + "|[^\"]*" + re.escape(FA_CSS_PATH) + r"(?:\?v=\d+)?)"
FA_PRELOAD_RE = re.compile(r'^(\s*)<link rel="preload" href="' + FA_HREF + r'" as="style"[^>]*>\s*$')
FA_NOSCRIPT_RE = re.compile(
    r'^(\s*)<noscript><link href="' + FA_HREF + r'" rel="stylesheet"[^>]*></noscript>\s*$'
)
CDNJS_PRECONNECT_RE = re.compile(
    r'^\s*<link rel="preconnect" href="https://cdnjs\.cloudflare\.com"[^>]*>\s*$'
)


def preload_tag(prefix: str) -> str:
    href = f"{prefix}{FA_CSS_PATH}?v={FA_CSS_VERSION}"
    return f'<link rel="preload" href="{href}" as="style" onload="this.onload=null;this.rel=\'stylesheet\'">'


def noscript_tag(prefix: str) -> str:
    href = f"{prefix}{FA_CSS_PATH}?v={FA_CSS_VERSION}"
    return f'<noscript><link href="{href}" rel="stylesheet"></noscript>'


def convert(text: str) -> tuple[str, bool]:
    m = CSS_LINK_RE.search(text)
    if not m:
        return text, False  # not a full page (partial or redirect stub)
    prefix = m.group(1)
    out: list[str] = []
    for line in text.split("\n"):
        pre = FA_PRELOAD_RE.match(line)
        if pre:
            out.append(pre.group(1) + preload_tag(prefix))
            continue
        ns = FA_NOSCRIPT_RE.match(line)
        if ns:
            out.append(ns.group(1) + noscript_tag(prefix))
            continue
        out.append(line)
    # The preconnect only pays off while the page still talks to cdnjs.
    if not any("cdnjs.cloudflare.com" in line and not CDNJS_PRECONNECT_RE.match(line) for line in out):
        out = [line for line in out if not CDNJS_PRECONNECT_RE.match(line)]
    new = "\n".join(out)
    return new, new != text


def targets() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files", "*.html"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [REPO_ROOT / p for p in tracked] + sorted(TEMPLATE_DIR.glob("*.j2"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the files (default: dry-run, exit 1 if any would change)")
    args = ap.parse_args()

    changed: list[Path] = []
    for path in targets():
        text = path.read_text(encoding="utf-8")
        new, did = convert(text)
        if FA_CDN_PATH in new:
            raise SystemExit(f"{path.relative_to(REPO_ROOT)}: Font Awesome cdnjs reference in an unknown shape")
        if did:
            changed.append(path)
            if args.apply:
                path.write_text(new, encoding="utf-8")
    verb = "changed" if args.apply else "would change"
    print(f"{verb} {len(changed)} file(s)")
    for p in changed:
        print("  " + str(p.relative_to(REPO_ROOT)))
    return 1 if (not args.apply and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
