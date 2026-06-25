"""TikTok trending hashtags from Creative Center (free, no auth).

The Creative Center trends page (https://ads.tiktok.com/creative/creativeCenter/trends/hashtag)
is a Remix app that ships its initial data in an SSR "loader" response:

    GET .../trends/hashtag?__loader=creativeCenter/trends/(tab)/page&__ssrDirect=true

That JSON embeds a TanStack-Query ``dehydratedState`` whose
``['popular','hashtags',…]`` query holds the trending hashtags — reachable with a
plain HTTP client (no signed token / no browser). Note the free SSR feed only
exposes a handful of "breakout" hashtags (the full grid needs an ads login), so
expect a short but real list. The old signed ``creative_radar_api`` is kept as a
best-effort fallback.
"""

from __future__ import annotations

import json

import httpx

from ...plugins.base import PluginSource
from ...sources.base import TrendItem


class TikTokTrendingSource(PluginSource):
    name = "tiktok_trending"
    description = "TikTok Creative Center - trending/breakout hashtags (SSR loader, no auth)"
    requires_auth = False
    rate_limit = "moderate"
    category = "social"
    frequency = "realtime"
    difficulty = "medium"

    LOADER_URL = "https://ads.tiktok.com/creative/creativeCenter/trends/hashtag"
    LOADER_PARAMS = {"__loader": "creativeCenter/trends/(tab)/page", "__ssrDirect": "true"}
    API_URL = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
    }

    async def fetch_trending(self, geo: str = "", count: int = 20) -> list[TrendItem]:
        try:
            items = await self._fetch_ssr_loader(count)
            if items:
                return items
        except Exception:
            pass
        # Best-effort fallback: the old signed API (usually returns 40101 without a token).
        try:
            return await self._fetch_api(geo, count)
        except Exception:
            return []

    async def _fetch_ssr_loader(self, count: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=self.HEADERS) as client:
            resp = await client.get(self.LOADER_URL, params=self.LOADER_PARAMS)
            resp.raise_for_status()
            data = resp.json()

        # Find the dehydrated query that holds the hashtag list.
        hashtags = []
        for query in data.get("dehydratedState", {}).get("queries", []):
            if "hashtag" not in json.dumps(query.get("queryKey", "")).lower():
                continue
            pages = (query.get("state", {}).get("data", {}) or {}).get("pages", [])
            for page in pages:
                rows = page.get("data") if isinstance(page, dict) else None
                if isinstance(rows, list):
                    hashtags.extend(rows)
        return self._parse_hashtags(hashtags, count)

    def _parse_hashtags(self, hashtags: list, count: int) -> list[TrendItem]:
        items: list[TrendItem] = []
        for rank, tag in enumerate(hashtags[:count], start=1):
            if not isinstance(tag, dict):
                continue
            name = tag.get("hashtagName") or tag.get("hashtag_name") or tag.get("name") or ""
            if not name:
                continue
            posts = int(tag.get("publishCnt") or tag.get("post_num") or tag.get("video_count") or 0)
            keyword = name if name.startswith("#") else f"#{name}"
            items.append(TrendItem(
                keyword=keyword,
                score=max(5.0, 100.0 - (rank - 1) * 5),
                source=self.name,
                url=f"https://www.tiktok.com/tag/{name.lstrip('#')}",
                traffic=f"{posts:,} posts" if posts else "",
                category="social",
                metadata={"hashtag": name.lstrip("#"), "post_count": posts, "rank": rank},
            ))
        return items

    async def _fetch_api(self, geo: str, count: int) -> list[TrendItem]:
        region = (geo or "US").upper()
        params = {"period": 7, "country_code": region, "page_size": count, "page": 1, "sort_by": "popular"}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=self.HEADERS) as client:
            resp = await client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        rows = data.get("data", {}).get("list", []) or data.get("list", [])
        # Normalize to the same shape _parse_hashtags expects.
        norm = [{"hashtagName": r.get("hashtag_name") or r.get("name", ""), "publishCnt": r.get("post_num", 0)} for r in rows]
        return self._parse_hashtags(norm, count)


def register() -> TikTokTrendingSource:
    return TikTokTrendingSource()
