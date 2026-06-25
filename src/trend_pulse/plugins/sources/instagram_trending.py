"""Instagram trending (best-effort, login required).

Instagram has **no free, no-auth trending API** — the public web endpoints all
redirect to a login wall. This source is therefore best-effort:

* With a logged-in session cookie in ``INSTAGRAM_SESSIONID`` it queries the
  mobile "topical explore" feed and extracts trending hashtags from the top
  media. (Use a throwaway account; respect Instagram's ToS.)
* Without the cookie it returns ``[]`` cleanly — it never fabricates data.

This keeps Instagram wired into the pipeline so it "just works" the day a
session cookie (or a paid API) is supplied, without pretending to have data it
doesn't.
"""

from __future__ import annotations

import os
from collections import Counter

import httpx

from ...plugins.base import PluginSource
from ...sources.base import TrendItem

_EXPLORE_URL = "https://i.instagram.com/api/v1/discover/topical_explore/"
# Pinned app id from the Instagram web client; required by the mobile API.
_APP_ID = "936619743392459"


class InstagramTrendingSource(PluginSource):
    name = "instagram"
    description = "Instagram - trending hashtags from explore (best-effort; needs INSTAGRAM_SESSIONID)"
    requires_auth = True
    rate_limit = "low (login session required)"
    category = "social"
    frequency = "daily"
    difficulty = "high"

    async def fetch_trending(self, geo: str = "", count: int = 20) -> list[TrendItem]:
        session_id = os.environ.get("INSTAGRAM_SESSIONID", "").strip()
        if not session_id:
            # No free no-auth path — stay honest and return nothing.
            return []
        try:
            return await self._fetch_explore(session_id, count)
        except Exception:
            return []

    async def _fetch_explore(self, session_id: str, count: int) -> list[TrendItem]:
        headers = {
            "User-Agent": "Instagram 269.0.0.18.75 Android",
            "X-IG-App-ID": _APP_ID,
            "Accept": "application/json",
        }
        cookies = {"sessionid": session_id}
        async with httpx.AsyncClient(timeout=15, headers=headers, cookies=cookies) as client:
            resp = await client.get(_EXPLORE_URL, params={"is_prefetch": "false"})
            resp.raise_for_status()
            data = resp.json()

        # Tally hashtags across the explore grid; rank by frequency.
        tags: Counter[str] = Counter()
        for section in data.get("sectional_items", []) or []:
            for item in (section.get("layout_content", {}) or {}).get("medias", []) or []:
                media = item.get("media", {}) or {}
                caption = (media.get("caption") or {}).get("text", "") or ""
                for token in caption.split():
                    if token.startswith("#") and len(token) > 2:
                        tags[token.lower()] += 1

        items: list[TrendItem] = []
        for rank, (tag, freq) in enumerate(tags.most_common(count), start=1):
            items.append(TrendItem(
                keyword=tag,
                score=max(5.0, 100.0 - (rank - 1) * 3),
                source=self.name,
                url=f"https://www.instagram.com/explore/tags/{tag.lstrip('#')}/",
                traffic=f"{freq} posts in explore",
                category="social",
                metadata={"hashtag": tag.lstrip("#"), "rank": rank},
            ))
        return items


def register() -> InstagramTrendingSource:
    return InstagramTrendingSource()
