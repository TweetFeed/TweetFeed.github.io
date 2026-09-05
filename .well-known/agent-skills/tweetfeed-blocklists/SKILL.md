---
name: tweetfeed-blocklists
description: Fetch ready-made plain-text blocklists built from TweetFeed's rolling 30-day IOC window - domains, hosts-file, AdGuard Home, IPs, DNS RPZ, dnsmasq, full URLs, a Zeek Intelligence Framework file, and Wazuh CDB lists for domains and IPs. Invoke when the user wants to import TweetFeed into Pi-hole, AdGuard Home, a firewall, DNS resolver, Zeek or Wazuh without parsing JSON or CSV themselves. Rebuilt every 15 minutes, one indicator per line, CC0 licensed, no auth.
---

# TweetFeed Blocklists

Plain-text exports, one indicator per line (the Zeek file adds two metadata columns), rolling 30-day window, rebuilt every 15 minutes. These are a 1:1 mirror of the feed with no additional quality gate beyond the standard pipeline - community-reported IOCs, use at your own risk. Base: `https://api.tweetfeed.live/v1/blocklist/`.

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
| `zeek-intel.txt` | Zeek Intelligence Framework: `#fields\tindicator\tindicator_type\tmeta.source` header, then rows only (no other comments) | Zeek, via `redef Intel::read_files` |
| `wazuh-domains.txt` | `key:tweetfeed` per line, no header | Wazuh rule with `lookup="match_key"` |
| `wazuh-ips.txt` | `key:tweetfeed` per line (IPv6 keys double-quoted, CIDR omitted), no header | Wazuh rule with `lookup="address_match_key"` on `srcip`/`dstip` |

## Fetch

```bash
curl -s https://api.tweetfeed.live/v1/blocklist/domains.txt
curl -s https://api.tweetfeed.live/v1/blocklist/hosts.txt
curl -s https://api.tweetfeed.live/v1/blocklist/adguard.txt
curl -s https://api.tweetfeed.live/v1/blocklist/ips.txt
curl -s https://api.tweetfeed.live/v1/blocklist/rpz.txt
curl -s https://api.tweetfeed.live/v1/blocklist/dnsmasq.txt
curl -s https://api.tweetfeed.live/v1/blocklist/urls.txt
curl -s https://api.tweetfeed.live/v1/blocklist/zeek-intel.txt
curl -s https://api.tweetfeed.live/v1/blocklist/wazuh-domains.txt
curl -s https://api.tweetfeed.live/v1/blocklist/wazuh-ips.txt
```

Every response supports conditional requests (`ETag` / `Last-Modified`); send `If-None-Match` or `If-Modified-Since` on a repeat fetch to get a `304` with no body instead of re-downloading unchanged data.

## Why `urls.txt` is separate

Every other flat list is host-level (domain or IP), so it can only block a whole site (`zeek-intel.txt` carries URL indicators too, but as Zeek intel rather than a blocklist). `urls.txt` carries the full path, which is the only way to block a phishing kit sitting on a compromised or shared host (Google Sites, GitHub Pages, cloud-storage buckets) where blocking the domain would take down legitimate content too.

## Gotchas

- These are a mirror of the raw 30-day feed, not a curated/deduplicated-against-false-positives list. Validate against VirusTotal or your own sandbox before blocking outright, same recommendation as the rest of the feed.
- 30-day window only. For longer history use the CSV feeds (`/feeds/`, up to 365 days) or the JSON API with a `year` time window.
- No per-type split beyond what's in the filename - `domains.txt` and `urls.txt` overlap conceptually (a URL implies a domain) but are generated independently, so diff them if you need to dedupe.
- `zeek-intel.txt`, `wazuh-domains.txt` and `wazuh-ips.txt` carry no `#` comment header - `zeek-intel.txt` opens with a single `#fields` line instead, and the two Wazuh files have no header at all, since a `#` would compile as a literal CDB key. Check freshness for these three via `/v1/manifest` or the response's `Last-Modified` header, not a header comment.
- Zeek: `redef Intel::read_files += { "/opt/zeek/share/zeek/site/zeek-intel.txt" };` and refresh by curling to a temp file then `mv` into place - Zeek's `Input::REREAD` watches the path, not the file descriptor, so an in-place write can be read half-finished.
- Wazuh does not fetch remotely - cron a daily pull: `curl -sfL https://api.tweetfeed.live/v1/blocklist/wazuh-domains.txt -o /var/ossec/etc/lists/tweetfeed-domains` (same pattern for `wazuh-ips.txt` under another list name), declare `<list>etc/lists/tweetfeed-domains</list>` inside `<ruleset>` in `ossec.conf`, then `systemctl restart wazuh-manager` - CDB lists are rebuilt only at start. Rules read them with `<list field="..." lookup="match_key">etc/lists/tweetfeed-domains</list>`; for the IPs list use `lookup="address_match_key"` on `srcip`/`dstip`.
- Palo Alto Networks PAN-OS: no dedicated export - point a Domain EDL at `domains.txt` (tick "Automatically expand to include subdomains", Hourly refresh) and an IP EDL at `ips.txt`. Do not use `urls.txt` as a URL EDL: PAN-OS reads `? & = ; +` as token separators, which breaks full-path indicators.

## MCP / API equivalents

There's no dedicated MCP tool for blocklists - use `query_iocs` with `type=domain` or `type=ip` and post-process, or fetch these files directly since they're already deduplicated plain text.

## License

CC0 1.0 Universal (public domain). No attribution required.

## Related pointers

- Human feeds page: `https://tweetfeed.live/feeds/#blocklist`
- General feed queries: skill `tweetfeed-iocs`
- Source: `https://github.com/0xDanielLopez/TweetFeed`
