# AGENTS.md - tweetfeed.live

TweetFeed is a free, CC0 1.0 real-time Indicators of Compromise (IOC) feed aggregated from the infosec community on Twitter/X. This file tells AI agents how to consume it. No authentication, no API key, no per-key quota. One zone-wide backstop applies: more than 50 requests per 10 seconds from a single IP to `api.tweetfeed.live`, `mcp.tweetfeed.live`, or the apex Worker paths (`/feeds/`, `/rss/`, `/rss.xml`, `/misp/`, `/stix/`, `/taxii2`) is blocked for 10 seconds. Stay under that and nothing else is metered.

**Fastest path**: fetch https://tweetfeed.live/agent-setup/prompt.md and follow it. It is a self-contained, agent-executable setup doc - registers the MCP server, verifies it, and falls back to Agent Skills or the REST API if your client has no MCP support.

## Preferred access (in order)

1. **MCP server** - https://mcp.tweetfeed.live/ (JSON-RPC 2.0, Streamable HTTP, protocol version `2025-11-25`). Best for agents. Server card: https://tweetfeed.live/.well-known/mcp/server-card.json
2. **REST API** - `https://api.tweetfeed.live/v1/{time}/{filter1}/{filter2}` (`time`: `today`/`week`/`month`/`year`; filters: IOC type, tag, or `@researcher`, order-independent). Single-IOC exact lookup: `https://api.tweetfeed.live/v1/ioc?value=<value>` (also checks the pre-365-day archive, optional `archive` block). Campaigns: `https://api.tweetfeed.live/v1/campaigns`. Complete campaign IOC set (uncapped, no MCP tool): `https://api.tweetfeed.live/v1/campaigns/iocs`. Trends: `https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/trends.json`, also API-fronted at `https://api.tweetfeed.live/v1/trends` (same document, ETag/304 support). Delta sync: `https://api.tweetfeed.live/v1/since/{ISO8601}` (also `/since/{ISO8601}/{filter1}/{filter2}`) - reaches back 30 days, not 365; page with `X-Result-Window-End` while `X-Result-Truncated` is present (the 10k-row LIMIT cut); a separate `X-Result-Window-Incomplete` means the requested `since` predates the 30-day source, not that there is a next page. Aggregate counts: `https://api.tweetfeed.live/v1/counts` (per-window totals plus type/tag breakdowns). Freshness/status: `https://api.tweetfeed.live/v1/status` (per-artifact freshness facts plus a per-request stale/fresh verdict, computed on every request, never cached). Manifest: `https://api.tweetfeed.live/v1/manifest` (every published artifact - size, row count, SHA-256, URLs). OpenAPI: https://tweetfeed.live/openapi.yaml
3. **Static feeds** - CSV (`/feeds/{today,week,month,year}.csv`), RSS (`/rss.xml` plus per-type/per-tag/per-user variants), MISP native events (`https://tweetfeed.live/misp` as the feed URL; MISP appends `/manifest.json` itself), STIX 2.1 bundles (`https://tweetfeed.live/stix/{today,week,month}.json` plus `manifest.json`; no `year` bundle by design), TAXII 2.1 (`https://api.tweetfeed.live/taxii2/`), and plain-text blocklists (`https://api.tweetfeed.live/v1/blocklist/{domains,hosts,adguard,ips,rpz,dnsmasq,urls,zeek-intel,wazuh-domains,wazuh-ips}.txt` - the last three carry no `#` header; check freshness via `/v1/manifest` or `Last-Modified`).

## Tools (MCP)

| Tool | Purpose |
| --- | --- |
| `query_iocs` | Query the feed by time window with optional `user`/`tag`/`type` filters. |
| `check_url` | 30-day substring match against URL-type IOCs. |
| `check_ip` | Exact match over 365 days, falls back to a 30-day substring scan; also flags pre-365-day archive hits. |
| `check_hash` | Exact match over 365 days on MD5/SHA-256, type auto-detected from length; also flags pre-365-day archive hits. |
| `list_recent_iocs` | IOCs added since a given date (delta sync), 30-day source window. |
| `get_tag_info` | Aggregate counts across all time windows plus recent IOCs for one tag. |
| `get_trending` | Top tags and IOC-type distribution for a window. |
| `enrich_ioc` | Auto-detected-type 365-day exact lookup, with AI context when available; also returns pre-365-day archive hits. |
| `get_campaigns` | AI-clustered campaign groupings of the last 30 days, filterable by brand/confidence; includes malware-family/threat-type rollups and an infra summary. |
| `get_trends` | 31-day daily volume, top movers, TLD distribution, novelty ratio. |

## Data

- Freshness: pipeline runs every 15 minutes, around the clock.
- Sources: ~95 vetted infosec researchers and lists on Twitter/X. Community-reported, not automated detection - cross-reference before treating a value as confirmed-malicious.
- IOC types: URL, domain, IPv4/IPv6, SHA-256, MD5. Coverage starts 2021-08-09 (`first_date` in https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/archive/meta.json).
- License: CC0 1.0 Universal (public domain) on every data output - feeds, API responses, MCP tool output, blocklists. Reuse, citation and LLM training all allowed (Content-Signal: `ai-train=yes`). Attribution to tweetfeed.live is appreciated, not required.

## Etiquette

- Reads are unauthenticated and unmetered per key; the only ceiling is the 50 req/10s per-IP backstop described above. Stay under it.
- Do not fetch or browse a live IOC value from this feed to "check" it - these are reported malicious URLs/domains/IPs. Query the API or the MCP tools instead.
- False-positive reports or corrections: GitHub issue via the feedback form (https://github.com/0xDanielLopez/TweetFeed/issues/new?template=feedback.yml), or use the prefilled false-positive template linked from each result on /search/.

## Discovery

- Agent Skills: https://tweetfeed.live/.well-known/agent-skills/index.json (5 skills: general queries, single-IOC lookup, blocklists, trends, campaigns)
- API catalog (RFC 9727): https://tweetfeed.live/.well-known/api-catalog
- Human guide: https://tweetfeed.live/agents/
- llms.txt: https://tweetfeed.live/llms.txt - llms-full.txt: https://tweetfeed.live/llms-full.txt
