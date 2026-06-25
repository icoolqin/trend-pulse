"""Reddit popular posts.

Two paths, picked automatically:

1. **Official Data API (preferred)** — if ``REDDIT_CLIENT_ID`` + ``REDDIT_CLIENT_SECRET``
   are set, use app-only OAuth (``client_credentials``) against ``oauth.reddit.com``.
   This returns real upvote scores and has a generous authenticated rate limit, so
   it never hits the 403/429 the public endpoints now throw. Register a free app at
   https://www.reddit.com/prefs/apps (type "script" or "web app").

2. **Public Atom feed (fallback)** — ``/r/popular/.rss``. No auth, but no upvote
   counts (ranked by feed order) and it rate-limits rapid repeat hits.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx

from .base import TrendSource, TrendItem

_ATOM = "{http://www.w3.org/2005/Atom}"
_LINK_RE = re.compile(r'<span><a href="([^"]+)">\[link\]</a>')


class RedditSource(TrendSource):
    name = "reddit"
    description = "Reddit - popular posts (official Data API if creds set, else public Atom feed)"
    requires_auth = False  # works without auth via RSS; creds make it more reliable
    rate_limit = "100 req/min (OAuth) or moderate (Atom feed)"

    FEED_URL = "https://www.reddit.com/r/popular/.rss"
    SEARCH_URL = "https://www.reddit.com/search.rss"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    OAUTH_BASE = "https://oauth.reddit.com"
    USER_AGENT = os.environ.get(
        "REDDIT_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    HEADERS = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self) -> None:
        self._client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
        self._client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
        self._token = ""
        self._token_expiry = 0.0

    # ---- Official Data API (OAuth) ----
    async def _get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        resp = await client.post(
            self.TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
            headers={"User-Agent": self.USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def _parse_listing(self, data: dict) -> list[TrendItem]:
        items: list[TrendItem] = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            if not title:
                continue
            upvotes = post.get("score", 0) or 0
            items.append(TrendItem(
                keyword=title,
                score=min(upvotes / 500, 100),  # 50K upvotes ≈ 100
                source=self.name,
                url=f'https://reddit.com{post.get("permalink", "")}',
                traffic=f"{upvotes} upvotes",
                category="general",
                published=datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc).isoformat(),
                metadata={
                    "subreddit": post.get("subreddit", ""),
                    "author": post.get("author", ""),
                    "comments": post.get("num_comments", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                    "outbound_url": "" if post.get("is_self") else post.get("url", ""),
                },
            ))
        return items

    async def _fetch_oauth(self, path: str, params: dict, count: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            token = await self._get_token(client)
            resp = await client.get(
                f"{self.OAUTH_BASE}{path}",
                params={**params, "limit": count, "raw_json": 1},
                headers={"Authorization": f"Bearer {token}", "User-Agent": self.USER_AGENT},
            )
            resp.raise_for_status()
            return self._parse_listing(resp.json())

    # ---- Public Atom feed (fallback) ----
    def _parse_feed(self, xml_text: str, count: int) -> list[TrendItem]:
        items: list[TrendItem] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return items

        for entry in root.findall(f"{_ATOM}entry"):
            title = (entry.findtext(f"{_ATOM}title") or "").strip()
            if not title:
                continue
            permalink = ""
            for link in entry.findall(f"{_ATOM}link"):
                href = link.get("href", "")
                if href and (link.get("rel") in (None, "alternate")):
                    permalink = href
                    break
            subreddit = ""
            category = entry.find(f"{_ATOM}category")
            if category is not None:
                subreddit = (category.get("label") or category.get("term") or "").strip()
            author = entry.findtext(f"{_ATOM}author/{_ATOM}name") or ""
            updated = entry.findtext(f"{_ATOM}updated") or ""
            content = entry.findtext(f"{_ATOM}content") or ""
            outbound = ""
            m = _LINK_RE.search(content)
            if m:
                outbound = m.group(1)
            rank = len(items) + 1
            items.append(TrendItem(
                keyword=title,
                score=max(5.0, 100.0 - (rank - 1) * 2),
                source=self.name,
                url=permalink or outbound,
                traffic=subreddit,
                category="general",
                published=updated,
                metadata={
                    "subreddit": subreddit,
                    "author": author.lstrip("/").removeprefix("u/"),
                    "outbound_url": outbound,
                    "rank": rank,
                },
            ))
            if len(items) >= count:
                break
        return items

    async def _fetch_feed(self, url: str, params: dict, count: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=self.HEADERS)
            if resp.status_code == 429:  # rapid repeat hits get throttled; back off once
                await asyncio.sleep(2.0)
                resp = await client.get(url, params=params, headers=self.HEADERS)
            resp.raise_for_status()
            return self._parse_feed(resp.text, count)

    # ---- Public entrypoints ----
    async def fetch_trending(self, geo: str = "", count: int = 20) -> list[TrendItem]:
        geo_params = {"geo_filter": geo.upper()} if geo else {}
        if self._client_id and self._client_secret:
            try:
                return await self._fetch_oauth("/r/popular/hot", geo_params, count)
            except Exception:
                pass  # fall back to the public feed
        return await self._fetch_feed(self.FEED_URL, geo_params, count)

    async def search(self, query: str, geo: str = "") -> list[TrendItem]:
        if self._client_id and self._client_secret:
            try:
                return await self._fetch_oauth(
                    "/search", {"q": query, "sort": "relevance", "type": "link"}, 25
                )
            except Exception:
                pass
        return await self._fetch_feed(self.SEARCH_URL, {"q": query, "sort": "relevance"}, 25)
