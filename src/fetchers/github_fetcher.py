from datetime import datetime, timedelta, timezone
import logging
from typing import List
import httpx
from src.fetchers.base import BaseFetcher, NewsItem

logger = logging.getLogger(__name__)


class GitHubFetcher(BaseFetcher):
    """
    Fetches trending/hot AI & LLM repositories on GitHub using the public Search API.
    No authentication required, rate-limited reasonably.
    """

    def fetch(self) -> List[NewsItem]:
        items: List[NewsItem] = []
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Daily-Pulse/1.0",
        }

        # Search active, popular LLM / AI repos
        queries = [
            {"q": "topic:llm stars:>100", "sort": "updated"},
            {"q": "topic:ai-agent stars:>50", "sort": "updated"},
        ]

        for query_info in queries:
            if len(items) >= self.max_items:
                break
            params = {
                "q": query_info["q"],
                "sort": query_info["sort"],
                "order": "desc",
                "per_page": self.max_items - len(items),
            }

            try:
                with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
                    resp = client.get("https://api.github.com/search/repositories", params=params)
                    if resp.status_code == 403:
                        logger.warning("GitHub API rate limit hit.")
                        break
                    resp.raise_for_status()
                    data = resp.json()

                for repo in data.get("items", []):
                    name = repo.get("full_name", "")
                    html_url = repo.get("html_url", "")
                    description = self.clean_text(repo.get("description", "No description provided."))
                    stars = repo.get("stargazers_count", 0)
                    lang = repo.get("language") or "Python"
                    created_at = repo.get("pushed_at", repo.get("created_at", ""))
                    if created_at and not self.is_within_days(created_at, days=3):
                        continue

                    title = f"⭐ {name} ({stars:,} stars - {lang})"
                    summary = f"{description} | 语言: {lang} | Star 数: {stars:,}"

                    item_id = NewsItem.generate_id(html_url, name)
                    items.append(
                        NewsItem(
                            id=item_id,
                            title=title,
                            url=html_url,
                            source_name=self.source_name,
                            category=self.category,
                            summary=summary,
                            published_at=created_at,
                            extra={"stars": stars, "language": lang},
                        )
                    )
            except Exception as e:
                logger.error(f"Error fetching GitHub repositories: {e}")

        return items
