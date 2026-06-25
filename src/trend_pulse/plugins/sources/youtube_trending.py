"""YouTube Trending videos.

Primary: the official **YouTube Data API v3** ``videos.list?chart=mostPopular``
(free; needs a Google API key in ``YOUTUBE_API_KEY``). This is the only reliable
free path since Google deprecated the public ``/feed/trending`` page in 2025 —
scraping it now yields an empty ``richGridRenderer`` with zero videos.

Fallback (best-effort, usually empty now): scrape ``ytInitialData`` / InnerTube.
Get a free key at https://console.cloud.google.com → enable "YouTube Data API v3".
"""

from __future__ import annotations

import json
import os
import re

import httpx

from ...plugins.base import PluginSource
from ...sources.base import TrendItem


class YouTubeTrendingSource(PluginSource):
    name = "youtube_trending"
    description = "YouTube Trending - most popular videos by region (official Data API; set YOUTUBE_API_KEY)"
    requires_auth = False  # works without a key via fallback, but the key makes it reliable
    rate_limit = "10k quota units/day (Data API free tier)"
    category = "global"
    frequency = "daily"

    DATA_API_URL = "https://www.googleapis.com/youtube/v3/videos"
    INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/browse"
    INNERTUBE_KEY = os.environ.get("YOUTUBE_INNERTUBE_KEY", "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8")
    PAGE_URL = "https://www.youtube.com/feed/trending"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
    }

    # Data API accepts ISO 3166-1 alpha-2 region codes directly.
    _VALID_REGION = re.compile(r"^[A-Z]{2}$")

    def _region(self, geo: str) -> str:
        region = (geo or "US").upper()
        return region if self._VALID_REGION.match(region) else "US"

    async def fetch_trending(self, geo: str = "", count: int = 20) -> list[TrendItem]:
        region = self._region(geo)

        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if api_key:
            try:
                return await self._fetch_data_api(region, count, api_key)
            except Exception:
                pass  # fall through to best-effort scraping

        # Best-effort fallbacks (often empty since trending was deprecated).
        try:
            return await self._fetch_html(region, count)
        except Exception:
            pass
        try:
            return await self._fetch_innertube(region, count)
        except Exception:
            return []

    async def _fetch_data_api(self, region: str, count: int, api_key: str) -> list[TrendItem]:
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": max(1, min(count, 50)),
            "key": api_key,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self.DATA_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        items: list[TrendItem] = []
        for entry in data.get("items", []):
            snippet = entry.get("snippet", {})
            stats = entry.get("statistics", {})
            title = snippet.get("title", "")
            if not title:
                continue
            video_id = entry.get("id", "")
            views = int(stats.get("viewCount", 0) or 0)
            items.append(TrendItem(
                keyword=title,
                score=min(views / 1_000_000, 100),  # 100M views = 100
                source=self.name,
                url=f"https://youtube.com/watch?v={video_id}",
                traffic=f"{views:,} views" if views else "",
                category="video",
                published=snippet.get("publishedAt", ""),
                metadata={
                    "video_id": video_id,
                    "channel": snippet.get("channelTitle", ""),
                    "views": views,
                    "likes": int(stats.get("likeCount", 0) or 0),
                },
            ))
        return items

    async def _fetch_html(self, region: str, count: int) -> list[TrendItem]:
        params = {"gl": region} if region != "US" else {}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(self.PAGE_URL, params=params, headers=self.HEADERS)
            resp.raise_for_status()
            html = resp.text

        for marker in ("var ytInitialData = ", "ytInitialData = "):
            idx = html.find(marker)
            if idx != -1:
                start = html.find("{", idx)
                if start != -1:
                    try:
                        data, _ = json.JSONDecoder().raw_decode(html, start)
                        return self._parse(data, count)
                    except (ValueError, json.JSONDecodeError):
                        continue
        return []

    async def _fetch_innertube(self, region: str, count: int) -> list[TrendItem]:
        payload = {
            "browseId": "FEtrending",
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240101",
                    "hl": "en",
                    "gl": region,
                },
            },
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.post(
                self.INNERTUBE_URL,
                params={"key": self.INNERTUBE_KEY},
                json=payload,
                headers=self.HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        return self._parse(data, count)

    def _parse(self, data: dict, count: int) -> list[TrendItem]:
        """Walk the ytInitialData tree collecting any videoRenderer items."""
        items: list[TrendItem] = []

        def walk(node):
            if len(items) >= count:
                return
            if isinstance(node, dict):
                vr = node.get("videoRenderer")
                if isinstance(vr, dict):
                    self._append_video(vr, items)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(data)
        return items[:count]

    def _append_video(self, vr: dict, items: list[TrendItem]) -> None:
        video_id = vr.get("videoId", "")
        title = "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", []))
        if not title:
            return
        view_text = (
            vr.get("viewCountText", {}).get("simpleText", "")
            or vr.get("viewCountText", {}).get("runs", [{}])[0].get("text", "")
        )
        views = self._parse_views(view_text)
        channel_runs = vr.get("ownerText", {}).get("runs", [{}])
        channel = channel_runs[0].get("text", "") if channel_runs else ""
        items.append(TrendItem(
            keyword=title,
            score=min(views / 1_000_000, 100),
            source=self.name,
            url=f"https://youtube.com/watch?v={video_id}",
            traffic=view_text,
            category="video",
            metadata={"video_id": video_id, "channel": channel, "views": views},
        ))

    @staticmethod
    def _parse_views(text: str) -> float:
        text = text.replace(",", "").replace(" views", "").replace("次觀看", "").strip()
        try:
            if "M" in text or "百萬" in text:
                return float(re.sub(r"[^0-9.]", "", text)) * 1_000_000
            if "K" in text or "千" in text:
                return float(re.sub(r"[^0-9.]", "", text)) * 1_000
            if text:
                return float(re.sub(r"[^0-9.]", "", text))
        except ValueError:
            pass
        return 0.0


def register() -> YouTubeTrendingSource:
    return YouTubeTrendingSource()
