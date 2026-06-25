"""Pinterest Trends (free, no auth).

Uses the same public JSON endpoints that https://trends.pinterest.com calls:

* ``/latest_available_date/`` → the most recent data date.
* ``/top_trends_filtered/?lookbackWindow=2&endDate=<date>&rankingMethod=3&country=<CC>``
  → the ranked trending search terms (country-aware).

These return clean JSON to a plain HTTP client (no token / no browser needed).
Trending terms here are highly visual/aesthetic (nail art, wallpapers, hairstyles,
outfit ideas …), which map well to Wondershot's creative-camera templates.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ...plugins.base import PluginSource
from ...sources.base import TrendItem


class PinterestSource(PluginSource):
    name = "pinterest"
    description = "Pinterest Trends - country-aware trending search terms (visual/aesthetic)"
    requires_auth = False
    rate_limit = "moderate"
    category = "social"
    frequency = "daily"
    difficulty = "low"

    BASE = "https://trends.pinterest.com"
    DATE_URL = f"{BASE}/latest_available_date/"
    TRENDS_URL = f"{BASE}/top_trends_filtered/"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://trends.pinterest.com/",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Pinterest Trends supports these country codes; everything else falls back to US.
    _COUNTRIES = {"US", "GB", "CA", "AU", "DE", "FR", "IT", "ES", "BR", "MX", "JP"}

    def _country(self, geo: str) -> str:
        cc = (geo or "US").upper()
        return cc if cc in self._COUNTRIES else "US"

    async def fetch_trending(self, geo: str = "", count: int = 20) -> list[TrendItem]:
        country = self._country(geo)
        async with httpx.AsyncClient(timeout=15, headers=self.HEADERS, follow_redirects=True) as client:
            end_date = await self._latest_date(client)
            resp = await client.get(
                self.TRENDS_URL,
                params={
                    "lookbackWindow": 2,
                    "endDate": end_date,
                    "rankingMethod": 3,
                    "country": country,
                },
            )
            resp.raise_for_status()
            values = resp.json().get("values", [])

        items: list[TrendItem] = []
        for i, entry in enumerate(values[:count]):
            term = (entry.get("term") or "").strip()
            if not term:
                continue
            normalized = entry.get("normalizedCount")
            search_count = entry.get("searchCount")
            # normalizedCount is ~0-100; fall back to rank-based score.
            score = float(normalized) if isinstance(normalized, (int, float)) else max(10.0, 100.0 - i * 4)
            wow = (entry.get("wow_change") or {}).get("value")
            items.append(TrendItem(
                keyword=term,
                score=min(score, 100.0),
                source=self.name,
                url=f"https://www.pinterest.com/search/pins/?q={term.replace(' ', '%20')}",
                traffic=f"index {search_count}" if search_count is not None else "",
                category="visual",
                metadata={
                    "country": country,
                    "normalized_count": normalized,
                    "search_count": search_count,
                    "wow_change": wow,
                    "rank": i + 1,
                },
            ))
        return items

    async def _latest_date(self, client: httpx.AsyncClient) -> str:
        try:
            resp = await client.get(self.DATE_URL)
            resp.raise_for_status()
            date = resp.json().get("date")
            if date:
                return date
        except Exception:
            pass
        # Fallback: a few days back (Pinterest data lags ~3-5 days).
        return (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%d")

    async def search(self, query: str, geo: str = "") -> list[TrendItem]:
        return []


def register() -> PinterestSource:
    return PinterestSource()
