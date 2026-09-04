import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from dotenv import load_dotenv

# Load .env file from project root if it exists
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class SourceConfig:
    name: str
    category: str
    type: str  # rss, github, huggingface, etc.
    url: str
    enabled: bool = True
    max_items: int = 5


@dataclass
class CategoryConfig:
    id: str
    name: str
    description: str


@dataclass
class SummarizerConfig:
    top_headlines_count: int = 3
    category_items_count: int = 3
    temperature: float = 0.3
    max_tokens: int = 3000


@dataclass
class AppConfig:
    # LLM Settings (OpenRouter API)
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "google/gemini-2.0-flash-exp:free")
    )

    # Feishu Settings (支持两种模式：企业自建应用 OpenAPI 或 群自定义 Webhook)
    feishu_webhook_url: str = field(default_factory=lambda: os.getenv("FEISHU_WEBHOOK_URL", ""))
    feishu_secret: str = field(default_factory=lambda: os.getenv("FEISHU_SECRET", ""))
    feishu_app_id: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""))
    feishu_app_secret: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""))
    feishu_chat_id: str = field(default_factory=lambda: os.getenv("FEISHU_CHAT_ID", ""))

    # General App Settings
    app_title: str = "🤖 AI Daily Pulse · 每日早报"
    timezone: str = "Asia/Shanghai"
    language: str = field(default_factory=lambda: os.getenv("LANGUAGE", "zh-CN"))

    # Storage & Deduplication
    history_file: str = field(default_factory=lambda: os.getenv("HISTORY_FILE", "data/history.json"))
    archive_dir: str = field(default_factory=lambda: os.getenv("ARCHIVE_DIR", "archives"))
    history_retention_days: int = field(
        default_factory=lambda: int(os.getenv("DEDUPLICATE_DAYS", "7"))
    )

    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)
    categories: List[CategoryConfig] = field(default_factory=list)
    sources: List[SourceConfig] = field(default_factory=list)


def load_config(
    config_path: Optional[str] = None,
    sources_path: Optional[str] = None,
) -> AppConfig:
    config_file = Path(config_path) if config_path else PROJECT_ROOT / "config" / "config.yaml"
    sources_file = Path(sources_path) if sources_path else PROJECT_ROOT / "config" / "sources.yaml"

    config_data: Dict[str, Any] = {}
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    sources_data: Dict[str, Any] = {}
    if sources_file.exists():
        with open(sources_file, "r", encoding="utf-8") as f:
            sources_data = yaml.safe_load(f) or {}

    # Parse categories
    categories = [
        CategoryConfig(
            id=cat["id"],
            name=cat["name"],
            description=cat.get("description", ""),
        )
        for cat in config_data.get("categories", [])
    ]

    # Parse summarizer config
    sum_data = config_data.get("summarizer", {})
    summarizer_cfg = SummarizerConfig(
        top_headlines_count=sum_data.get("top_headlines_count", 3),
        category_items_count=sum_data.get("category_items_count", 3),
        temperature=sum_data.get("temperature", 0.3),
        max_tokens=sum_data.get("max_tokens", 3000),
    )

    # Parse sources
    sources = [
        SourceConfig(
            name=s["name"],
            category=s.get("category", "industry"),
            type=s.get("type", "rss"),
            url=s["url"],
            enabled=s.get("enabled", True),
            max_items=s.get("max_items", 5),
        )
        for s in sources_data.get("sources", [])
    ]

    app_data = config_data.get("app", {})
    storage_data = config_data.get("storage", {})

    return AppConfig(
        app_title=app_data.get("title", "🤖 AI Daily Pulse · 每日早报"),
        timezone=app_data.get("timezone", "Asia/Shanghai"),
        history_file=storage_data.get("history_file", "data/history.json"),
        archive_dir=storage_data.get("archive_dir", "archives"),
        history_retention_days=storage_data.get("history_retention_days", 7),
        summarizer=summarizer_cfg,
        categories=categories,
        sources=sources,
    )
