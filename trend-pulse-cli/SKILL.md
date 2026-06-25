---
name: trend-pulse-cli
description: Operate the Trend Pulse CLI for live trend collection, source health checks, and daily hot-topic candidate exports for app marketing, template ideation, social posts, ASO, and Apple Search Ads workflows. Use when Codex needs to run trend-pulse commands, choose reliable trend sources, inspect source failures, or generate a daily table with hot_topic, source, country, template_idea, video_hook, ASA_keywords, and confidence.
---

# Trend Pulse CLI

## Quick Start

Run from the local `trend-pulse` repository when possible so edits in the fork are used:

```bash
uv run trend-pulse sources
uv run trend-pulse trending --sources google_trends,google_news,wikipedia --geo US --count 20
uv run trend-pulse search "AI photo template" --sources google_trends,hackernews,github --geo US
uv run trend-pulse snapshot --sources google_trends,google_news,wikipedia --geo US --count 50
```

If the repo is not available, use the published package:

```bash
uvx trend-pulse sources
uvx trend-pulse trending --sources google_trends,google_news,wikipedia --geo US --count 20
```

## Commands

- `sources`: list registered built-in and plugin sources.
- `trending`: fetch current items. Use `--sources`, `--geo`, and `--count`.
- `search`: search source-specific indexes where implemented.
- `snapshot`: fetch and save current data into the local history DB.
- `history`: query saved snapshots for a keyword.

Use comma-separated source names with no spaces:

```bash
uv run trend-pulse trending -s google_trends,google_news,hackernews -g GB -n 10
```

## Daily Hot-Topic Workflow

1. Verify the source registry:

```bash
uv run trend-pulse sources
```

2. Probe reliable market sources by bucket, not only the merged ranking. The merged list can be biased toward sources with numeric scores such as Wikipedia.

```bash
uv run trend-pulse trending -s google_trends -g US -n 25
uv run trend-pulse trending -s google_news -g US -n 25
uv run trend-pulse trending -s wikipedia -g US -n 25
uv run trend-pulse trending -s hackernews,github,devto,lobsters -g US -n 20
```

3. Repeat market probes for the priority App Store regions:

```bash
for geo in US GB CA AU DE FR IT ES NL SE IE CH; do
  uv run trend-pulse trending -s google_trends,google_news -g "$geo" -n 10
done
```

4. Convert candidates into the operating table:

```text
hot_topic | source | country | why_now | template_idea | video_hook | ASA_keywords | confidence
```

5. Prefer topics that satisfy all three conditions:

- Recent search/news/social attention.
- Clear "make a template / post this / customize this" user action.
- Plausible App Store keyword intent for ASA or ASO.

## Source Selection

For Wondershot-style template and social operations, start with:

```text
google_trends, google_news, wikipedia, hackernews, github, devto, lobsters, bluesky, mastodon
```

Treat these as opportunistic until re-verified:

```text
reddit, producthunt, youtube_trending, pinterest, tiktok_trending
```

Read `references/source-reliability.md` when deciding which sources to trust or when explaining empty/error results.

## Output Guidance

When presenting results, separate:

- `stable`: source returned current items.
- `empty`: source ran but returned no items.
- `error`: source failed, include the exception or HTTP status.
- `missing`: source is not implemented in Trend Pulse.

For app operations, add two extra columns beyond raw trend data:

- `template_fit`: whether the topic can become a user-facing template.
- `asa_intent`: likely App Store search terms derived from the topic.

Do not imply that Trend Pulse contains Apple App Store RSS, Apple Ads keyword popularity, or GDELT unless those sources have been added to the fork. Use those as external complements.
