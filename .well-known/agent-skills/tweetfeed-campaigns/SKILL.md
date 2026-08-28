---
name: tweetfeed-campaigns
description: Query TweetFeed's AI-clustered campaign groupings - related IOCs from a rolling 30-day window grouped by shared infrastructure (registered domain, cross-domain URL path patterns) or a shared specific tag, then named and described by an AI layer that never adds or removes IOCs. Invoke when the user asks "what phishing campaigns are active right now", "is this IOC part of a larger campaign", or wants IOCs grouped by threat instead of a flat time-windowed list.
---

# TweetFeed Campaigns

Daily job that clusters the last 30 days of community-reported IOCs into named campaigns. Clustering is two-stage: deterministic pre-grouping (shared registered domain, cross-domain URL path patterns, or a shared specific tag - generic tags like `#phishing`/`#malware` never cluster alone), then an AI layer names and describes each cluster. The AI only names/describes - it never adds or removes IOCs; every `iocs` entry in a campaign is verbatim from the feed.

```bash
curl -s https://api.tweetfeed.live/v1/campaigns | jq '.campaigns[] | {id, name, confidence, ioc_count}'
```

## Response shape

Top level: `version`, `generated_at`, `window` (`month`), `stale` / `stale_since`, `campaign_count`, `campaigns` (array).

Each campaign:

```json
{
  "id": "tfc-a1b2c3d4e5f6",
  "name": "...",
  "context": "...",
  "confidence": "high",
  "targeted_brand": "...",
  "targeted_sector": "...",
  "targeted_country": "...",
  "ttps": ["..."],
  "first_seen": "...",
  "last_seen": "...",
  "ioc_count": 0,
  "ioc_count_1d": 0,
  "ioc_count_7d": 0,
  "ioc_count_30d": 0,
  "types": {"url": 0, "domain": 0, "ip": 0, "sha256": 0, "md5": 0},
  "tags": ["..."],
  "reporters": ["..."],
  "iocs": [ /* up to 25 sample rows, same shape as the main feed */ ],
  "member_cluster_ids": ["..."],
  "anchors": {"registered_domains": ["..."], "url_path_patterns": ["..."], "tags": ["..."]}
}
```

`confidence` is `high` / `medium` / `low`. `targeted_brand` is present only when one was identified. `targeted_sector` (STIX 2.1 `industry-sector-ov` slug, e.g. `financial-services`) and `targeted_country` (ISO 3166-1 alpha-2, e.g. `BR`) are AI-inferred the same way and may be `null`. `ttps` is a JSON array of 0 to 4 MITRE ATT&CK Enterprise technique ids (e.g. `T1566.002`), AI-inferred from the clustered IOCs - infrastructure-only, not attribution. Always an array, never `null`; may be an empty array, and may be absent entirely on an older cached document. `iocs` is capped at 25 sample rows per campaign even if the cluster has more members.

`ioc_count_1d`/`ioc_count_7d`/`ioc_count_30d` are optional ints: IOCs seen in the last 1/7/30 days respectively (`ioc_count` stays the total across the full window, unchanged). They may be absent on older documents - treat a missing `ioc_count_7d` as "currently active" rather than as zero. `ioc_count_7d > 0` is what identifies a campaign as currently active; the human page at `/campaigns/` uses exactly that check to default to "active this week" and hide campaigns that have gone quiet.

## Staleness

Regenerated daily. If a run fails, `stale` is `true` and `stale_since` holds the date of the last successful run - the document falls back to that previous snapshot rather than going empty. Always check `stale` before treating `generated_at` as current.

## Filtering

No server-side filter parameters on the raw endpoint - fetch the full array and filter client-side, e.g. with `jq`:

```bash
curl -s https://api.tweetfeed.live/v1/campaigns | jq '.campaigns[] | select(.confidence == "high")'
curl -s https://api.tweetfeed.live/v1/campaigns | jq '.campaigns[] | select(.targeted_brand | test("microsoft"; "i"))'
```

## Human page

`https://tweetfeed.live/campaigns/`

## MCP equivalent

`get_campaigns` tool - optional `brand` (substring match on `targeted_brand`), `min_confidence` (`low`/`medium`/`high`), `limit` (1-50, default 20). Same trimmed-sample shape as the raw endpoint.

## Gotchas

- This is not attribution - "campaign" here means shared infrastructure or tag, not a claim about who operates it.
- 30-day rolling window only; older activity isn't clustered even if it's still in the raw IOC feed.
- `iocs` samples cap at 25 - for the full membership of a cluster you only get what's sampled, not a guaranteed complete list.

## License

CC0 1.0 Universal (public domain) on the IOC data; the AI-generated `name`/`context` fields are released under the same terms.

## Related pointers

- Trend analytics (aggregate, not clustered by campaign): skill `tweetfeed-trends`
- Single-IOC lookup: skill `tweetfeed-ioc-lookup`
- Source: `https://github.com/0xDanielLopez/TweetFeed`
