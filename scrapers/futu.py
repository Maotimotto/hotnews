"""Futu (富途) scraper — via TopHub SSR page."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from config import FUTU_URL, FUTU_HEADERS
from scrapers.base import Article, BaseScraper


class FutuScraper(BaseScraper):
    source_name = "富途"

    def _do_fetch(self) -> list[Article]:
        resp = httpx.get(FUTU_URL, headers=FUTU_HEADERS, timeout=15, follow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_="table")
        if not table:
            return []

        articles: list[Article] = []
        seen_titles: set[str] = set()

        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 3:
                continue

            content_td = tds[2]
            link = content_td.find("a")
            if not link:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            if title in seen_titles:
                continue
            seen_titles.add(title)

            url = link.get("href", "")

            # Source is in .item-desc div
            author = ""
            desc_div = content_td.find("div", class_="item-desc")
            if desc_div:
                author = desc_div.get_text(strip=True)

            articles.append(
                Article(
                    source=self.source_name,
                    title=title,
                    url=url,
                    author=author,
                )
            )

        return articles
