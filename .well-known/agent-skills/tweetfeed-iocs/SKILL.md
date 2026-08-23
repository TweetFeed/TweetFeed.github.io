---
name: tweetfeed
description: Query TweetFeed (tweetfeed.live) for security IOCs shared by the infosec community on Twitter/X. Invoke when the user asks about recent phishing URLs, malware domains, C2 IPs, malware hashes (MD5/SHA256), threat actors, malware families, or mentions the TweetFeed service. Data is aggregated from ~95 Twitter sources every 15 min and licensed CC0.
---

# TweetFeed IOC Queries

Public API at `https://api.tweetfeed.live/v1` - no auth, no API key, ~100k req/day free-tier headroom (actual usage ~7k/day as of 2026-04-18). Cloudflare Worker backed, JSON response. Use plain `curl`.

## Route pattern

```
/v1/{time}[/{filter1}[/{filter2}]]
```

- `time`: `today` · `week` · `month` · `year`
- `filter1`, `filter2` (both optional, order-independent):
  - `@username` - tweets by a specific handle (include the `@`)
  - type: `url` · `domain` · `ip` · `sha256` · `md5`
  - tag: anything else (case-insensitive substring match against the tags column, e.g. `phishing`, `cobaltstrike`, `APT`, `Lockbit`)

Two different-category filters are ANDed. `year` returns a 302 to the raw CSV on GitHub (16 MB); follow with `curl -L` if you need the full file.

## Response shape

JSON array (not wrapped in a `data` key). Each element:

```json
{
  "date": "2026-04-18 20:54:30",
  "user": "skocherhan",
  "type": "url",
  "value": "http://example.com/phish",
  "tags": ["phishing"],
  "tweet": "https://x.com/..."
}
```

Empty `[]` when no matches. Max 10 000 rows per response. Always pipe to `jq` for inspection.

## Common queries

```bash
# Today's phishing URLs
curl -s 'https://api.tweetfeed.live/v1/today/phishing/url'

# CobaltStrike IPs from the last month
curl -s 'https://api.tweetfeed.live/v1/month/cobaltstrike/ip'

# Everything a specific researcher posted this week
curl -s 'https://api.tweetfeed.live/v1/week/@JCyberSec_'

# All SHA256 hashes shared today
curl -s 'https://api.tweetfeed.live/v1/today/sha256'

# Just today's entries unfiltered
curl -s 'https://api.tweetfeed.live/v1/today'

# Full year dataset (CSV, 302 redirect)
curl -sL 'https://api.tweetfeed.live/v1/year' > year.csv
```

## Check if a specific IOC is in the feed

There is a direct exact-match lookup over the full 365-day retention window, plus a pre-365-day archive on top:

```bash
curl -s 'https://api.tweetfeed.live/v1/ioc/example.com'

# equivalent query-parameter form, easier when the value needs escaping
curl -s 'https://api.tweetfeed.live/v1/ioc?value=example.com'
```

Response when there is no match:

```json
{"found": false, "query": "example.com", "window": "365d", "records": []}
```

On a hit, `found` is `true` and `records` holds one aggregated entry per IOC type the value matched (`first_seen`, `last_seen`, `count`, `users`, `tags`, `tweets` - not one row per posting like the `/v1/{time}` rows). `query` echoes the normalised value that was actually looked up: defanged input (`hxxp://`, `[.]`) is refanged server-side before matching, so the defanged and plain forms behave the same. Optional sidecars, present only when data exists for that value: `ai` (summary/family/threat type), `external` (abuse.ch corroboration), `net` (IP network metadata), `reg` (RDAP registration, domain/url lookups only), and `archive` (hits older than the 365-day window, back to `first_date` in `archive/meta.json` - additive to `found`/`records`, never merged with them; can appear even when `found` is `false`, or alongside `found: true`).

The lookup is exact, not a substring search. For partial matches (for example every URL on a given host) filter a window client-side instead:

```bash
curl -s 'https://api.tweetfeed.live/v1/month' \
  | jq --arg v 'suspicious-domain.com' '[.[] | select(.value | contains($v))]'
```

MCP equivalent: `enrich_ioc` tool (same exact 365-day-plus-archive lookup, with a 30-day substring fallback on a miss).

## Campaign clusters

For grouped threat activity instead of raw rows, use the separate campaigns endpoint (not part of the `/v1/{time}` route pattern above):

```bash
curl -s 'https://api.tweetfeed.live/v1/campaigns' | jq '.campaigns[] | {id, name, confidence, ioc_count}'
```

Each campaign clusters related IOCs from a rolling 30-day window by shared infrastructure (registered domain, cross-domain URL path patterns) or tag, then an AI layer names and describes the cluster - it never adds or removes IOCs, every `iocs` entry is verbatim from the feed. Regenerated daily; `stale: true` plus `stale_since` means the last run failed and this is the previous day's document.

Each campaign also carries optional `ioc_count_1d`/`ioc_count_7d`/`ioc_count_30d` int fields (IOCs seen in the last 1/7/30 days; `ioc_count` stays the total across the full window). They may be absent on older documents - a missing `ioc_count_7d` should be treated as "currently active", not as zero. `ioc_count_7d > 0` is what identifies a campaign as currently active.

MCP equivalent: `get_campaigns` tool, optional `brand` (substring match on `targeted_brand`), `min_confidence` (`low`/`medium`/`high`), `limit` (1-50, default 20).

Human page: `https://tweetfeed.live/campaigns/`.

## Tag-family taxonomy

92 tags in `tags.yaml` split by casing:
- **PascalCase for malware families** (avoid substring collisions): `#CobaltStrike`, `#AkiraRansomware`, `#PlayRansomware`, `#Lockbit3`, `#Kimsuky`
- **lowercase for generic categories**: `#phishing`, `#scam`, `#ransomware`, `#malware`, `#C2`, `#credtheft`

Filter values are case-insensitive - `cobaltstrike` matches both `#CobaltStrike` and `#cobaltstrike` in the data.

## Gotchas

- Response is a plain array, not `{data: [...]}`. Always use `jq '.[] | ...'`.
- `@username` filter needs the literal `@` prefix in the URL (e.g. `/week/@malwrhunterteam`). The Worker strips it internally before matching.
- Year endpoint does NOT go through the Worker - it 302s to raw GitHub. The Worker redirects because the year CSV exceeds the Worker CPU budget.
- Tag matching is substring: `apt` in filter matches `#APT28`, `#APT29`, `#ShadowAPT` etc. Use a more specific tag to disambiguate.
- The feed refreshes every 15 min. `today` resets at 00:00 UTC (full wipe + rebuild from the day's tweets).

## License

All IOC data is CC0 1.0 Universal (public domain). No attribution required for the feed rows. The website, code, and branding are separate (not CC0).

## Related pointers

- Human API docs: `https://tweetfeed.live/api/`
- API catalog (RFC 9727 linkset): `https://tweetfeed.live/.well-known/api-catalog`
- Researcher directory: `https://tweetfeed.live/researchers/`
- Charts/stats: `https://tweetfeed.live/graphs/`
- Source: `https://github.com/0xDanielLopez/TweetFeed` (the feed data repo, CC0)
