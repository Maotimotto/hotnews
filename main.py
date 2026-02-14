"""Main orchestrator — runs scrapers, applies filters, generates report."""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

from scrapers import (
    CLSScraper,
    Jin10Scraper,
    FutuScraper,
    EastmoneyNewsScraper,
    EastmoneyGubaScraper,
)
from filters import tag_precious_metals
from formatter import generate_report

# LLM Configuration - hardcoded for deployment
LLM_BASE_URL = "https://api.ephone.chat/v1/chat/completions"
LLM_API_KEY = "sk-8BXSZEmvWaM3qanlEMt4eRcDqLjQrh44rWwiNevSfSZ0Sxcl"
LLM_MODEL_POOL = [
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gpt-5.2",
    "glm-4.7"
]

# Progress tracking
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "output", "progress.json")


def update_progress(current: int, total: int, message: str = ""):
    """Update progress file for frontend to read."""
    progress_data = {
        "current": current,
        "total": total,
        "percentage": int((current / total) * 100) if total > 0 else 0,
        "message": message,
    }
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress_data, f, ensure_ascii=False)


def generate_topics_with_llm(
    articles: list,
    user_profile: str,
    persona_name: str = "",
) -> str:
    """Use LLM to generate personalized topic recommendations for the persona.

    Returns the raw markdown text from the LLM.
    """
    # Build headline list with source and URL
    headline_entries = []
    title_url_map: dict[str, str] = {}
    for a in articles:
        entry = f"- 【{a.source}】{a.title}"
        if a.url:
            entry += f"（{a.url}）"
            title_url_map[a.title] = a.url
        headline_entries.append(entry)

    headlines = "\n".join(headline_entries)

    prompt = f"""你的任务
根据以下提供的【新闻素材】和【达人画像】，为该达人生成一份个性化的选题推荐列表。

输入

达人画像
{user_profile}

今日新闻素材
{headlines}

推荐逻辑

请按以下步骤思考：

1. 理解达人定位：分析达人的内容风格、核心领域、目标受众和惯用角度。
2. 筛选相关素材：从所有新闻源中，挑选与达人定位相关的新闻（直接相关或可延伸关联）。
3. 生成选题：将筛选出的素材转化为适合该达人风格的具体选题，而非简单复述标题。每个选题应体现达人的独特视角和表达方式。
4. 排序与分类：按相关度和时效性排序。

输出格式

请输出 8-15 个选题建议，每个选题包含：

- 选题标题：一句适合该达人风格的标题（可直接用于视频/文章）
- 核心角度：用一句话说明这个选题的切入点
- 素材来源：引用了哪条/哪几条新闻，必须使用 Markdown 超链接格式 [新闻标题](URL)
- 推荐理由：为什么这个选题适合该达人（1-2句）
- 热度评级：🔥（高）/ 🔶（中）/ ⚪（低）

注意事项
- 优先推荐有争议性、有观点空间的话题，而非纯资讯类新闻
- 可以将多条相关新闻合并为一个更有深度的选题
- 选题要有"钩子"——能引发观众好奇或共鸣
- 避免推荐与达人定位完全无关的内容，即使该新闻很热门
- 如果某条重大新闻与达人领域有间接关联，可以建议一个"跨界解读"角度

请严格按照以下 Markdown 格式输出，注意使用正确的 Markdown 标题层级和换行：

## {persona_name} · 今日选题推荐

---

### 选题1：选题标题

- **核心角度**：...
- **素材来源**：[新闻标题1](URL1)、[新闻标题2](URL2)
- **推荐理由**：...
- **热度评级**：🔥/🔶/⚪

---

### 选题2：选题标题

- **核心角度**：...
- **素材来源**：[新闻标题](URL)
- **推荐理由**：...
- **热度评级**：🔥/🔶/⚪

...

### 总结排序建议

说明优先产出哪几个选题及原因。"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    for i, model in enumerate(LLM_MODEL_POOL):
        print(f"正在调用 LLM 生成选题推荐 (模型: {model})...")
        payload["model"] = model
        try:
            resp = httpx.post(
                LLM_BASE_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            break
        except Exception as e:
            print(f"模型 {model} 调用失败: {e}")
            if i == len(LLM_MODEL_POOL) - 1:
                raise

    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    # Post-process: replace plain-text title references with markdown links
    content = _linkify_titles(content, title_url_map)

    return content


def _linkify_titles(text: str, title_url_map: dict[str, str]) -> str:
    """Replace plain-text news title mentions with markdown hyperlinks.

    Skips titles that are already inside a markdown link [...](url).
    Sorts by title length descending to avoid partial matches.
    """
    import re
    for title in sorted(title_url_map, key=len, reverse=True):
        url = title_url_map[title]
        # Skip if this title is already a markdown link somewhere
        escaped = re.escape(title)
        # Match the title only when NOT already inside [...](...)
        # i.e. not preceded by [ or followed by ](
        pattern = r"(?<!\[)" + escaped + r"(?!\]\()"
        replacement = f"[{title}]({url})"
        text = re.sub(pattern, replacement, text, count=0)
    return text


def main():
    # Read user profile and persona name from command line arguments
    user_profile = ""
    persona_name = ""
    if len(sys.argv) > 1:
        user_profile = sys.argv[1]
    if len(sys.argv) > 2:
        persona_name = sys.argv[2]

    all_articles = []
    all_errors = []

    scrapers = [
        CLSScraper(),
        Jin10Scraper(),
        FutuScraper(),
        EastmoneyNewsScraper(),
        EastmoneyGubaScraper(),
    ]

    # Total steps: scrapers + filter + LLM + report generation
    total_steps = len(scrapers) + 3
    current_step = 0

    for i, scraper in enumerate(scrapers):
        current_step += 1
        update_progress(current_step, total_steps, f"正在抓取 {scraper.source_name}...")
        print(f"[{scraper.source_name}] 正在抓取...")
        articles, errors = scraper.fetch()
        print(f"[{scraper.source_name}] 获取 {len(articles)} 篇文章")
        if errors:
            for err in errors:
                print(f"[{scraper.source_name}] 错误: {err[:200]}")
        all_articles.extend(articles)
        all_errors.extend(errors)

        # Small delay between scrapers
        if i < len(scrapers) - 1:
            time.sleep(1.5)

    # Apply precious metals filter
    current_step += 1
    update_progress(current_step, total_steps, "正在筛选贵金属相关文章...")
    print(f"\n共获取 {len(all_articles)} 篇文章，正在筛选贵金属相关...")
    tag_precious_metals(all_articles)
    precious_count = sum(1 for a in all_articles if a.is_precious_metals)
    print(f"贵金属相关: {precious_count} 篇")

    # LLM personalized topic recommendations
    topics_md = ""
    if user_profile:
        try:
            current_step += 1
            update_progress(current_step, total_steps, "正在生成选题推荐...")
            topics_md = generate_topics_with_llm(all_articles, user_profile, persona_name or "达人")
            print(f"LLM 选题推荐已生成")
        except Exception as e:
            print(f"LLM 选题推荐失败: {e}")
    else:
        current_step += 1
        print("未提供达人画像，跳过选题推荐")

    # Generate report
    current_step += 1
    update_progress(current_step, total_steps, "正在生成报告...")
    filepath = generate_report(all_articles, all_errors, topics_md, user_profile, persona_name)
    print(f"\n报告已生成: {filepath}")

    # Clear progress file
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


if __name__ == "__main__":
    main()
