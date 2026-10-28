#!/usr/bin/env python3
"""Build the minified stylesheets the pages link: css/<name>.min.css.

Why: PSI mobile flagged the 5 render-blocking sheets (~420 ms on / and
/search/) and 27 KiB of unminified CSS. Half of css/tweetfeed.css is
comments, so the pages now link css/tweetfeed.min.css, css/index.min.css
and css/table.min.css (gzip 32.8 + 6.5 + 4.3 KB -> 11.7 + 1.6 + 1.0 KB).

Edit the SOURCE (css/tweetfeed.css, css/index.css, css/table.css), never the
.min.css, then run this script and commit both. check_consistency.py fails
when a .min.css does not match its source.

The minifier is deliberately small: it drops comments, collapses whitespace
and trims it around { } ; and the last ; of a block. Strings ('...' and
"...") are copied byte for byte. Nothing else is rewritten (no colour or
number shortening, no rule merging), so the parsed CSS stays the same.

Usage:
    python3 scripts/build_css.py          # write the .min.css files
    python3 scripts/build_css.py --check  # dry-run, exit 1 if any is stale
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Sources under css/ that the pages link minified.
SOURCES = ("tweetfeed.css", "index.css", "table.css")

BANNER = "/* Built from css/{name} by scripts/build_css.py. Edit the source, not this file. */\n"

_WS_RE = re.compile(r"\s+")
_PUNCT_WS_RE = re.compile(r"\s*([{};])\s*")


def _segments(css: str) -> list[tuple[bool, str]]:
    """Split into (is_string, text) runs with comments removed. One pass, so
    an apostrophe inside a comment never opens a string."""
    out: list[tuple[bool, str]] = []
    code: list[str] = []
    i, n = 0, len(css)
    while i < n:
        c = css[i]
        if c == "/" and css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end == -1 else end + 2
            code.append(" ")
        elif c in "\"'":
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == "\\" else 1
            if code:
                out.append((False, "".join(code)))
                code = []
            out.append((True, css[i:j + 1]))
            i = j + 1
        else:
            code.append(c)
            i += 1
    if code:
        out.append((False, "".join(code)))
    return out


def minify(css: str) -> str:
    parts = []
    for is_string, text in _segments(css):
        if not is_string:
            text = _PUNCT_WS_RE.sub(r"\1", _WS_RE.sub(" ", text))
        parts.append(text)
    return "".join(parts).replace(";}", "}").strip() + "\n"


def built(name: str) -> str:
    source = (REPO_ROOT / "css" / name).read_text(encoding="utf-8")
    return BANNER.format(name=name) + minify(source)


def min_path(name: str) -> Path:
    return REPO_ROOT / "css" / name.replace(".css", ".min.css")


def main() -> int:
    check = "--check" in sys.argv[1:]
    stale = []
    for name in SOURCES:
        out = min_path(name)
        text = built(name)
        current = out.read_text(encoding="utf-8") if out.exists() else None
        if current == text:
            continue
        stale.append(str(out.relative_to(REPO_ROOT)))
        if not check:
            out.write_text(text, encoding="utf-8")
    verb = "stale" if check else "wrote"
    print(f"{verb}: {', '.join(stale) if stale else 'none'}")
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
