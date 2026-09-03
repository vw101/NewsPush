import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from openai import OpenAI
from src.config import AppConfig
from src.fetchers.base import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class DigestItem:
    title: str
    summary: str
    why_it_matters: str
    technical_mechanics: str = ""  # Technical mechanics, architecture, or skill usage details (100-200 words)
    detailed_content: str = ""     # In-depth content for folding
    url: str = ""
    source: str = ""
    category: str = "industry"
    score: int = 5
    tags: List[str] = field(default_factory=list)
    original_title: str = ""


@dataclass
class DigestResult:
    date_str: str
    top_headlines: List[DigestItem] = field(default_factory=list)
    categorized_items: Dict[str, List[DigestItem]] = field(default_factory=dict)
    total_scanned: int = 0


SYSTEM_PROMPT = """你是一位顶尖的 AI 科技主编、AI 行业战略分析师兼资深 AI 架构师。
你的任务是将近 3 天从全球官方博客、GitHub Trending、Hacker News、arXiv/HuggingFace 与 AI 安全论坛抓取的原始资讯，进行深度甄别、语义去重、翻译与结构化提炼。

【核心原则】
1. **全中文化要求**：不管原始新闻是中文还是英文，所有输出内容必须全部转化为自然、专业、地道的中文。
2. **跨信源语义去重与合并**：若多条原始资讯报道的是同一个重大事件（例如 OpenAI 发布新模型），请自动合并为 1 条精炼条目，并在 `source` 字段中列出所有信源名称（如 "OpenAI Blog / HackerNews"）。
3. **结构化产出 4 大核心板块**：
   - 评选出 3 条今日最具影响力的【今日必读头条 (top_headlines)】。
   - 分类整理精选要点 (categorized_items)，每类精选 2~3 条最具价值的内容。
   - 4大分类 ID 必须精确匹配：
     * "industry" (🌐 AI 行业动态与重磅发布)
     * "skills" (🔥 热门 AI Skill 与实战工具)
     * "frontier" (🔬 前沿突破与开源风向)
     * "security" (🛡️ AI 安全领域)

4. **单条资讯字段标准**：
   - `title`: 纯中文精炼标题（带 emoji 前缀，如 🌐、🔥、🔬、🛡️）
   - `summary`: 核心事实总结（纯中文，40字以内）
   - `why_it_matters`: 宏观行业意义/落地价值（纯中文，50字以内）
   - `technical_mechanics`: 架构机制/Skill实战技巧/安全风险评估（纯中文，100~200字深度解析）
   - `detailed_content`: 综合背景与深度正文（纯中文，150~300字）
   - `tags`: 2~4 个技术主题标签列表（例如 ["#Agent", "#Inference", "#AISafety"]）
   - `url`: 原始文章 URL（保持原链接）
   - `source`: 信源名称
   - `category`: 分类 ID (industry / skills / frontier / security)
   - `score`: 影响度评分 (1-10 分)

【输出格式】
你必须且仅输出标准的 JSON 格式，格式如下：
{
  "top_headlines": [
    {
      "title": "🌐 ...（纯中文标题）",
      "summary": "...（一句话核心事实）",
      "why_it_matters": "...（宏观行业价值/影响）",
      "technical_mechanics": "...（100-200字技术架构机制/Skill用法/安全评估）",
      "detailed_content": "...（150-300字深度中文正文）",
      "tags": ["#Tag1", "#Tag2"],
      "url": "...",
      "source": "...",
      "category": "industry",
      "score": 9
    }
  ],
  "categorized_items": {
    "industry": [...],
    "skills": [...],
    "frontier": [...],
    "security": [...]
  }
}
"""


class NewsSummarizer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.client: Optional[OpenAI] = None
        if self.config.llm_api_key:
            default_headers = {
                "HTTP-Referer": "https://github.com/NewsApp",
                "X-Title": "AI Daily Pulse",
            }
            self.client = OpenAI(
                api_key=self.config.llm_api_key,
                base_url=self.config.llm_base_url,
                default_headers=default_headers,
                timeout=120.0,
            )

    def summarize(self, items: List[NewsItem]) -> DigestResult:
        now_dt = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = f"{now_dt.strftime('%Y年%m月%d日')} {weekdays[now_dt.weekday()]}"

        if not items:
            logger.warning("No items to summarize.")
            return DigestResult(date_str=date_str, total_scanned=0)

        if not self.client or not self.config.llm_api_key or self.config.llm_api_key == "your_api_key_here":
            logger.warning("LLM API key not configured or set to placeholder. Using fallback heuristic generator.")
            return self._fallback_summarize(items, date_str)

        try:
            return self._llm_summarize(items, date_str)
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}. Falling back to heuristic summary.")
            return self._fallback_summarize(items, date_str)

    def _llm_summarize(self, items: List[NewsItem], date_str: str) -> DigestResult:
        # Cap raw items sent to LLM prompt to top 20 items to keep prompt focused and prevent output token cutoff
        capped_items = items[:20]
        prepared_data = []
        for i, it in enumerate(capped_items, 1):
            prepared_data.append(
                {
                    "index": i,
                    "title": it.title,
                    "url": it.url,
                    "source": it.source_name,
                    "category": it.category,
                    "published_at": it.published_at,
                    "raw_summary": it.summary[:300],
                }
            )

        user_content = (
            f"以下是今天采集到的 {len(capped_items)} 条 AI 原始资讯列表（近 3 天）：\n"
            f"{json.dumps(prepared_data, ensure_ascii=False, indent=2)}\n\n"
            f"请挑选并生成 Top {self.config.summarizer.top_headlines_count} 头条，以及 4 大分类（industry, skills, frontier, security，每类最多 {self.config.summarizer.category_items_count} 条）精选内容。\n"
            f"注意：进行语义去重（同一事件合并为一条并附带多信源），为每条生成 technical_mechanics、why_it_matters 与 2-4 个 #Tag 标签。务必输出纯 JSON。"
        )

        response = self.client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=self.config.summarizer.temperature,
            max_tokens=self.config.summarizer.max_tokens,
            response_format={"type": "json_object"} if "deepseek" not in self.config.llm_model.lower() else None,
        )

        raw_output = response.choices[0].message.content or ""
        return self._parse_llm_json(raw_output, items, date_str)

    @staticmethod
    def _robust_json_load(clean_json: str) -> dict:
        try:
            return json.loads(clean_json)
        except json.JSONDecodeError:
            s = clean_json.strip()
            in_string = False
            escape = False
            stack = []
            for ch in s:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if ch in "{[":
                        stack.append(ch)
                    elif ch == "}" and stack and stack[-1] == "{":
                        stack.pop()
                    elif ch == "]" and stack and stack[-1] == "[":
                        stack.pop()

            if in_string:
                s += '"'

            while stack:
                open_ch = stack.pop()
                s += "}" if open_ch == "{" else "]"

            try:
                return json.loads(s)
            except json.JSONDecodeError:
                last_brace = clean_json.rfind("}")
                if last_brace != -1:
                    truncated = clean_json[: last_brace + 1]
                    t_stack = []
                    t_in_str = False
                    for ch in truncated:
                        if ch == '"':
                            t_in_str = not t_in_str
                        elif not t_in_str:
                            if ch in "{[":
                                t_stack.append(ch)
                            elif ch == "}" and t_stack and t_stack[-1] == "{":
                                t_stack.pop()
                            elif ch == "]" and t_stack and t_stack[-1] == "[":
                                t_stack.pop()
                    while t_stack:
                        op = t_stack.pop()
                        truncated += "}" if op == "{" else "]"
                    return json.loads(truncated)
                raise

    def _parse_llm_json(self, text: str, original_items: List[NewsItem], date_str: str) -> DigestResult:
        clean_json = text.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        data = self._robust_json_load(clean_json)

        # Parse top_headlines
        top_headlines: List[DigestItem] = []
        for h in data.get("top_headlines", []):
            summary = h.get("summary", "")
            detailed = h.get("detailed_content") or summary
            top_headlines.append(
                DigestItem(
                    title=h.get("title", ""),
                    summary=summary,
                    why_it_matters=h.get("why_it_matters", ""),
                    technical_mechanics=h.get("technical_mechanics", ""),
                    detailed_content=detailed,
                    url=h.get("url", ""),
                    source=h.get("source", ""),
                    category=h.get("category", "industry"),
                    score=h.get("score", 8),
                    tags=h.get("tags", []),
                )
            )

        # Parse categorized_items
        categorized_items: Dict[str, List[DigestItem]] = {}
        raw_cats = data.get("categorized_items", {})
        for cat_id, cat_list in raw_cats.items():
            parsed_list: List[DigestItem] = []
            for item in cat_list:
                summary = item.get("summary", "")
                detailed = item.get("detailed_content") or summary
                parsed_list.append(
                    DigestItem(
                        title=item.get("title", ""),
                        summary=summary,
                        why_it_matters=item.get("why_it_matters", ""),
                        technical_mechanics=item.get("technical_mechanics", ""),
                        detailed_content=detailed,
                        url=item.get("url", ""),
                        source=item.get("source", ""),
                        category=cat_id,
                        score=item.get("score", 6),
                        tags=item.get("tags", []),
                    )
                )
            if parsed_list:
                categorized_items[cat_id] = parsed_list

        return DigestResult(
            date_str=date_str,
            top_headlines=top_headlines[: self.config.summarizer.top_headlines_count],
            categorized_items=categorized_items,
            total_scanned=len(original_items),
        )

    def _fallback_summarize(self, items: List[NewsItem], date_str: str) -> DigestResult:
        """Heuristic fallback when LLM is unavailable."""
        categorized: Dict[str, List[DigestItem]] = {}
        all_digest_items: List[DigestItem] = []

        for item in items:
            desc = item.summary if item.summary else "暂无更多详细描述，请点击原文链接查看全文。"
            cat = item.category if item.category in ["industry", "skills", "frontier", "security"] else "industry"
            d_item = DigestItem(
                title=f"📌 {item.title}",
                summary=desc[:80] + ("..." if len(desc) > 80 else ""),
                why_it_matters=f"来自信源【{item.source_name}】的最新动态。",
                technical_mechanics=f"技术要点：{desc[:150]}",
                detailed_content=f"{desc}\n\n来源于【{item.source_name}】。",
                url=item.url,
                source=item.source_name,
                category=cat,
                score=5,
                tags=["#AI", f"#{cat.capitalize()}"],
                original_title=item.title,
            )
            all_digest_items.append(d_item)
            categorized.setdefault(cat, []).append(d_item)

        top_headlines = all_digest_items[: self.config.summarizer.top_headlines_count]
        for cat_id in categorized:
            categorized[cat_id] = categorized[cat_id][: self.config.summarizer.category_items_count]

        return DigestResult(
            date_str=date_str,
            top_headlines=top_headlines,
            categorized_items=categorized,
            total_scanned=len(items),
        )
