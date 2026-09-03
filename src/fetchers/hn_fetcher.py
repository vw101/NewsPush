import logging
from typing import List
import httpx
from src.fetchers.base import BaseFetcher, NewsItem

logger = logging.getLogger(__name__)


class HackerNewsFetcher(BaseFetcher):
    """
    Fetches top AI / LLM discussions from Hacker News via the official Algolia API.
    Fast, reliable, and immune to 502 gateway errors.
    """

    def fetch(self) -> List[NewsItem]:
        items: List[NewsItem] = []
        headers = {
            "User-Agent": "AI-Daily-Pulse/1.0",
            "Accept": "application/json",
        }
        params = {
            "query": "AI OR LLM OR GPT OR Claude OR DeepSeek",
            "tags": "story",
            "numericFilters": "points>=50",
            "hitsPerPage": self.max_items,
        }

        try:
            with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
                resp = client.get("https://hn.algolia.com/api/v1/search_by_date", params=params)
                resp.raise_for_status()
                data = resp.json()

            for hit in data.get("hits", [])[: self.max_items]:
                title = self.clean_text(hit.get("title", ""))
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                points = hit.get("points", 0)
                num_comments = hit.get("num_comments", 0)
                created_at = hit.get("created_at", "")
                if created_at and not self.is_within_days(created_at, days=3):
                    continue

                hn_discuss_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"

                summary = f"HN 得分: {points} 点赞 | 讨论数: {num_comments} 条评论 | 社区讨论: {hn_discuss_url}"

                item_id = NewsItem.generate_id(url, title)
                items.append(
                    NewsItem(
                        id=item_id,
                        title=f"🔥 {title}",
                        url=url,
                        source_name=self.source_name,
                        category=self.category,
                        summary=summary,
                        published_at=created_at,
                        extra={"points": points, "comments": num_comments},
                    )
                )
        except Exception as e:
            logger.error(f"Error fetching Hacker News: {e}")

        return items
