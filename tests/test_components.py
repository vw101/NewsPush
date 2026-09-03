import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from src.config import AppConfig, load_config
from src.fetchers.base import BaseFetcher, NewsItem
from src.formatters.feishu_card import FeishuCardFormatter
from src.formatters.markdown_report import MarkdownFormatter
from src.processors.deduplicator import Deduplicator
from src.processors.summarizer import DigestItem, DigestResult, NewsSummarizer


def test_config_loading():
    config = load_config()
    assert config is not None
    assert len(config.categories) == 4
    cat_ids = [c.id for c in config.categories]
    assert cat_ids == ["industry", "skills", "frontier", "security"]
    assert config.history_retention_days == 14
    assert len(config.sources) >= 5
    assert config.summarizer.top_headlines_count == 3


def test_news_item_id_generation():
    id1 = NewsItem.generate_id("https://example.com/a", "Title A")
    id2 = NewsItem.generate_id("https://example.com/a", "Title A")
    id3 = NewsItem.generate_id("https://example.com/b", "Title B")

    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 16


def test_base_fetcher_clean_text():
    dirty = "<p>Hello <b>World</b> &amp; AI &lt;test&gt;</p>\n\n   Extra spaces   "
    clean = BaseFetcher.clean_text(dirty)
    assert clean == "Hello World & AI <test> Extra spaces"


def test_is_within_days():
    now = datetime.now(timezone.utc)
    one_day_ago = (now - timedelta(days=1)).isoformat()
    four_days_ago = (now - timedelta(days=4)).isoformat()

    assert BaseFetcher.is_within_days(one_day_ago, days=3) is True
    assert BaseFetcher.is_within_days(four_days_ago, days=3) is False
    assert BaseFetcher.is_within_days(None, days=3) is True


def test_deduplicator():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_path = tf.name

    try:
        dedup = Deduplicator(temp_path, retention_days=14)
        item1 = NewsItem(id="item1", title="T1", url="http://1", source_name="S1", category="industry")
        item2 = NewsItem(id="item2", title="T2", url="http://2", source_name="S2", category="skills")

        # Initially both are unseen
        unseen = dedup.filter_unseen([item1, item2])
        assert len(unseen) == 2

        # Mark item1 as pushed
        dedup.mark_pushed([item1])

        # Next check: only item2 should be unseen
        unseen_next = dedup.filter_unseen([item1, item2])
        assert len(unseen_next) == 1
        assert unseen_next[0].id == "item2"

        # Reload deduplicator from disk
        dedup_reloaded = Deduplicator(temp_path, retention_days=14)
        unseen_reloaded = dedup_reloaded.filter_unseen([item1, item2])
        assert len(unseen_reloaded) == 1
        assert unseen_reloaded[0].id == "item2"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_robust_json_load():
    # Test valid JSON
    valid = '{"top_headlines": [{"title": "Test"}]}'
    res = NewsSummarizer._robust_json_load(valid)
    assert "top_headlines" in res

    # Test auto-repair of unclosed quote and braces
    truncated = '{"top_headlines": [{"title": "Test'
    repaired = NewsSummarizer._robust_json_load(truncated)
    assert "top_headlines" in repaired


def test_summarizer_fallback():
    config = AppConfig(llm_api_key="")
    summarizer = NewsSummarizer(config)

    items = [
        NewsItem(id="1", title="AI Model Release", url="http://a.com", source_name="OpenAI", category="industry", summary="Released new model"),
        NewsItem(id="2", title="Cursor Skill Repo", url="http://b.com", source_name="GitHub", category="skills", summary="Agent skill"),
        NewsItem(id="3", title="SOTA Paper", url="http://c.com", source_name="HuggingFace", category="frontier", summary="Paper summary"),
        NewsItem(id="4", title="Safety Eval", url="http://d.com", source_name="LessWrong", category="security", summary="Safety analysis"),
    ]

    result = summarizer.summarize(items)
    assert isinstance(result, DigestResult)
    assert len(result.top_headlines) > 0
    assert "industry" in result.categorized_items
    assert "skills" in result.categorized_items


def test_feishu_card_formatter():
    config = load_config()
    formatter = FeishuCardFormatter(config)

    digest = DigestResult(
        date_str="2026年09月03日 星期四",
        top_headlines=[
            DigestItem(
                title="DeepSeek 推出新架构",
                summary="推理效率提升 60%",
                why_it_matters="降低开源模型使用成本",
                technical_mechanics="解耦 Attention 机制压低 KV-Cache",
                url="https://example.com/deepseek",
                source="GitHub",
                category="industry",
                tags=["#Inference", "#MoE"],
            )
        ],
        categorized_items={
            "skills": [
                DigestItem(
                    title="Agent Skill 最佳实践",
                    summary="提高生产力",
                    why_it_matters="实战提效",
                    technical_mechanics="利用自动化工作流加速迭代",
                    url="https://example.com/skill",
                    source="GitHub",
                    category="skills",
                    tags=["#Agent", "#Skill"],
                )
            ]
        },
        total_scanned=10,
    )

    card = formatter.format_card(digest)
    assert card["msg_type"] == "interactive"
    assert "elements" in card["card"]
    assert len(card["card"]["elements"]) > 0


def test_markdown_formatter_with_frontmatter():
    config = load_config()
    formatter = MarkdownFormatter(config)

    digest = DigestResult(
        date_str="2026年09月03日 星期四",
        top_headlines=[
            DigestItem(
                title="GPT-5 预览版发布",
                summary="逻辑推理突破",
                why_it_matters="开启新一代生产力",
                technical_mechanics="新架构提升复杂推理能力",
                url="https://example.com/gpt5",
                source="OpenAI Blog",
                category="industry",
                tags=["#LLM", "#GPT"],
            )
        ],
        categorized_items={
            "security": [
                DigestItem(
                    title="AI 对齐防越狱评估",
                    summary="最新红队安全测试",
                    why_it_matters="防止越狱攻击",
                    technical_mechanics="多轮提示注入防御体系",
                    url="https://example.com/safety",
                    source="AI Safety",
                    category="security",
                    tags=["#AISafety", "#RedTeaming"],
                )
            ]
        },
        total_scanned=5,
    )

    md = formatter.format_markdown(digest)
    # Check YAML Frontmatter
    assert md.startswith("---\n")
    assert "title:" in md
    assert "date:" in md
    assert "tags:" in md
    assert "scanned_items: 5" in md
    assert "#AISafety" in md
    assert "# 🤖 AI Daily Pulse" in md
    assert "GPT-5 预览版发布" in md
    assert "https://example.com/gpt5" in md


def test_pipeline_dry_run_with_mock():
    from src.pipeline import NewsPipeline
    from unittest.mock import patch

    config = load_config()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        config.history_file = tf.name
    with tempfile.TemporaryDirectory() as td:
        config.archive_dir = td

        pipeline = NewsPipeline(config)
        mock_items = [
            NewsItem(id="mock1", title="Mock AI Breakthrough", url="https://mock.com/1", source_name="MockLab", category="industry", summary="Summary 1"),
            NewsItem(id="mock2", title="Mock Open Source Agent", url="https://mock.com/2", source_name="GitHub", category="skills", summary="Summary 2"),
        ]

        with patch.object(pipeline, "fetch_all", return_value=mock_items):
            res = pipeline.run(dry_run=True)
            assert res["status"] == "success"
            assert res["scanned"] == 2
            assert res["new_items"] == 2
            assert res["dry_run"] is True

    Path(config.history_file).unlink(missing_ok=True)


