import hashlib
import hmac
import time
from typing import Any, Dict, List
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
        """Build a mobile-first modular news block with extra-large title, indented column container, native collapsible detail, and subtle meta."""
        # 1. Headline & Hook (Enlarged H2 title + 15px hook)
        title_content = f"## {index_prefix}{item.title}\n\n📌 **一句话速览**：{item.summary}"

        # 2. Detailed content inside native collapsible panel with enlarged subheadings and double-spaced readability
        facts_text = item.detailed_content or item.why_it_matters or item.summary
        mechanics_text = item.technical_mechanics or "持续关注该项目后续架构演进与实践。"

        detail_markdown = (
            f"### 📖 具体实况进展\n{facts_text}\n\n"
            f"### ⚙️ 底层技术机制\n{mechanics_text}"
        )

        tags_str = " ".join([f"#{t.lstrip('#')}" for t in item.tags]) if item.tags else ""
        tags_part = f" · {tags_str}" if tags_str else ""
        meta_content = f"<font color='grey'>💬 {item.source}{tags_part} · [原文 ↗]({item.url})</font>"

        inner_elements = [
            {
                "tag": "markdown",
                "content": title_content,
            },
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
            },
            {
                "tag": "markdown",
                "content": meta_content,
            },
        ]

        return inner_elements

    @staticmethod
    def count_card_elements(payload: Any) -> int:
        """Recursively count all components/elements with a 'tag' field."""
        count = 0
        if isinstance(payload, dict):
            if "tag" in payload:
                count += 1
            for val in payload.values():
                count += FeishuCardFormatter.count_card_elements(val)
        elif isinstance(payload, list):
            for val in payload:
                count += FeishuCardFormatter.count_card_elements(val)
        return count

    def format_card(self, digest: DigestResult) -> Dict[str, Any]:
        """
        Constructs rich Feishu Interactive Card Schema 2.0.
        Uses clean direct layout without redundant container nesting to strictly comply with the 200-element limit.
        """
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

        # Check total element count budget to absolutely prevent 11310
        total_elements = self.count_card_elements(card_payload)
        if total_elements > 185:
            return self.format_compact_card(digest)

        if self.config.feishu_secret:
            timestamp = str(int(time.time()))
            sign = self._generate_sign(timestamp, self.config.feishu_secret)
            card_payload["timestamp"] = timestamp
            card_payload["sign"] = sign

        return card_payload

    def format_compact_card(self, digest: DigestResult) -> Dict[str, Any]:
        """
        Ultra-lightweight fallback card with minimal element count (<40 elements).
        Guaranteed to bypass element limit (11310) and mobile rendering bottlenecks.
        """
        elements = []

        if digest.top_headlines:
            elements.append(
                {
                    "tag": "markdown",
                    "content": "**🔶 今日最重磅头条 (Top Headlines)**",
                }
            )
            hl_md = []
            for idx, item in enumerate(digest.top_headlines, 1):
                tags_str = " ".join([f"#{t.lstrip('#')}" for t in item.tags]) if item.tags else ""
                hl_md.append(
                    f"**{idx}. {item.title}**\n"
                    f"📌 {item.summary}\n"
                    f"<font color='grey'>💬 {item.source} {tags_str} · [原文 ↗]({item.url})</font>"
                )
            elements.append({"tag": "markdown", "content": "\n\n".join(hl_md)})
            elements.append({"tag": "hr"})

        cat_meta = {cat.id: cat.name for cat in self.config.categories}
        category_order = ["industry", "skills", "frontier", "security"]
        for cat_id in category_order:
            items = digest.categorized_items.get(cat_id, [])
            if not items:
                continue

            cat_title = cat_meta.get(cat_id, cat_id.capitalize())
            elements.append({"tag": "markdown", "content": f"**{cat_title}**"})

            cat_md = []
            for item in items:
                tags_str = " ".join([f"#{t.lstrip('#')}" for t in item.tags]) if item.tags else ""
                cat_md.append(
                    f"• **{item.title}**\n"
                    f"  {item.summary} <font color='grey'>({item.source} · [原文 ↗]({item.url}))</font>"
                )
            elements.append({"tag": "markdown", "content": "\n\n".join(cat_md)})
            elements.append({"tag": "hr"})

        elements.append(
            {
                "tag": "markdown",
                "content": "<font color='grey'>✦ AI Daily Pulse · 30秒无感精读全球 AI 浪潮 (精炼版)</font>",
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
