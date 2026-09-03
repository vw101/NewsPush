from typing import Optional
from src.config import SourceConfig
from src.fetchers.base import BaseFetcher, NewsItem
from src.fetchers.rss_fetcher import RSSFetcher
from src.fetchers.github_fetcher import GitHubFetcher
from src.fetchers.hf_fetcher import HuggingFaceFetcher
from src.fetchers.hn_fetcher import HackerNewsFetcher


def get_fetcher(source: SourceConfig) -> Optional[BaseFetcher]:
    if source.type == "rss":
        return RSSFetcher(
            source_name=source.name,
            category=source.category,
            url=source.url,
            max_items=source.max_items,
        )
    elif source.type == "github":
        return GitHubFetcher(
            source_name=source.name,
            category=source.category,
            url=source.url,
            max_items=source.max_items,
        )
    elif source.type == "huggingface":
        return HuggingFaceFetcher(
            source_name=source.name,
            category=source.category,
            url=source.url,
            max_items=source.max_items,
        )
    elif source.type == "hackernews":
        return HackerNewsFetcher(
            source_name=source.name,
            category=source.category,
            url=source.url,
            max_items=source.max_items,
        )
    else:
        # Default fallback to RSS
        return RSSFetcher(
            source_name=source.name,
            category=source.category,
            url=source.url,
            max_items=source.max_items,
        )


__all__ = [
    "BaseFetcher",
    "NewsItem",
    "RSSFetcher",
    "GitHubFetcher",
    "HuggingFaceFetcher",
    "HackerNewsFetcher",
    "get_fetcher",
]
