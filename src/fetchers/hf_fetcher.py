import logging
from typing import List
import httpx
from src.fetchers.base import BaseFetcher, NewsItem

logger = logging.getLogger(__name__)


class HuggingFaceFetcher(BaseFetcher):
    """
    Fetches top AI research papers from Hugging Face Daily Papers.
    """

    def fetch(self) -> List[NewsItem]:
        items: List[NewsItem] = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        # Try fetching with retries
        papers = None
        for attempt in range(1, 3):
            try:
                with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True, http2=False) as client:
                    resp = client.get("https://huggingface.co/api/daily_papers")
                    resp.raise_for_status()
                    papers = resp.json()
                    break
            except Exception as e:
                logger.warning(f"Hugging Face fetch attempt {attempt} failed: {e}")

        if not papers:
            logger.error("Failed to fetch Hugging Face daily papers after retries.")
            return items

        try:
            for entry in papers[: self.max_items]:
                paper = entry.get("paper", {})
                paper_id = paper.get("id", "")
                title = self.clean_text(paper.get("title", ""))
                summary = self.clean_text(paper.get("summary", ""))
                upvotes = paper.get("upvotes", 0)
                authors = [a.get("name", "") for a in paper.get("authors", [])[:3]]
                authors_str = ", ".join(filter(None, authors))

                pub_date = paper.get("publishedAt", "")
                if pub_date and not self.is_within_days(pub_date, days=3):
                    continue

                formatted_summary = (
                    f"论文作者: {authors_str} | 社区点赞: {upvotes} | 核心摘要: {summary[:300]}"
                )

                item_id = NewsItem.generate_id(url, title)
                items.append(
                    NewsItem(
                        id=item_id,
                        title=f"📄 {title}",
                        url=url,
                        source_name=self.source_name,
                        category=self.category,
                        summary=formatted_summary,
                        published_at=pub_date,
                        extra={"upvotes": upvotes, "authors": authors_str},
                    )
                )
        except Exception as e:
            logger.error(f"Error parsing Hugging Face daily papers: {e}")

        return items
