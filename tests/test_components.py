import json
import tempfile
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


def test_deduplicator():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_path = tf.name

    try:
        dedup = Deduplicator(temp_path, retention_days=7)
        item1 = NewsItem(id="item1", title="T1", url="http://1", source_name="S1", category="industry")
        item2 = NewsItem(id="item2", title="T2", url="http://2", source_name="S2", category="industry")

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
        dedup_reloaded = Deduplicator(temp_path, retention_days=7)
        unseen_reloaded = dedup_reloaded.filter_unseen([item1, item2])
        assert len(unseen_reloaded) == 1
        assert unseen_reloaded[0].id == "item2"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_summarizer_fallback():
    config = AppConfig(llm_api_key="")
    summarizer = NewsSummarizer(config)

    items = [
        NewsItem(id="1", title="AI Model Release", url="http://a.com", source_name="OpenAI", category="industry", summary="Released new model"),
        NewsItem(id="2", title="New Repo", url="http://b.com", source_name="GitHub", category="opensource", summary="Open source project"),
    ]

    result = summarizer.summarize(items)
    assert isinstance(result, DigestResult)
    assert len(result.top_headlines) > 0
    assert "202" in result.date_str


def test_feishu_card_formatter():
    config = load_config()
    formatter = FeishuCardFormatter(config)

    digest = DigestResult(
        date_str="2026年09月02日 星期三",
        top_headlines=[
            DigestItem(
                title="DeepSeek 推出新算法",
                summary="推理效率提升 50%",
                why_it_matters="降低开源模型使用成本",
                url="https://example.com/deepseek",
                source="GitHub",
                category="industry",
            )
        ],
        categorized_items={
            "opensource": [
                DigestItem(
                    title="vLLM 新增多模态支持",
                    summary="大幅提升吞吐",
                    why_it_matters="生产环境加速",
                    url="https://example.com/vllm",
                    source="GitHub",
                    category="opensource",
                )
            ]
        },
        total_scanned=10,
    )

    card = formatter.format_card(digest)
    assert card["msg_type"] == "interactive"
    assert "elements" in card["card"]
    assert len(card["card"]["elements"]) > 0


def test_markdown_formatter():
    config = load_config()
    formatter = MarkdownFormatter(config)

    digest = DigestResult(
        date_str="2026年09月02日 星期三",
        top_headlines=[
            DigestItem(
                title="GPT-5 预览版发布",
                summary="逻辑推理突破",
                why_it_matters="开启新一代生产力",
                url="https://example.com/gpt5",
                source="OpenAI Blog",
                category="industry",
            )
        ],
        categorized_items={},
        total_scanned=5,
    )

    md = formatter.format_markdown(digest)
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
            NewsItem(id="mock2", title="Mock Open Source Agent", url="https://mock.com/2", source_name="GitHub", category="opensource", summary="Summary 2"),
        ]

        with patch.object(pipeline, "fetch_all", return_value=mock_items):
            res = pipeline.run(dry_run=True)
            assert res["status"] == "success"
            assert res["scanned"] == 2
            assert res["new_items"] == 2
            assert res["dry_run"] is True

    Path(config.history_file).unlink(missing_ok=True)

