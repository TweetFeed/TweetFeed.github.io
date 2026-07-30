---
name: tweetfeed-blocklists
description: Fetch ready-made plain-text blocklists built from TweetFeed's rolling 30-day IOC window - domains, hosts-file, AdGuard Home, IPs, DNS RPZ, dnsmasq, and full URLs. Invoke when the user wants to import TweetFeed into Pi-hole, AdGuard Home, a firewall, DNS resolver or IDS without parsing JSON or CSV themselves. Rebuilt every 15 minutes, one indicator per line, CC0 licensed, no auth.
---

# TweetFeed Blocklists

Plain-text exports, one indicator per line, rolling 30-day window, rebuilt every 15 minutes. These are a 1:1 mirror of the feed with no additional quality gate beyond the standard pipeline - community-reported IOCs, use at your own risk. Base: `https://api.tweetfeed.live/v1/blocklist/`.

## Formats

| File | Format | Best for |
| --- | --- | --- |
| `domains.txt` | one domain per line | Pi-hole, generic DNS blocklists |
| `hosts.txt` | `0.0.0.0 domain` hosts-file syntax | `/etc/hosts`, hosts-file-based blockers |
| `adguard.txt` | `\|\|domain^` AdGuard syntax | AdGuard Home, uBlock-style filters |
| `ips.txt` | one IPv4 per line | firewalls, IDS/IPS deny rules |
| `rpz.txt` | DNS Response Policy Zone | BIND, Unbound, PowerDNS Recursor |
| `dnsmasq.txt` | `address=/domain/0.0.0.0` | dnsmasq |
| `urls.txt` | full URL per line (not just the host) | proxies, WAFs; covers IOCs on shared/legitimate infrastructure that DNS-level blocking can't safely reach |

## Fetch

```bash
curl -s https://api.tweetfeed.live/v1/blocklist/domains.txt
curl -s https://api.tweetfeed.live/v1/blocklist/hosts.txt
curl -s https://api.tweetfeed.live/v1/blocklist/adguard.txt
curl -s https://api.tweetfeed.live/v1/blocklist/ips.txt
curl -s https://api.tweetfeed.live/v1/blocklist/rpz.txt
curl -s https://api.tweetfeed.live/v1/blocklist/dnsmasq.txt
curl -s https://api.tweetfeed.live/v1/blocklist/urls.txt
```

Every response supports conditional requests (`ETag` / `Last-Modified`); send `If-None-Match` or `If-Modified-Since` on a repeat fetch to get a `304` with no body instead of re-downloading unchanged data.

## Why `urls.txt` is separate

Every other format is host-level (domain or IP), so it can only block a whole site. `urls.txt` carries the full path, which is the only way to block a phishing kit sitting on a compromised or shared host (Google Sites, GitHub Pages, cloud-storage buckets) where blocking the domain would take down legitimate content too.

## Gotchas

- These are a mirror of the raw 30-day feed, not a curated/deduplicated-against-false-positives list. Validate against VirusTotal or your own sandbox before blocking outright, same recommendation as the rest of the feed.
- 30-day window only. For longer history use the CSV feeds (`/feeds/`, up to 365 days) or the JSON API with a `year` time window.
- No per-type split beyond what's in the filename - `domains.txt` and `urls.txt` overlap conceptually (a URL implies a domain) but are generated independently, so diff them if you need to dedupe.

## MCP / API equivalents

There's no dedicated MCP tool for blocklists - use `query_iocs` with `type=domain` or `type=ip` and post-process, or fetch these files directly since they're already deduplicated plain text.

## License

CC0 1.0 Universal (public domain). No attribution required.

## Related pointers

- Human feeds page: `https://tweetfeed.live/feeds/#blocklist`
- General feed queries: skill `tweetfeed-iocs`
- Source: `https://github.com/0xDanielLopez/TweetFeed`
