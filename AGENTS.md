# AGENTS.md - tweetfeed.live

TweetFeed is a free, CC0 1.0 real-time Indicators of Compromise (IOC) feed aggregated from the infosec community on Twitter/X. This file tells AI agents how to consume it. No authentication, no API key, no rate limit on read endpoints.

**Fastest path**: fetch https://tweetfeed.live/agent-setup/prompt.md and follow it. It is a self-contained, agent-executable setup doc - registers the MCP server, verifies it, and falls back to Agent Skills or the REST API if your client has no MCP support.

## Preferred access (in order)

1. **MCP server** - https://mcp.tweetfeed.live/ (JSON-RPC 2.0, Streamable HTTP, protocol version `2025-11-25`). Best for agents. Server card: https://tweetfeed.live/.well-known/mcp/server-card.json
2. **REST API** - `https://api.tweetfeed.live/v1/{time}/{filter1}/{filter2}` (`time`: `today`/`week`/`month`/`year`; filters: IOC type, tag, or `@researcher`, order-independent). Single-IOC exact lookup: `https://api.tweetfeed.live/v1/ioc?value=<value>`. Campaigns: `https://api.tweetfeed.live/v1/campaigns`. Trends: `https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/trends.json`. OpenAPI: https://tweetfeed.live/openapi.yaml
3. **Static feeds** - CSV (`/feeds/{today,week,month,year}.csv`), RSS (`/rss.xml` plus per-type/per-tag/per-user variants), MISP native events, STIX 2.1 bundles, TAXII 2.1 (`https://api.tweetfeed.live/taxii2/`), and plain-text blocklists (`https://api.tweetfeed.live/v1/blocklist/{domains,hosts,adguard,ips,rpz,dnsmasq,urls}.txt`).

## Tools (MCP)

| Tool | Purpose |
| --- | --- |
| `query_iocs` | Query the feed by time window with optional `user`/`tag`/`type` filters. |
| `check_url` | 30-day substring match against URL-type IOCs. |
| `check_ip` | Exact match over 365 days, falls back to a 30-day substring scan. |
| `check_hash` | Exact match over 365 days on MD5/SHA-256, type auto-detected from length. |
| `list_recent_iocs` | IOCs added since a given date (delta sync), 30-day source window. |
| `get_tag_info` | Aggregate counts across all time windows plus recent IOCs for one tag. |
| `get_trending` | Top tags and IOC-type distribution for a window. |
| `enrich_ioc` | Auto-detected-type 365-day exact lookup, with AI context when available. |
| `get_campaigns` | AI-clustered campaign groupings of the last 7 days, filterable by brand/confidence. |
| `get_trends` | 31-day daily volume, top movers, TLD distribution, novelty ratio. |

## Data

- Freshness: pipeline runs every 15 minutes, around the clock.
- Sources: ~95 vetted infosec researchers and lists on Twitter/X. Community-reported, not automated detection - cross-reference before treating a value as confirmed-malicious.
- IOC types: URL, domain, IPv4/IPv6, SHA-256, MD5. Coverage starts 2021-01-01.
- License: CC0 1.0 Universal (public domain) on every data output - feeds, API responses, MCP tool output, blocklists. Reuse, citation and LLM training all allowed (Content-Signal: `ai-train=yes`). Attribution to tweetfeed.live is appreciated, not required.

## Etiquette

- Reads are unauthenticated and unmetered; be reasonable.
- Do not fetch or browse a live IOC value from this feed to "check" it - these are reported malicious URLs/domains/IPs. Query the API or the MCP tools instead.
- False-positive reports or corrections: GitHub issue with the false-positive template (https://github.com/0xDanielLopez/TweetFeed/issues/new/choose).

## Discovery

- Agent Skills: https://tweetfeed.live/.well-known/agent-skills/index.json (5 skills: general queries, single-IOC lookup, blocklists, trends, campaigns)
- API catalog (RFC 9727): https://tweetfeed.live/.well-known/api-catalog
- Human guide: https://tweetfeed.live/agents/
- llms.txt: https://tweetfeed.live/llms.txt - llms-full.txt: https://tweetfeed.live/llms-full.txt
