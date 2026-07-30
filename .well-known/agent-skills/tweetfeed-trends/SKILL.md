---
name: tweetfeed-trends
description: Pull TweetFeed's community IOC trend analytics - 31-day daily volume by type, week-over-week top-moving tags, most-abused TLDs among malicious domains, and the new-vs-recurring novelty ratio. Invoke when the user asks "what's trending in TweetFeed right now", "which malware family is spiking this week", "what TLDs are most abused", or wants an aggregate volume/novelty snapshot instead of raw IOC rows.
---

# TweetFeed Trends

Aggregate analytics computed from the same 15-minute pipeline that feeds the raw IOC endpoints, regenerated alongside it. Raw data: `https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/trends.json` (CC0).

```bash
curl -s https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/trends.json | jq .
```

## Response shape

```json
{
  "daily": [ {"date": "2026-07-01", "total": 412, "types": {"url": 190, "domain": 150, "ip": 40, "sha256": 20, "md5": 12}}, ... ],
  "movers": [ {"tag": "lumma", "current": 42, "previous": 17, "delta_pct": 147.1}, ... ],
  "tlds": [ {"tld": "com", "count": 812}, {"tld": "top", "count": 340}, ... ],
  "novelty": {"distinct_this_week": 1830, "new": 1102, "recurring": 728, "new_pct": 60.2}
}
```

- `daily`: 31 days of totals plus a per-type breakdown (url/domain/ip/sha256/md5) - use for a rolling 30-day volume chart.
- `movers`: current vs previous 7-day tag counts, ranked by change magnitude - answers "what's spiking".
- `tlds`: top TLDs among malicious domains from the last 30 days.
- `novelty`: the share of this week's distinct IOC values that are new versus recurring from a prior window.

Exact field names can shift slightly as the schema evolves - always inspect a live response rather than hardcoding the shape from this file.

## Human page

`https://tweetfeed.live/trends/` - charts the same data (daily volume, top movers, TLD breakdown, novelty rate) for a human reader.

## MCP equivalent

`get_trends` tool - no arguments, returns the same daily/movers/tlds/novelty structure.

## Gotchas

- This is aggregate/statistical data, not individual IOC rows - for a lookup of one specific value use the `tweetfeed-ioc-lookup` skill instead.
- `movers` and `novelty` are week-over-week comparisons; a tag with zero prior-week activity shows as effectively infinite growth - sanity-check `previous` before reporting a percentage.
- Regenerated with the rest of the feed (every 15 min), so `daily`'s most recent entry is a partial day until 00:00 UTC.

## License

CC0 1.0 Universal (public domain). No attribution required.

## Related pointers

- Single-IOC lookup: skill `tweetfeed-ioc-lookup`
- Campaign clustering (grouped by shared infrastructure, not just tag counts): skill `tweetfeed-campaigns`
- Source: `https://github.com/0xDanielLopez/TweetFeed`
