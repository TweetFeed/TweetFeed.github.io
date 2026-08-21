---
name: tweetfeed-ioc-lookup
description: Look up one specific IOC (URL, domain, IP, MD5 or SHA-256 hash) in TweetFeed's full 365-day retention window - first seen, last seen, how many times it was reported, which researchers reported it, and optional AI-generated context. Invoke when the user asks "is this domain/IP/hash/URL in TweetFeed", "has this IOC been reported before", or wants a single-value exact-match check instead of browsing a time-windowed feed. Public HTTP API, no auth, CC0 licensed.
---

# TweetFeed IOC Lookup

Direct exact-match lookup over the full 365-day retention window, separate from the `/v1/{time}` route pattern used to browse the feed. Base: `https://api.tweetfeed.live/v1/ioc`.

## Route

```bash
curl -s 'https://api.tweetfeed.live/v1/ioc/example.com'

# equivalent query-parameter form, easier when the value needs URL-escaping
curl -s 'https://api.tweetfeed.live/v1/ioc?value=example.com'
```

Defanged input (`hxxp://`, `[.]`) is refanged server-side before matching, so `example[.]com` and `example.com` return the same result. `http://` and `https://` variants of a URL are treated the same way.

## Response shape

No match:

```json
{"found": false, "query": "example.com", "window": "365d", "records": []}
```

Match: `found` is `true`, `query` echoes the normalised value that was actually looked up, and `records` holds one entry per time the value was posted (same fields as the `/v1/{time}` rows: `date`, `user`, `type`, `value`, `tags`, `tweet`).

Optional sidecar fields, present only when data exists for that value:

- `ai`: AI-generated context from the enrichment job - `summary` (<=200 chars), `family` (malware family or null), `threat_type`, `confidence` (0-1).
- `related`: up to 5 other IOCs posted in the same source tweet(s) as the looked-up value.
- `external`: cross-feed corroboration from public abuse.ch feeds (URLhaus/ThreatFox/MalwareBazaar).
- `net`: for IP lookups only - network metadata (org/ASN, country, city, or a `bogon` flag for reserved ranges) from ipinfo.io, refreshed every 6h.

## Exact match, not substring

This endpoint matches the value exactly. For partial matches (every URL on a given host, for example) filter a time window client-side instead:

```bash
curl -s 'https://api.tweetfeed.live/v1/month' \
  | jq --arg v 'suspicious-domain.com' '[.[] | select(.value | contains($v))]'
```

## MCP equivalent

`enrich_ioc` tool: same exact 365-day lookup, auto-detects IOC type from the value, with a 30-day substring fallback on a miss. `check_url` / `check_ip` / `check_hash` are narrower 30-day substring-match variants for when the type is already known and an exact match isn't required.

## Gotchas

- Response is a single object, not an array like the `/v1/{time}` routes.
- `query` in the response is the normalised value, which may differ from what you sent in (defanged input, scheme variants).
- The lookup window is 365 days; values older than that return `found: false` even if they were once in the feed.

## License

IOC data is CC0 1.0 Universal (public domain). The `ai`/`external`/`net` sidecars are generated context, not canonical feed data, but are released under the same terms.

## Related pointers

- General feed queries (time-windowed, filterable): skill `tweetfeed-iocs`.
- Human API docs: `https://tweetfeed.live/api/`
- Source: `https://github.com/0xDanielLopez/TweetFeed` (CC0)
