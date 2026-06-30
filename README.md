# TweetFeed.github.io

Static frontend for [tweetfeed.live](https://tweetfeed.live) - a public feed of
Indicators of Compromise (URLs, domains, IPs, SHA256/MD5 hashes) shared by the
infosec community on Twitter/X, aggregated every 15 minutes.

- **Live site:** https://tweetfeed.live
- **Data repository (the feed itself):** https://github.com/0xDanielLopez/TweetFeed
- **API:** https://api.tweetfeed.live
- **Terms of Service:** https://tweetfeed.live/tos/
- **Feedback:** https://tweetfeed.featurebase.app

This repo is served by GitHub Pages behind Cloudflare. It contains only the
website (HTML/CSS/JS); the IOC data lives in the data repository above and is
fetched client-side and via the API Worker.

## Licensing

- **Website code:** MIT (based on the [SB Admin 2](https://startbootstrap.com/theme/sb-admin-2) theme).
- **IOC data:** [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) - no rights reserved.
