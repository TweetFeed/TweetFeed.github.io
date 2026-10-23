#!/usr/bin/env python3
"""Swap the Google Fonts <head> tags for preloads of the self-hosted woff2 files.

Why: Google serves Rubik / Alegreya Sans SC from fonts.gstatic.com under
URLs that differ per browser (phones get one Rubik file, desktop browsers
three others), so only phones could be preloaded. On desktop the text was
laid out in the fallback font and re-flowed when Rubik arrived (PSI CLS:
/api/ 0.154, /hunt/ 0.082, /tos/ 0.216). The fonts now live under fonts/
(@font-face at the top of css/tweetfeed.css), so the exact files can be
preloaded on every viewport.

Per file the script removes the Google tags (2 preconnects, 2 gstatic
preloads, 2 css2 preload + <noscript> pairs) and puts

    <link rel="preload" href="<prefix>fonts/rubik-latin.woff2" as="font" type="font/woff2" crossorigin>

(and the Alegreya one) where the gstatic preloads were. <prefix> is copied
from the page's own css/tweetfeed.css link ('', '../', '../../', or
404.html's '/tweetfeed-stage/'), so every depth works. Covers every .html
file plus the Jinja templates, so the next regen of tag/ and campaigns/
stays Google-free. Run it after pulling a page that still has the old tags.

Idempotent: a second run changes nothing.

Usage:
    python3 scripts/selfhost_fonts.py          # apply
    python3 scripts/selfhost_fonts.py --check  # dry-run, exit 1 if any file would change
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "scripts" / "templates"

# Order matters: the tags land in this order, Alegreya first as before.
PRELOAD_FILES = ("alegreya-sans-sc-latin.woff2", "rubik-latin.woff2")

CSS_LINK_RE = re.compile(r'href="([^"]*?)css/tweetfeed\.css\?v=\d+"')
# One whole line each (leading whitespace, tag, trailing whitespace).
GOOGLE_PRECONNECT_RE = re.compile(
    r'^\s*<link rel="preconnect" href="(?://fonts\.googleapis\.com|https://fonts\.gstatic\.com)"[^>]*>\s*$'
)
GSTATIC_PRELOAD_RE = re.compile(
    r'^(\s*)<link rel="preload" href="https://fonts\.gstatic\.com/[^"]*"[^>]*>\s*$'
)
GOOGLE_CSS2_RE = re.compile(
    r'^\s*(?:<noscript>)?<link (?:rel="preload" )?href="https://fonts\.googleapis\.com/css2\?[^"]*"[^>]*>(?:</noscript>)?\s*$'
)


def preload_tag(prefix: str, name: str) -> str:
    return f'<link rel="preload" href="{prefix}fonts/{name}" as="font" type="font/woff2" crossorigin>'


def convert(text: str) -> tuple[str, bool]:
    m = CSS_LINK_RE.search(text)
    if not m:
        return text, False  # not a full page (partial or redirect stub)
    prefix = m.group(1)
    wanted = [preload_tag(prefix, n) for n in PRELOAD_FILES]
    out: list[str] = []
    inserted = False
    for line in text.split("\n"):
        gs = GSTATIC_PRELOAD_RE.match(line)
        if gs:
            if not inserted:
                out.extend(gs.group(1) + tag for tag in wanted)
                inserted = True
            continue
        if GOOGLE_PRECONNECT_RE.match(line) or GOOGLE_CSS2_RE.match(line):
            continue
        out.append(line)
    new = "\n".join(out)
    if not inserted:
        # Already converted (or never had the Google tags): make sure the
        # preloads exist, anchored on the cdnjs preconnect.
        if all(t in new for t in wanted):
            return new, new != text
        anchor = re.search(r'^(\s*)<link rel="preconnect" href="https://cdnjs\.cloudflare\.com"[^>]*>\n', new, re.M)
        if not anchor:
            raise SystemExit("no anchor to insert the font preloads after")
        block = "".join(anchor.group(1) + t + "\n" for t in wanted)
        new = new[: anchor.end()] + block + new[anchor.end():]
    return new, new != text


def targets() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files", "*.html"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [REPO_ROOT / p for p in tracked] + sorted(TEMPLATE_DIR.glob("*.j2"))


def main() -> int:
    check = "--check" in sys.argv[1:]
    changed: list[Path] = []
    for path in targets():
        text = path.read_text(encoding="utf-8")
        new, did = convert(text)
        if did:
            changed.append(path)
            if not check:
                path.write_text(new, encoding="utf-8")
    verb = "would change" if check else "changed"
    print(f"{verb} {len(changed)} file(s)")
    for p in changed:
        print("  " + str(p.relative_to(REPO_ROOT)))
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
