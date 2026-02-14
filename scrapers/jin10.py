"""Jin10 (金十) scraper — NUXT payload parsing via Node.js eval, Playwright fallback."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile

import httpx

from config import JIN10_URL, JIN10_HEADERS
from scrapers.base import Article, BaseScraper


class Jin10Scraper(BaseScraper):
    source_name = "金十"

    def _do_fetch(self) -> list[Article]:
        articles = self._try_http()
        if articles is not None:
            return articles
        return self._try_playwright()

    def _try_http(self) -> list[Article] | None:
        """Fetch HTML, extract NUXT IIFE, evaluate with Node.js."""
        try:
            resp = httpx.get(
                JIN10_URL, headers=JIN10_HEADERS, timeout=20, follow_redirects=True,
            )
            resp.raise_for_status()
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.HTTPStatusError):
            return None
        html = resp.text

        match = re.search(r"window\.__NUXT__\s*=\s*(.+?);\s*</script>", html, re.DOTALL)
        if not match:
            return None

        raw_js = match.group(1)

        # The NUXT payload is an IIFE that chompjs can't parse.
        # Use Node.js to evaluate it safely.
        js_code = (
            "try { console.log(JSON.stringify(" + raw_js + ")); }"
            " catch(e) { process.exit(1); }"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(js_code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["node", tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            nuxt_data = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

        return self._extract_articles(nuxt_data)

    def _extract_articles(self, nuxt_data: dict) -> list[Article]:
        """Extract articles from parsed NUXT data structure."""
        articles: list[Article] = []

        data = nuxt_data.get("data") or nuxt_data.get("payload") or {}

        article_list = None
        if isinstance(data, list) and len(data) > 1:
            inner = data[1] if isinstance(data[1], dict) else {}
            article_list = inner.get("list") or inner.get("articles")
        if not article_list and isinstance(data, dict):
            article_list = data.get("list") or data.get("articles")
        if not article_list:
            state = nuxt_data.get("state", {})
            if isinstance(state, dict):
                for v in state.values():
                    if isinstance(v, dict) and "list" in v:
                        article_list = v["list"]
                        break

        if not article_list:
            return articles

        for item in article_list:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            if not title:
                continue

            intro = (item.get("introduction") or item.get("intro") or "").strip()
            display_time = item.get("display_datetime") or item.get("display_time") or ""
            detail_url = item.get("detail_url") or item.get("url") or ""
            if detail_url and not detail_url.startswith("http"):
                detail_url = f"https://xnews.jin10.com{detail_url}"

            author = item.get("author") or ""
            if isinstance(author, dict):
                author = author.get("nick") or author.get("name") or ""

            hits = item.get("hits") or item.get("reading_count") or 0

            articles.append(
                Article(
                    source=self.source_name,
                    title=title,
                    url=detail_url,
                    summary=intro,
                    published_at=str(display_time),
                    author=str(author),
                    hits=int(hits) if str(hits).isdigit() else 0,
                )
            )

        return articles

    def _try_playwright(self) -> list[Article]:
        """Fallback: use Playwright to evaluate window.__NUXT__ in browser."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(JIN10_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            nuxt_data = page.evaluate(
                """() => {
                    try {
                        return JSON.parse(JSON.stringify(window.__NUXT__));
                    } catch(e) {
                        return null;
                    }
                }"""
            )

            if nuxt_data:
                articles = self._extract_articles(nuxt_data)
                if articles:
                    browser.close()
                    return articles

            articles = self._parse_dom(page)
            browser.close()
            return articles

    def _parse_dom(self, page) -> list[Article]:
        """Parse articles from rendered DOM as last resort."""
        articles: list[Article] = []
        selectors = [
            "article", ".article-item", ".news-item",
            ".list-item", "[class*='article']", "[class*='news']",
        ]
        for selector in selectors:
            elements = page.query_selector_all(selector)
            if elements:
                for el in elements:
                    title_el = el.query_selector("h1, h2, h3, a[class*='title'], .title")
                    if not title_el:
                        continue
                    title = (title_el.inner_text() or "").strip()
                    href = title_el.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://xnews.jin10.com{href}"
                    if title:
                        articles.append(
                            Article(
                                source=self.source_name,
                                title=title,
                                url=href,
                            )
                        )
                if articles:
                    break
        return articles
