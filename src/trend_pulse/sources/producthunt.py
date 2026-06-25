"""Product Hunt via HTML scraping (free, no auth).

Product Hunt is a Next.js app that embeds a denormalized Apollo cache inline in
the HTML. Field order inside each ``Post`` object is not stable (sometimes
``slug`` comes before ``name``, sometimes after, and ``votesCount`` is usually
hidden), so instead of one brittle regex we split the document on Post markers
and extract each field independently from the surrounding window.
"""

from __future__ import annotations

import re

import httpx

from .base import TrendSource, TrendItem

_POST_MARKER = '"__typename":"Post"'
_NAME_RE = re.compile(r'"name":"((?:[^"\\]|\\.)*)"')
_SLUG_RE = re.compile(r'"slug":"([a-z0-9-]+)"')
_TAGLINE_RE = re.compile(r'"tagline":"((?:[^"\\]|\\.)*)"')
_COMMENTS_RE = re.compile(r'"commentsCount":(\d+)')
_VOTES_RE = re.compile(r'"votesCount":(\d+)')


def _unescape(value: str) -> str:
    return (
        value.replace("\\u0026", "&")
        .replace('\\"', '"')
        .replace("\\/", "/")
        .replace("\\n", " ")
        .strip()
    )


class ProductHuntSource(TrendSource):
    name = "producthunt"
    description = "Product Hunt - top products and launches"
    requires_auth = False
    rate_limit = "reasonable (HTML scrape)"

    BASE_URL = "https://www.producthunt.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def _parse_html(self, html_text: str) -> list[TrendItem]:
        # Each Post object spans roughly until the next Post marker; cap the window
        # so a malformed document can't make us scan megabytes per post.
        chunks = html_text.split(_POST_MARKER)
        by_slug: dict[str, dict] = {}

        for chunk in chunks[1:]:
            window = chunk[:700]
            slug_match = _SLUG_RE.search(window)
            name_match = _NAME_RE.search(window)
            if not slug_match or not name_match:
                continue
            slug = slug_match.group(1)
            name = _unescape(name_match.group(1))
            if not name:
                continue

            tagline_match = _TAGLINE_RE.search(window)
            votes_match = _VOTES_RE.search(window)
            comments_match = _COMMENTS_RE.search(window)

            entry = by_slug.setdefault(slug, {"name": name, "tagline": "", "votes": 0, "comments": 0})
            entry["name"] = name
            if tagline_match:
                entry["tagline"] = _unescape(tagline_match.group(1))
            if votes_match:
                entry["votes"] = max(entry["votes"], int(votes_match.group(1)))
            if comments_match:
                entry["comments"] = max(entry["comments"], int(comments_match.group(1)))

        items: list[TrendItem] = []
        for slug, entry in by_slug.items():
            votes = entry["votes"]
            comments = entry["comments"]
            # Votes are usually hidden on the homepage payload; fall back to comment
            # volume (×8 ≈ rough vote proxy) so ranking still reflects engagement.
            engagement = votes if votes else comments * 8
            traffic = f"{votes} votes" if votes else f"{comments} comments"
            items.append(TrendItem(
                keyword=entry["name"],
                score=min(engagement / 5, 100),
                source=self.name,
                url=f"{self.BASE_URL}/posts/{slug}",
                traffic=traffic,
                category="product",
                metadata={"tagline": entry["tagline"], "slug": slug, "comments": comments},
            ))

        items.sort(key=lambda it: it.score, reverse=True)
        return items

    async def fetch_trending(self, geo: str = "", count: int = 20) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(self.BASE_URL, headers=self.HEADERS)
            resp.raise_for_status()
            html_text = resp.text

        return self._parse_html(html_text)[:count]

    async def search(self, query: str, geo: str = "") -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                f"{self.BASE_URL}/search",
                params={"q": query},
                headers=self.HEADERS,
            )
            resp.raise_for_status()
            html_text = resp.text

        return self._parse_html(html_text)
