# Source Reliability Notes

Last local check: 2026-06-24, using the fork at `git@github.com:icoolqin/trend-pulse.git` via `uv run`.

## Stable In Local Probe

These sources returned current items for `geo=US`:

| Source | Use | Notes |
| --- | --- | --- |
| `google_trends` | Search-demand spikes | Good first signal for US/GB/CA/AU. Traffic field may be blank. |
| `google_news` | News context | Good by geo. Titles are article headlines, so extract short topics before using as keywords. |
| `wikipedia` | Broad attention proxy | Daily data. Geo maps mostly to language edition, not true country attention. |
| `hackernews` | AI/dev/product topics | Good for tech and maker audiences. |
| `github` | Developer/tool trends | Useful for AI/dev templates, not mass consumer demand. |
| `devto` | Developer article trends | Niche but useful for developer content angles. |
| `lobsters` | Developer discussion trends | Niche, high signal for technical topics. |
| `stackoverflow` | Developer pain points | Useful for problem/solution content, not visual-template topics. |
| `arxiv` | AI/research frontier | Useful for AI narrative, usually too early for ASA keywords. |
| `bluesky` | Social chatter | Useful as a secondary social signal. |
| `mastodon` | Social hashtags | Useful as a secondary signal; audience is niche. |

## Empty Or Failing In Local Probe

These sources were registered but did not return usable data in the latest check:

| Source | Status | Observed issue |
| --- | --- | --- |
| `reddit` | error | HTTP 403 from `https://www.reddit.com/r/popular.json`. |
| `producthunt` | empty | No items returned. Verify parser or endpoint before relying on it. |
| `youtube_trending` | empty | No items returned for US/GB/CA/AU. Consider official YouTube Data API as a fallback. |
| `pinterest` | empty | No items returned for US/GB/CA/AU. Manual Pinterest Trends may still be valuable. |
| `tiktok_trending` | empty | No items returned for US/GB/CA/AU. Manual TikTok Creative Center may still be valuable. |

## Missing From Trend Pulse Today

These are important for app operations but are not built-in Trend Pulse sources yet:

| Source | Why it matters |
| --- | --- |
| Apple RSS Builder | Free App Store top charts by storefront, media type, genre, and feed format. |
| Apple Ads keyword tools | Closest source for ASA keyword suggestions and search popularity. |
| GDELT | Free global news/event monitoring with high volume and country/language filters. |
| Google Trends official API | Alpha/limited access; not generally available as a simple free API. |

## Geo Caveats

- `google_trends` and `google_news` are the strongest country-aware sources.
- `wikipedia` maps geo to language edition; `US`, `GB`, `CA`, and `AU` may all return `en.wikipedia`-based results.
- Many plugin/social/dev sources ignore `--geo` or only approximate geography.
- Always show source-level results when making operational decisions; do not rely only on the merged ranking.
