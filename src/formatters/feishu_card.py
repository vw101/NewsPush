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
        """Build a modular news item block with title, core summary, impact, tags, collapsible text, and link."""
        title_text = f"**{index_prefix}{item.title}**"

        tags_str = " ".join([f"`{t}`" for t in item.tags]) if item.tags else ""
        tags_line = f"\n🏷️ **标签**：{tags_str}" if tags_str else ""

        main_text = (
            f"{title_text}\n"
            f"💡 **核心事实**：{item.summary}\n"
            f"🎯 **宏观影响/实战价值**：{item.why_it_matters}"
            f"{tags_line}"
        )

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": main_text,
                },
            },
        ]

        # Detailed content in collapsible panel including technical mechanics
        detailed_body = item.technical_mechanics or item.detailed_content or item.summary
        elements.append(
            {
                "tag": "collapsible_panel",
                "expanded": False,
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "📖 展开阅读机制/技巧/安全深度解析",
                    },
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"{detailed_body}\n\n---\n{item.detailed_content}",
                        },
                    }
                ],
            }
        )

        # Direct link row below for quick access
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"🏷️ *信源：{item.source}* · [🌐 直达原文 ↗]({item.url})",
                },
            }
        )

        return elements

    def format_card(self, digest: DigestResult) -> Dict[str, Any]:
        elements = []

        # 1. Top 3 Headlines Section (今日必读头条)
        if digest.top_headlines:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**🔥 今日最重磅头条 (Top Headlines)**",
                    },
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
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{cat_title}**",
                    },
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
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": (
                            f"🤖 AI Daily Pulse 全自动中文精编 · 本期扫描 {digest.total_scanned} 篇全球信源"
                        ),
                    }
                ],
            }
        )

        card_payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True,
                    "enable_forward": True,
                },
                "header": {
                    "template": "indigo",
                    "title": {
                        "tag": "plain_text",
                        "content": f"{self.config.app_title} ({digest.date_str})",
                    },
                },
                "elements": elements,
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
