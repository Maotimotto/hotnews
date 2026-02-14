"""Eastmoney (东方财富) 股吧热门话题 scraper — POST API."""

from __future__ import annotations

import httpx

from config import EASTMONEY_GUBA_API_URL, EASTMONEY_GUBA_HEADERS
from scrapers.base import Article, BaseScraper


class EastmoneyGubaScraper(BaseScraper):
    source_name = "东方财富股吧"

    def _do_fetch(self) -> list[Article]:
        resp = httpx.post(
            EASTMONEY_GUBA_API_URL,
            data={"path": "newtopic/api/Topic/HomePageListRead"},
            headers=EASTMONEY_GUBA_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        topics = data.get("re") or []
        articles: list[Article] = []

        for topic in topics:
            name = (topic.get("nickname") or "").strip()
            if not name:
                continue

            desc = (topic.get("desc") or "").strip()
            htid = topic.get("htid")
            url = f"https://gubatopic.eastmoney.com/news/topic/{htid}.html" if htid else ""

            click_num = topic.get("clickNumber") or 0
            post_num = topic.get("postNumber") or 0

            # Extract related stock names as tags
            stocks = topic.get("recomStock") or topic.get("stock_list") or []
            stock_tags = []
            if isinstance(stocks, list):
                for s in stocks[:5]:
                    if isinstance(s, dict):
                        sname = s.get("name", "")
                        if sname:
                            stock_tags.append(sname)

            articles.append(
                Article(
                    source=self.source_name,
                    title=name,
                    url=url,
                    summary=desc,
                    hits=click_num,
                    tags=stock_tags,
                )
            )

        return articles
