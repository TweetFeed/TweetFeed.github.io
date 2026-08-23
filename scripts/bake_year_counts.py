#!/usr/bin/env python3
"""Keep the "Nk+ ... past year" claim on each /malicious-<type>/ page true,
by generating it from the rolling year feed instead of typing it by hand.

Why this exists
---------------
The four year-window counts were hand-corrected on 2026-08-22 and gated the
same day. The next morning the daily workflow failed on the gate: the claim
said 9.6k+ IPs, the rolling 365-day window had slipped to 9,569, and the
whole regen commit (tag pages, freshness bake, sitemap lastmod) stopped
being pushed. See year_counts.py for the full story. The lesson is not "pick
a rounder number", it is that a hand-typed figure measured against a moving
window is a scheduled failure - three of the five claims were sitting inside
a 3.5% margin at the time.

So the figure is generated here, from the same feed the gate reads
(year_counts.fetch_year_counts), and the gate keeps blocking. After this
script runs, the gate should only ever fire on a hand edit it could not
reach - which is exactly what a gate is for.

Hysteresis, and why the margins are asymmetric
----------------------------------------------
A number regenerated to the exact current count would be rewritten every
single day, churning five meta descriptions and their git history for no
reader benefit, and would sit one row away from overstating. So:

  * The claim is written at 95% of the real count, truncated DOWN to two
    significant figures. Understating is safe by design - the gate tolerates
    it, and a threat feed that undersells its own corpus costs nothing.
  * It is only rewritten when it leaves the band [85%, 97%] of the real
    count: too close to reality (about to overstate) or gone stale. In
    between, the file is left alone, so the copy is stable for weeks.

REWRITE_CEILING is 0.97 and not 1.0 on purpose: rewriting only on an actual
overstatement would mean the gate and this script race each other on the same
day, which is the failure being fixed.

Run by regen-landing-pages.yml between bake_freshness.py and
check_consistency.py, so the gate always inspects the freshly-baked copy.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from year_counts import YEAR_CLAIM_PAGES, YEAR_CLAIM_RE, fetch_year_counts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

SAFETY = 0.95           # what fraction of the real count gets published
REWRITE_CEILING = 0.97  # above this fraction, the claim is too tight -> rewrite
REWRITE_FLOOR = 0.85    # below this fraction, the claim is stale -> rewrite


def claim_value(actual: int) -> int:
    """The number to publish: SAFETY of `actual`, truncated down to two
    significant figures so it reads like a human wrote it (9k+, 2.5k+, 50k+)
    rather than a meter reading."""
    target = actual * SAFETY
    if target <= 0:
        return 0
    step = 10 ** (math.floor(math.log10(target)) - 1)
    return int(math.floor(target / step) * step)


def claim_text(value: int) -> str:
    """Render a claim value in the k+ notation the copy already uses. Every
    count these pages carry is in the thousands, so two significant figures
    always lands on at most one decimal of k."""
    k = value / 1000
    return (f"{k:.0f}" if float(k).is_integer() else f"{k:.1f}") + "k+"


def parse_claim(text: str) -> str:
    return f"{float(text) * 1000:.0f}"


def bake_page(page: str, actual: int) -> tuple[bool, str]:
    """Returns (changed, message)."""
    path = REPO_ROOT / page
    html = path.read_text(encoding="utf-8")
    written = {m.group(1) for m in YEAR_CLAIM_RE.finditer(html)}
    if not written:
        # Same failure mode the gate guards: if the copy stops carrying a
        # claim in a shape this regex knows, silence here would look like
        # success while the number quietly rotted.
        raise ValueError(f"{page}: no 'Nk+ ... past year' claim found; the copy has drifted from the pattern")

    new_value = claim_value(actual)
    new_text = claim_text(new_value)

    stale = [w for w in written if int(float(w) * 1000) < actual * REWRITE_FLOOR]
    tight = [w for w in written if int(float(w) * 1000) > actual * REWRITE_CEILING]
    if not stale and not tight:
        only = sorted(written)[0] if len(written) == 1 else "/".join(sorted(written))
        return False, f"  [keep] {page}: {only}k+ still inside the band (real {actual:,})"

    n = 0

    def _sub(m: re.Match) -> str:
        nonlocal n
        n += 1
        return new_text + m.group(0)[len(m.group(1)) + 2:]

    html = YEAR_CLAIM_RE.sub(_sub, html)
    path.write_text(html, encoding="utf-8")
    why = "too tight" if tight else "stale"
    return True, (
        f"  [bake] {page}: {'/'.join(sorted(written))}k+ -> {new_text} "
        f"in {n} place(s) (real {actual:,}, {why})"
    )


def main() -> int:
    real = fetch_year_counts()
    if real is None:
        print("  (skipped: year.csv unreachable, offline run)")
        return 0

    changed = 0
    for page, ioc_type in YEAR_CLAIM_PAGES.items():
        actual = real.get(ioc_type, 0)
        if actual <= 0:
            # A type missing from the feed is a data problem, not a copy
            # problem; rewriting the page to "0k+" would be worse than
            # leaving yesterday's number and letting the gate judge it.
            print(f"  [skip] {page}: no {ioc_type} rows in year.csv")
            continue
        did, msg = bake_page(page, actual)
        changed += did
        print(msg)
    print(f"  {changed} page(s) rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
