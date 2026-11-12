---
name: tweetfeed-trends
description: Pull TweetFeed's community IOC trend analytics - 31-day daily volume by type, week-over-week top-moving tags, most-abused TLDs among malicious domains, and the new-vs-recurring novelty ratio. Invoke when the user asks "what's trending in TweetFeed right now", "which malware family is spiking this week", "what TLDs are most abused", or wants an aggregate volume/novelty snapshot instead of raw IOC rows.
---

# TweetFeed Trends

Aggregate analytics computed from the same 15-minute pipeline that feeds the raw IOC endpoints, regenerated alongside it. Raw data: `https://api.tweetfeed.live/v1/trends` (CC0).

```bash
curl -s https://api.tweetfeed.live/v1/trends | jq .
```

## Response shape

```json
{
  "version": 1,
  "generated_at": "2026-11-12T19:00:21Z",
  "daily": {"days": 31, "dates": ["2026-10-13", "..."], "total": [412, "..."], "types": {"url": [190, "..."], "domain": [150, "..."], "ip": [40, "..."], "sha256": [20, "..."], "md5": [12, "..."]}},
  "movers": {
    "current_range": ["2026-11-06", "2026-11-12"],
    "previous_range": ["2026-10-30", "2026-11-05"],
    "tags": [{"tag": "vidar", "count": 21, "previous": 0, "delta": 21, "pct": null, "tweets": 1, "previous_tweets": 0, "reporters": 1, "previous_reporters": 0}, "..."]
  },
  "tlds": {"window": "month", "domains_total": 2677, "top": [{"tld": "com", "count": 1451}, "..."], "other": 544},
  "novelty": {"window": "week", "distinct_values": 1203, "new": 1149, "recurring": 54, "pct_new": 95.5},
  "producers": {"window_7d": {"total": 1243, "active_producers": 54, "top": [{"user": "...", "count": 443, "share": 0.3564}, "..."]}}
}
```

- `daily`: column-oriented, 31 days: `dates`, `total` and each `types` entry are parallel arrays sharing one index - use for a rolling 30-day volume chart.
- `movers`: current vs previous 7-day tag counts, ranked by change magnitude - answers "what's spiking". Each `tags` row also carries `tweets`/`reporters` (distinct source tweets and reporting accounts behind `count`, counters only) and their `previous_*` twins.
- `tlds`: top TLDs among malicious domains from the last 30 days.
- `novelty`: the share of this week's distinct IOC values that are new versus recurring from a prior window.

Exact field names can shift slightly as the schema evolves - always inspect a live response rather than hardcoding the shape from this file.

## Human page

`https://tweetfeed.live/trends/` - charts the same data (daily volume, top movers, TLD breakdown, novelty rate) for a human reader.

## MCP equivalent

`get_trends` tool - no arguments, returns the same daily/movers/tlds/novelty structure.

## Gotchas

- This is aggregate/statistical data, not individual IOC rows - for a lookup of one specific value use the `tweetfeed-ioc-lookup` skill instead.
- `movers` and `novelty` are week-over-week comparisons; a tag with zero prior-week activity has `pct: null` (new tag) - sanity-check `previous` before reporting a percentage.
- Check `tweets` before calling a mover a trend: a big `delta` with `tweets: 1` is a single report (one post listing many IOCs), not broad activity.
- Regenerated with the rest of the feed (every 15 min), so `daily`'s most recent entry is a partial day until 00:00 UTC.

## License

CC0 1.0 Universal (public domain). No attribution required.

## Related pointers

- Single-IOC lookup: skill `tweetfeed-ioc-lookup`
- Campaign clustering (grouped by shared infrastructure, not just tag counts): skill `tweetfeed-campaigns`
- Source: `https://github.com/0xDanielLopez/TweetFeed`
