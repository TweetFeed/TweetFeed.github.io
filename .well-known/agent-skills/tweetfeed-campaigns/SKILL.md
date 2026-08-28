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
  "activity": {"2026-08-14": 205, "2026-08-19": 202},
  "types": {"url": 0, "domain": 0, "ip": 0, "sha256": 0, "md5": 0},
  "enriched_count": 0,
  "threat_types": {"phishing": 172, "cryptoscam": 100, "malware": 51, "c2": 25},
  "families": {"Joker": 10, "sliver": 5},
  "infra": [{"org": "AS13335 Cloudflare, Inc.", "ip_count": 3, "country": "US"}],
  "tags": ["..."],
  "reporters": ["..."],
  "iocs": [ /* stratified 25-row sample, same shape as the main feed - see Gotchas */ ],
  "member_cluster_ids": ["..."],
  "anchors": {"registered_domains": ["..."], "url_path_patterns": ["..."], "tags": ["..."]}
}
```

`confidence` is `high` / `medium` / `low`. `targeted_brand` is present only when one was identified. `targeted_sector` (STIX 2.1 `industry-sector-ov` slug, e.g. `financial-services`) and `targeted_country` (ISO 3166-1 alpha-2, e.g. `BR`) are AI-inferred the same way and may be `null`. `ttps` is a JSON array of 0 to 4 MITRE ATT&CK Enterprise technique ids (e.g. `T1566.002`), AI-inferred from the clustered IOCs - infrastructure-only, not attribution. Always an array, never `null`; may be an empty array, and may be absent entirely on an older cached document. `iocs` is capped at 25 sample rows per campaign even if the cluster has more members (see Gotchas for how to get the rest).

`ioc_count_1d`/`ioc_count_7d`/`ioc_count_30d` are optional ints: IOCs seen in the last 1/7/30 days respectively (`ioc_count` stays the total across the full window, unchanged). They may be absent on older documents - treat a missing `ioc_count_7d` as "currently active" rather than as zero. `ioc_count_7d > 0` is what identifies a campaign as currently active; the human page at `/campaigns/` uses exactly that check to default to "active this week" and hide campaigns that have gone quiet.

`activity`, `enriched_count`, `threat_types`, `families` and `infra` are newer optional fields; like `ttps` and the `ioc_count_*d` fields, they may be absent entirely on an older cached or stale-fallback document. `activity` is a sparse per-day IOC histogram with chronologically sorted keys, counting every row in the campaign, not just the published `iocs` sample. `enriched_count` is an int: how many of the campaign's IOCs have an AI enrichment entry. It is the denominator for `threat_types` and `families` below - without it, those two rollups look like they cover the whole campaign when they only cover the enriched subset. `threat_types` (e.g. `{"phishing": 172, "cryptoscam": 100}`) and `families` (malware family, e.g. `{"Joker": 10}`) are rollups over the full campaign membership, not just the sample; `families` is usually empty or absent since family attribution is sparse. `infra` is present only when the campaign has at least one `ip`-type IOC: an array of `{"org", "ip_count", "country"}`, sorted by `ip_count` descending. The ASN is embedded in `org` (e.g. `"AS13335 Cloudflare, Inc."`) - there is no separate `asn` field.

Each `iocs` row may also carry two optional fields mirroring the same-named objects `GET /v1/ioc/<value>` returns: `ai` (`{"threat_type": "phishing", "family": "Joker"}`, `family` omitted when unknown, the whole object omitted when the IOC has no enrichment) and `net` (`{"org": "...", "country": "..."}`, `ip`-type IOCs only).

## Staleness

Regenerated daily. If a run fails, `stale` is `true` and `stale_since` holds the date of the last successful run - the document falls back to that previous snapshot rather than going empty. Always check `stale` before treating `generated_at` as current.

## Filtering

No server-side filter parameters on the raw endpoint - fetch the full array and filter client-side, e.g. with `jq`:

```bash
curl -s https://api.tweetfeed.live/v1/campaigns | jq '.campaigns[] | select(.confidence == "high")'
curl -s https://api.tweetfeed.live/v1/campaigns | jq '.campaigns[] | select(.targeted_brand | test("microsoft"; "i"))'
```

## Complete IOC membership

`iocs` on the main endpoint is a stratified 25-row sample per campaign. For the full, uncapped membership of every campaign in the current document:

```bash
curl -s https://api.tweetfeed.live/v1/campaigns/iocs | jq '.campaigns["tfc-a1b2c3d4e5f6"]'
```

Shape: `{"version": 1, "generated_at": "...", "campaigns": {"<campaign id>": [ <full IOC rows> ], ...}}`. Rows carry the same six fields as the inline `iocs` sample, including the optional `ai`/`net` fields. `generated_at` matches the main `/v1/campaigns` document - compare the two and fall back to the inline sample on a mismatch. ~231 KB uncapped. Same cache policy as `/v1/campaigns`: `max-age=60, stale-while-revalidate=600, stale-if-error=86400`.

No MCP tool wraps this endpoint - a 231 KB document doesn't fit a tool response. Fetch it directly with `curl`/`fetch` if you need full membership.

## Human page

`https://tweetfeed.live/campaigns/`

## MCP equivalent

`get_campaigns` tool - optional `brand` (substring match on `targeted_brand`), `min_confidence` (`low`/`medium`/`high`), `limit` (1-50, default 20). Same trimmed-sample shape as the raw endpoint, and ships `families`/`threat_types`/`enriched_count`/`infra` per campaign, but drops `activity` (token economy - `ioc_count_1d`/`_7d`/`_30d` already answer "how recent").

## Gotchas

- This is not attribution - "campaign" here means shared infrastructure or tag, not a claim about who operates it.
- 30-day rolling window only; older activity isn't clustered even if it's still in the raw IOC feed.
- The inline `iocs` array is a stratified sample (across sub-clusters and eTLD+1 buckets, not just the newest 25) capped at 25 rows - not a guaranteed complete list. For the complete IOC set of every campaign, use `GET https://api.tweetfeed.live/v1/campaigns/iocs` (see above).

## License

CC0 1.0 Universal (public domain) on the IOC data; the AI-generated `name`/`context` fields are released under the same terms.

## Related pointers

- Trend analytics (aggregate, not clustered by campaign): skill `tweetfeed-trends`
- Single-IOC lookup: skill `tweetfeed-ioc-lookup`
- Source: `https://github.com/0xDanielLopez/TweetFeed`
