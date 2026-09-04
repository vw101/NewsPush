import hashlib
import hmac
import time
from typing import Any, Dict
from src.config import AppConfig
from src.processors.summarizer import DigestItem, DigestResult


class FeishuCardFormatter:
    """
    Constructs Feishu Interactive Card JSON structure
    featuring 100% Chinese content, collapsible detailed panels, and direct original links.
    """

    def __init__(self, config: AppConfig):
        self.config = config

    def _build_news_block(self, item: DigestItem, index_prefix: str = "") -> list:
        """Build a mobile-first modular news block with large font title, hook, native collapsible detail, and subtle meta."""
        # 1. Headline & Hook (Large 16px bold title + 15px hook)
        title_content = f"### {index_prefix}{item.title}\n\n📌 **一句话速览**：{item.summary}"
        elements = [
            {
                "tag": "markdown",
                "content": title_content,
            }
        ]

        # 2. Detailed content inside native collapsible panel
        facts_text = item.detailed_content or item.why_it_matters or item.summary
        mechanics_text = item.technical_mechanics or "持续关注该项目后续架构演进与实践。"

        detail_markdown = (
            f"📖 **具体实况进展**：\n{facts_text}\n\n"
            f"⚙️ **底层技术机制**：\n{mechanics_text}"
        )

        elements.append(
            {
                "tag": "collapsible_panel",
                "expanded": False,
                "background_color": "grey",
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "展开完整报道与底层机制",
                    },
                    "icon": {
                        "tag": "standard_icon",
                        "token": "down-round_outlined",
                    },
                    "icon_position": "follow_text",
                    "icon_expanded_angle": -180,
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": detail_markdown,
                    }
                ],
            }
        )

        # 3. Subtle grey metadata footer
        tags_str = " ".join([f"#{t.lstrip('#')}" for t in item.tags]) if item.tags else ""
        tags_part = f" · {tags_str}" if tags_str else ""
        meta_content = f"<font color='grey'>💬 {item.source}{tags_part} · [原文 ↗]({item.url})</font>"

        elements.append(
            {
                "tag": "markdown",
                "content": meta_content,
            }
        )

        return elements

    def format_card(self, digest: DigestResult) -> Dict[str, Any]:
        elements = []

        # 1. Top Headlines Section (今日必读头条)
        if digest.top_headlines:
            elements.append(
                {
                    "tag": "markdown",
                    "content": "**🔶 今日最重磅头条 (Top Headlines)**",
                }
            )

            for idx, item in enumerate(digest.top_headlines, 1):
                elements.extend(self._build_news_block(item, index_prefix=f"{idx}. "))
                if idx < len(digest.top_headlines):
                    elements.append({"tag": "hr"})

            elements.append({"tag": "hr"})

        # Category Name Mapping
        cat_meta = {cat.id: cat.name for cat in self.config.categories}

        # 2. Categorized Sections
        category_order = ["industry", "skills", "frontier", "security"]
        for cat_id in category_order:
            items = digest.categorized_items.get(cat_id, [])
            if not items:
                continue

            cat_title = cat_meta.get(cat_id, cat_id.capitalize())
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"**{cat_title}**",
                }
            )

            for idx, item in enumerate(items, 1):
                elements.extend(self._build_news_block(item, index_prefix="• "))
                if idx < len(items):
                    elements.append({"tag": "hr"})

            elements.append({"tag": "hr"})

        # 3. Footer Note
        elements.append(
            {
                "tag": "markdown",
                "content": "<font color='grey'>✦ AI Daily Pulse · 30秒无感精读全球 AI 浪潮</font>",
            }
        )

        card_payload = {
            "msg_type": "interactive",
            "card": {
                "schema": "2.0",
                "config": {
                    "wide_screen_mode": True,
                    "enable_forward": True,
                },
                "header": {
                    "template": "wathet",
                    "title": {
                        "tag": "plain_text",
                        "content": f"{self.config.app_title} ({digest.date_str})",
                    },
                },
                "body": {
                    "direction": "vertical",
                    "elements": elements,
                },
            },
        }

        # Handle signature if secret is present
        if self.config.feishu_secret:
            timestamp = str(int(time.time()))
            sign = self._generate_sign(timestamp, self.config.feishu_secret)
            card_payload["timestamp"] = timestamp
            card_payload["sign"] = sign

        return card_payload

    @staticmethod
    def _generate_sign(timestamp: str, secret: str) -> str:
        """Generate Feishu webhook signature."""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        import base64
        return base64.b64encode(hmac_code).decode("utf-8")
