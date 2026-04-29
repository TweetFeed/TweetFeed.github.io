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

The API doesn't have a direct `?value=` lookup. Pull a window and filter client-side:

```bash
curl -s 'https://api.tweetfeed.live/v1/month' \
  | jq --arg v 'suspicious-domain.com' '[.[] | select(.value | contains($v))]'
```

For IP/hash exact match, use `select(.value == $v)`. For longer retention, query `year` via the raw CSV.

## Tag-family taxonomy

119 tags in `tags.yaml` split by casing:
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

- Human API docs: `https://tweetfeed.live/api.html`
- API catalog (RFC 9727 linkset): `https://tweetfeed.live/.well-known/api-catalog`
- Researcher directory: `https://tweetfeed.live/researchers.html`
- Charts/stats: `https://tweetfeed.live/graphs.html`
- Source: `https://github.com/0xDanielLopez/TweetFeed` (the feed data repo, CC0)
