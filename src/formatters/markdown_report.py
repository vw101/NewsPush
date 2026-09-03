from typing import Dict
from src.config import AppConfig
from src.processors.summarizer import DigestResult


class MarkdownFormatter:
    """
    Renders the daily digest as a clean, structured Markdown document
    with native HTML details/summary collapsible panels.
    """

    def __init__(self, config: AppConfig):
        self.config = config

    def format_markdown(self, digest: DigestResult) -> str:
        cat_meta = {cat.id: cat.name for cat in self.config.categories}
        
        # Collect all tags for Frontmatter
        all_tags = set()
        for item in digest.top_headlines:
            all_tags.update(item.tags)
        for cat_list in digest.categorized_items.values():
            for item in cat_list:
                all_tags.update(item.tags)
        tags_yaml = ", ".join([f'"{t}"' for t in sorted(all_tags)])

        lines = [
            "---",
            f"title: \"{self.config.app_title} ({digest.date_str})\"",
            f"date: \"{digest.date_str}\"",
            f"tags: [{tags_yaml}]",
            f"scanned_items: {digest.total_scanned}",
            "---",
            "",
            f"# {self.config.app_title}",
            f"> 📅 **发布日期**：{digest.date_str} | 🔍 **全网扫描（近3天）**：{digest.total_scanned} 篇资讯",
            "",
            "---",
            "",
            "## 🔥 今日最重磅头条 (Top Headlines)",
            "",
        ]

        if digest.top_headlines:
            for idx, item in enumerate(digest.top_headlines, 1):
                detailed = item.detailed_content or item.summary
                mechanics = f"- ⚡️ **机制/技巧/安全解析**：{item.technical_mechanics}\n" if item.technical_mechanics else ""
                tags_str = " ".join([f"`{t}`" for t in item.tags]) if item.tags else ""
                lines.extend(
                    [
                        f"### {idx}. {item.title}",
                        f"- 💡 **核心事实**：{item.summary}",
                        f"- 🎯 **宏观影响/实战价值**：{item.why_it_matters}",
                        mechanics.strip(),
                        f"- 🏷️ **标签**：{tags_str} | **信源**：`{item.source}` · [🌐 直达原文 ↗]({item.url})",
                        "",
                        "<details>",
                        "<summary>📖 展开阅读中文深度解析</summary>",
                        "",
                        detailed,
                        "",
                        "</details>",
                        "",
                    ]
                )
        else:
            lines.append("*今日暂无重大头条。*\n")

        lines.extend(["---", "", "## 📑 核心板块精选", ""])

        category_order = ["industry", "skills", "frontier", "security"]
        for cat_id in category_order:
            items = digest.categorized_items.get(cat_id, [])
            if not items:
                continue

            cat_title = cat_meta.get(cat_id, cat_id.capitalize())
            lines.extend([f"### {cat_title}", ""])

            for idx, item in enumerate(items, 1):
                detailed = item.detailed_content or item.summary
                mechanics = f"- ⚡️ **机制/技巧/安全解析**：{item.technical_mechanics}\n" if item.technical_mechanics else ""
                tags_str = " ".join([f"`{t}`" for t in item.tags]) if item.tags else ""
                lines.extend(
                    [
                        f"#### {idx}. {item.title}",
                        f"- 💡 **核心事实**：{item.summary}",
                        f"- 🎯 **宏观影响/实战价值**：{item.why_it_matters}",
                        mechanics.strip(),
                        f"- 🏷️ **标签**：{tags_str} | **信源**：`{item.source}` · [🌐 直达原文 ↗]({item.url})",
                        "",
                        "<details>",
                        "<summary>📖 展开阅读中文深度解析</summary>",
                        "",
                        detailed,
                        "",
                        "</details>",
                        "",
                    ]
                )

        lines.extend(
            [
                "---",
                "",
                "*由 AI Daily Pulse 全自动精编归档 · 完美契合 Obsidian / PKM 检索*",
                "",
            ]
        )

        return "\n".join(lines)
