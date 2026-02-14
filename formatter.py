"""Generate daily markdown report from collected articles."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime

from config import OUTPUT_DIR
from scrapers.base import Article


def generate_report(
    articles: list[Article],
    errors: list[str],
    topics_md: str = "",
    user_profile: str = "",
    persona_name: str = "",
) -> str:
    """Generate markdown report and save to output/ directory. Returns the file path."""
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Group articles by source
    by_source: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        by_source[a.source].append(a)

    # Always generate/update the articles data file
    articles_filepath = os.path.join(OUTPUT_DIR, "hotnews_articles.md")
    articles_content = _generate_articles_section(by_source, errors)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(articles_filepath, "w", encoding="utf-8") as f:
        f.write(articles_content)

    # If we have a persona with topics, save the recommendations to a separate file
    if persona_name and topics_md:
        recommendations_filepath = os.path.join(OUTPUT_DIR, f"hotnews_推荐_{persona_name}.md")

        # Build recommendations content with header
        rec_lines: list[str] = []
        rec_lines.append(f"# 新闻日报 {today}")
        rec_lines.append("")
        rec_lines.append(f"> 生成时间: {timestamp}")
        rec_lines.append("")
        rec_lines.append(topics_md)

        recommendations_content = "\n".join(rec_lines)

        with open(recommendations_filepath, "w", encoding="utf-8") as f:
            f.write(recommendations_content)

        return recommendations_filepath

    # If no persona, just return the articles file path
    return articles_filepath


def _generate_articles_section(by_source: dict, errors: list[str]) -> str:
    """Generate the articles section as a string."""
    lines: list[str] = []
    lines.append("## 全部文章")
    lines.append("")

    for source in sorted(by_source.keys()):
        arts = by_source[source]
        lines.append(f"### {source} ({len(arts)} 篇)")
        lines.append("")
        for a in arts:
            # Title with link - using #### for article titles
            if a.url:
                lines.append(f"#### [{_escape_md(a.title)}]({a.url})")
            else:
                lines.append(f"#### {_escape_md(a.title)}")

            meta_parts = []
            if a.published_at:
                meta_parts.append(a.published_at[:16])
            if a.author:
                meta_parts.append(f"作者: {a.author}")
            if a.hits:
                meta_parts.append(f"阅读: {a.hits}")
            if meta_parts:
                lines.append(f"**{' | '.join(meta_parts)}**")

            lines.append("")

            if a.summary:
                lines.append(f"{_escape_md(a.summary)}")
                lines.append("")

            if a.is_precious_metals and a.tags:
                lines.append(f"🏷️ **贵金属关键词**: {', '.join(a.tags)}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # --- Errors ---
    if errors:
        lines.append("## 错误与警告")
        lines.append("")
        for err in errors:
            lines.append(f"```\n{err}\n```")
            lines.append("")

    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape markdown special chars in text for table cells."""
    return text.replace("|", "\\|").replace("\n", " ")
