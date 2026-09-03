import logging
from typing import List
import feedparser
import httpx
from src.fetchers.base import BaseFetcher, NewsItem

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/rdf+xml, application/atom+xml, application/xml, text/xml, */*",
}


class RSSFetcher(BaseFetcher):
    def fetch(self) -> List[NewsItem]:
        items: List[NewsItem] = []
        try:
            # Fetch feed content via httpx with custom headers to prevent bot blocking
            with httpx.Client(timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
                response = client.get(self.url)
                response.raise_for_status()
                feed_content = response.text

            feed = feedparser.parse(feed_content)
            if feed.bozo and not feed.entries:
                logger.warning(f"Failed to parse RSS feed from {self.source_name} ({self.url}): {feed.bozo_exception}")
                return items

            for entry in feed.entries[: self.max_items]:
                title = self.clean_text(entry.get("title", ""))
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                # Get description / summary / content
                summary = ""
                if "summary" in entry:
                    summary = self.clean_text(entry.summary)
                elif "description" in entry:
                    summary = self.clean_text(entry.description)
                elif "content" in entry and entry.content:
                    summary = self.clean_text(entry.content[0].get("value", ""))

                # Limit raw summary length to avoid bloated prompts
                if len(summary) > 400:
                    summary = summary[:400] + "..."

                # Published date
                pub_date = entry.get("published", entry.get("updated", ""))
                if pub_date and not self.is_within_days(pub_date, days=3):
                    logger.debug(f"[{self.source_name}] Skipping item published > 3 days ago: {title}")
                    continue

                item_id = NewsItem.generate_id(link, title)
                items.append(
                    NewsItem(
                        id=item_id,
                        title=title,
                        url=link,
                        source_name=self.source_name,
                        category=self.category,
                        summary=summary,
                        published_at=pub_date,
                    )
                )

        except Exception as e:
            logger.error(f"Error fetching RSS from {self.source_name} ({self.url}): {e}")

        return items
