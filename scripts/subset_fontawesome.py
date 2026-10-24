#!/usr/bin/env python3
"""Build the self-hosted, subset Font Awesome 5.15.4 Free under vendor/fontawesome/.

Why: every page loaded Font Awesome from cdnjs (a render-blocking-ish CSS
file, then 79 KB + 78 KB + 14 KB of woff2 from a second origin), and PSI put
those fonts in the LCP path. The site draws a few dozen icons, so the three
fonts are cut down to exactly those glyphs and served from our own origin,
same as Rubik / Alegreya (scripts/selfhost_fonts.py). Same library, same
version, same glyph outlines, same CSS rules: only the font files shrink.

What it does (re-runnable; the committed files are exactly its output):

1. Takes the pristine cdnjs originals (css/all.min.css and the three
   webfonts/fa-{solid-900,regular-400,brands-400}.woff2). If --src does not
   have them yet, it downloads them from cdnjs. The CSS is checked against
   the same SRI hash the pages used to carry, the fonts against the SHA-256
   pinned below; any mismatch aborts.
2. Inventories every icon the site can show by scanning the working tree
   (tracked + untracked, not ignored): fa-NAME tokens in *.html, *.j2, *.js,
   *.py, *.yaml, *.css (nav icons live in scripts/site_ia.py, copy/check
   icons in js/, templates and inline <script> blocks in the pages), plus
   content:"\\fXXX" escapes in CSS (sb-admin-2 draws its collapse chevrons
   that way). FA utility classes (fa-fw, fa-2x, fa-spin, ...) are not icons
   and are dropped. Icon names must appear as literal fa-NAME tokens
   somewhere in the tree. If the code ever builds one ('fa-' + x, fa-${x},
   fa-{{ x }}) the script stops instead of guessing.
3. Resolves each name to its codepoint through all.min.css. Names FA 5.15.4
   does not have (FA6-only names, typos) are pre-existing dead classes: they
   are listed, never fatal. Every (style, name) pair that shares one class
   attribute / quoted string with fas/far/fab/fa is checked against the FULL
   font first, then against the subset.
4. Subsets each font to the union of all codepoints (over-inclusive across
   styles on purpose: a codepoint a style lacks is simply skipped), then
   proves every kept glyph has the same outline and advance as in the
   original.
5. Writes vendor/fontawesome/{css/all.min.css, webfonts/*.woff2, icons.txt,
   LICENSE.txt}. The CSS is the original with each @font-face src cut down
   to the woff2 file (font-display:block kept); eot/woff/ttf/svg are gone.

Run it after adding an icon (a new fa-NAME in a page, template or script) so
the font and icons.txt pick it up; scripts/check_consistency.py fails until you do.
The page tags come from scripts/selfhost_fontawesome.py. A page that uses an icon missing from
icons.txt shows an empty box.

Setup (fonttools + brotli are not in the repo, use a throwaway venv):
    python3 -m venv /tmp/fa-venv && /tmp/fa-venv/bin/pip install fonttools brotli

Usage:
    /tmp/fa-venv/bin/python scripts/subset_fontawesome.py             # rebuild
    /tmp/fa-venv/bin/python scripts/subset_fontawesome.py --check     # dry-run, exit 1 if a committed file would change
    /tmp/fa-venv/bin/python scripts/subset_fontawesome.py --src DIR   # DIR holds all.min.css + the 3 woff2 (default: a temp dir, downloaded)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# fonttools + brotli are only needed to rebuild the fonts. scripts/check_consistency.py
# imports this module for the icon scan, so a missing install is reported by main()
# (first thing it does), not at import time.
try:
    import brotli  # noqa: F401  (woff2 needs it)
    from fontTools import subset
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    from fontTools.ttLib import TTFont
    FONTTOOLS_MISSING = False
except ImportError:
    FONTTOOLS_MISSING = True

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "vendor" / "fontawesome"

FA_VERSION = "5.15.4"
CDN = f"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/{FA_VERSION}"
# The integrity value the pages carried for css/all.min.css (sha512, base64).
CSS_SRI = "1ycn6IcaQQ40/MKBW2W4Rhis/DbILU74C1vSrLJxCq57o941Ym01SwNsOMqvEBFlcgUa6xLiPY/NS5R+E6ztJQ=="

# stem -> (class prefixes that select it, SHA-256 of the cdnjs original)
FONTS = {
    "fa-solid-900": (("fas", "fa"), "9834b82ad26e2a37583d22676a12dd2eb0fe7c80356a2114d0db1aa8b3899537"),
    "fa-regular-400": (("far",), "e42a88444448ac3d60549cc7c1ff2c8a9cac721034c073d80a14a44e79730cca"),
    "fa-brands-400": (("fab",), "8ea8791754915a898a3100e63e32978a6d1763be6df8e73a39d3a90d691cdeef"),
}
STYLE_TO_FONT = {s: stem for stem, (styles, _) in FONTS.items() for s in styles}

SCAN_SUFFIXES = {".html", ".j2", ".js", ".py", ".yaml", ".yml", ".css"}
SKIP_PREFIXES = ("vendor/fontawesome/", "node_modules/")
# These two name fa-NAME / fa-{n} as examples in docstrings and f-strings, not as icons.
SKIP_FILES = {"scripts/subset_fontawesome.py", "scripts/check_consistency.py"}

# fa-NAME with a left boundary, so "tf-fa-x" and "font-awesome" never match.
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])fa-([a-z0-9]+(?:-[a-z0-9]+)*)")
# FA's non-icon classes, plus the webfont file names a page may preload.
UTILITY_RE = re.compile(
    r"fw|xs|sm|lg|\d+x|spin|pulse|rotate-\d+|flip-[a-z]+|stack(?:-\dx)?|inverse|border"
    r"|pull-(?:left|right)|ul|li|layers(?:-[a-z]+)?|w-\d+|(?:solid|regular|brands)-\d+"
)
# One quoted run (class attribute value or JS string) holding at least one fa-NAME.
QUOTED_RE = re.compile(r"""["']([^"'<>\n]*(?<![A-Za-z0-9_-])fa-[a-z0-9][^"'<>\n]*)["']""")
STYLES = {"fa", "fas", "far", "fab", "fal", "fad"}
# content:"\f107" / content:'\f107'; FA lives in the private use area.
CSS_ESCAPE_RE = re.compile(r"""content\s*:\s*["']\\([0-9a-fA-F]{4})["']""")
# Names built at run time cannot be enumerated: 'fa-' + x, `fa-${x}`, fa-{{ x }}, 'fas ' + x.
DYNAMIC_RES = (
    re.compile(r"(?<![A-Za-z0-9_-])fa-(?![a-z0-9])"),
    re.compile(r"""["'`]fa[srbld]?\s*["'`]\s*[+~]"""),
)

# Matches one icon rule in all.min.css: .fa-NAME:before{content:"\fXXX"}
ICON_RULE_RE = re.compile(r'\.fa-([a-z0-9-]+):before\{content:"\\([0-9a-f]+)"\}')
FONT_FACE_SRC_RE = re.compile(
    r"src:url\(\.\./webfonts/(fa-[a-z]+-\d+)\.eot\);src:[^}]*"
)

LICENSE_TEXT = f"""\
Font Awesome Free {FA_VERSION} by @fontawesome - https://fontawesome.com
License - https://fontawesome.com/license/free

Icons: CC BY 4.0 License (https://creativecommons.org/licenses/by/4.0/)
Fonts: SIL OFL 1.1 License (https://scripts.sil.org/OFL)
Code:  MIT License (https://opensource.org/licenses/MIT)

Copyright (c) Fonticons, Inc. (https://fontawesome.com)

What is in this directory:
  css/all.min.css       the original stylesheet (MIT); only the @font-face src was
                        reduced to the woff2 file
  webfonts/*.woff2      the original fonts (OFL 1.1 for the font files, CC BY 4.0
                        for the icon artwork) cut down to the glyphs listed in
                        icons.txt; outlines are unchanged
  icons.txt             manifest of the kept icons

Rebuilt from the cdnjs originals by scripts/subset_fontawesome.py.
"""


def sha512_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha512(data).digest()).decode()


def load_originals(src: Path) -> dict[str, bytes]:
    """Return the verified originals {filename: bytes}, downloading what is missing."""
    wanted = {"all.min.css": f"{CDN}/css/all.min.css"}
    wanted.update({f"{stem}.woff2": f"{CDN}/webfonts/{stem}.woff2" for stem in FONTS})
    src.mkdir(parents=True, exist_ok=True)
    out: dict[str, bytes] = {}
    for name, url in wanted.items():
        path = src / name
        if not path.exists():
            print(f"download {url}")
            with urllib.request.urlopen(url, timeout=60) as resp:
                path.write_bytes(resp.read())
        out[name] = path.read_bytes()
    if sha512_b64(out["all.min.css"]) != CSS_SRI:
        raise SystemExit(f"{src / 'all.min.css'} does not match the SRI hash of Font Awesome {FA_VERSION}")
    for stem, (_, sha256) in FONTS.items():
        if hashlib.sha256(out[f"{stem}.woff2"]).hexdigest() != sha256:
            raise SystemExit(f"{src / (stem + '.woff2')} does not match the pinned SHA-256")
    return out


def source_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    files = []
    for rel in listed:
        if not rel or rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES):
            continue
        path = REPO_ROOT / rel
        if path.suffix in SCAN_SUFFIXES and path.is_file():
            files.append(path)
    return sorted(files)


class Inventory:
    def __init__(self) -> None:
        self.names: set[str] = set()                    # fa-NAME tokens, utilities dropped
        self.escapes: set[int] = set()                  # content:"\fXXX" codepoints
        self.pairs: set[tuple[str, str]] = set()        # (style class, name) sharing one quoted run
        self.dynamic: list[str] = []                    # file:line of anything built at run time
        self.files = 0


def scan(files: list[Path]) -> Inventory:
    inv = Inventory()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        inv.files += 1
        rel = path.relative_to(REPO_ROOT)
        for m in TOKEN_RE.finditer(text):
            if not UTILITY_RE.fullmatch(m.group(1)):
                inv.names.add(m.group(1))
        for m in QUOTED_RE.finditer(text):
            words = m.group(1).split()
            styles = [w for w in words if w in STYLES]
            for w in words:
                t = TOKEN_RE.fullmatch(w)
                if t and not UTILITY_RE.fullmatch(t.group(1)):
                    inv.pairs.update((s, t.group(1)) for s in styles)
        for m in CSS_ESCAPE_RE.finditer(text):
            cp = int(m.group(1), 16)
            if 0xE000 <= cp <= 0xF8FF:
                inv.escapes.add(cp)
        for rx in DYNAMIC_RES:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                inv.dynamic.append(f"{rel}:{line}: {text[m.start():m.start() + 60].splitlines()[0]}")
    return inv


def subset_font(font_bytes: bytes, codepoints: set[int]) -> bytes:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.drop_tables = opts.drop_tables + ["FFTM"]  # FontForge timestamp, pure noise (and a warning)
    font = subset.load_font(io.BytesIO(font_bytes), opts)
    subsetter = subset.Subsetter(opts)
    subsetter.populate(unicodes=sorted(codepoints))
    subsetter.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    return buf.getvalue()


def assert_same_glyphs(stem: str, full: TTFont, sub: TTFont, codepoints: set[int]) -> int:
    """Every kept glyph must draw and advance exactly like the original."""
    fcmap, scmap = full.getBestCmap(), sub.getBestCmap()
    fgs, sgs = full.getGlyphSet(), sub.getGlyphSet()
    kept = 0
    for cp in sorted(codepoints & set(fcmap)):
        if cp not in scmap:
            raise SystemExit(f"{stem}: U+{cp:04X} is in the original but missing from the subset")
        a, b = DecomposingRecordingPen(fgs), DecomposingRecordingPen(sgs)
        fg, sg = fgs[fcmap[cp]], sgs[scmap[cp]]
        fg.draw(a)
        sg.draw(b)
        if a.value != b.value or fg.width != sg.width:
            raise SystemExit(f"{stem}: U+{cp:04X} differs from the original")
        kept += 1
    extra = set(scmap) - codepoints
    if extra:
        raise SystemExit(f"{stem}: subset holds unrequested codepoints {sorted(map(hex, extra))}")
    return kept


def build(originals: dict[str, bytes]) -> tuple[dict[Path, bytes], list[str]]:
    """Return ({output path: bytes}, report lines). Raises SystemExit on a blocker."""
    report: list[str] = []
    inv = scan(source_files())
    if inv.dynamic:
        raise SystemExit(
            "icon names built at run time cannot be enumerated; write them as literal fa-NAME tokens:\n  "
            + "\n  ".join(inv.dynamic)
        )

    css = originals["all.min.css"].decode("utf-8")
    name_to_cp = {n: int(cp, 16) for n, cp in ICON_RULE_RE.findall(css)}
    cp_to_name: dict[int, str] = {}
    for n, cp in name_to_cp.items():
        cp_to_name.setdefault(cp, n)  # first name in CSS order is the canonical one

    dead = sorted(n for n in inv.names if n not in name_to_cp)
    names = {n for n in inv.names if n in name_to_cp}
    codepoints = {name_to_cp[n] for n in names} | inv.escapes
    names |= {cp_to_name[cp] for cp in inv.escapes if cp in cp_to_name}

    fulls = {stem: TTFont(io.BytesIO(originals[f"{stem}.woff2"])) for stem in FONTS}
    cmaps = {stem: f.getBestCmap() for stem, f in fulls.items()}
    outputs: dict[Path, bytes] = {}
    sizes: list[str] = []
    subs: dict[str, TTFont] = {}
    for stem in FONTS:
        data = subset_font(originals[f"{stem}.woff2"], codepoints)
        subs[stem] = TTFont(io.BytesIO(data))
        kept = assert_same_glyphs(stem, fulls[stem], subs[stem], codepoints)
        outputs[OUT_DIR / "webfonts" / f"{stem}.woff2"] = data
        sizes.append(f"  {stem}.woff2: {len(originals[stem + '.woff2'])} -> {len(data)} bytes, {kept} glyphs")

    # (style, name) pairs: the full font first (missing there = pre-existing), then the subset (missing = bug).
    missing_in_full: list[str] = []
    for style, name in sorted(inv.pairs):
        if name not in name_to_cp:
            continue  # already listed as dead
        stem = STYLE_TO_FONT.get(style)
        cp = name_to_cp[name]
        if stem is None or cp not in cmaps[stem]:
            missing_in_full.append(f"{style} fa-{name}")
        elif cp not in subs[stem].getBestCmap():
            raise SystemExit(f"{stem}: fa-{name} (U+{cp:04X}) is in the full font but not in the subset")
    # Names without a style class (site_ia.py, hasClass checks) and CSS escapes: some font must have the glyph.
    for cp in sorted(codepoints):
        if not any(cp in c for c in cmaps.values()):
            missing_in_full.append(f"U+{cp:04X} ({cp_to_name.get(cp, '?')})")

    faces = FONT_FACE_SRC_RE.subn(lambda m: f'src:url(../webfonts/{m.group(1)}.woff2) format("woff2")', css)
    new_css, count = faces
    if count != len(FONTS) or re.search(r"\.(eot|woff[^2]|ttf|svg)", new_css):
        raise SystemExit(f"expected {len(FONTS)} @font-face rules reduced to woff2, got {count}")
    outputs[OUT_DIR / "css" / "all.min.css"] = new_css.encode("utf-8")

    manifest = [
        f"# Font Awesome Free {FA_VERSION} icons kept in the self-hosted subset (one per line, sorted).",
        "# Generated by scripts/subset_fontawesome.py from the fa-NAME tokens in the tree; rerun it, do not edit.",
    ] + [f"fa-{n}" for n in sorted(names)]
    outputs[OUT_DIR / "icons.txt"] = ("\n".join(manifest) + "\n").encode("utf-8")
    outputs[OUT_DIR / "LICENSE.txt"] = LICENSE_TEXT.encode("utf-8")

    report.append(
        f"scanned {inv.files} files: {len(names)} icons, {len(codepoints)} codepoints, "
        f"{len(inv.pairs)} (style, name) pairs checked"
    )
    report.extend(sizes)
    report.append(f"dead classes (not in FA {FA_VERSION}): {', '.join('fa-' + n for n in dead) or 'none'}")
    report.append(f"missing from the full font (pre-existing): {', '.join(missing_in_full) or 'none'}")
    report.append("css-drawn glyphs: " + (", ".join(f"U+{c:04X}" for c in sorted(inv.escapes)) or "none"))
    return outputs, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="dry-run, exit 1 if any output would change")
    ap.add_argument("--src", type=Path, default=Path(tempfile.gettempdir()) / f"fontawesome-{FA_VERSION}-original",
                    help="directory with the cdnjs originals (downloaded there if missing)")
    args = ap.parse_args()
    if FONTTOOLS_MISSING:
        raise SystemExit("needs fonttools + brotli: python3 -m venv V && V/bin/pip install fonttools brotli")

    outputs, report = build(load_originals(args.src))
    print("\n".join(report))
    stale = [p for p, data in outputs.items() if not p.exists() or p.read_bytes() != data]
    if not args.check:
        for path, data in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    verb = "would change" if args.check else "changed"
    print(f"{verb} {len(stale)} file(s)")
    for p in stale:
        print("  " + str(p.relative_to(REPO_ROOT)))
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
