import hashlib
import re
import html
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class NewsItem:
    id: str  # Unique hash computed from URL or GUID
    title: str
    url: str
    source_name: str
    category: str
    summary: str = ""
    published_at: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def generate_id(cls, url: str, title: str = "") -> str:
        content = f"{url.strip().lower()}|{title.strip().lower()}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class BaseFetcher(ABC):
    def __init__(self, source_name: str, category: str, url: str, max_items: int = 5):
        self.source_name = source_name
        self.category = category
        self.url = url
        self.max_items = max_items

    @abstractmethod
    def fetch(self) -> List[NewsItem]:
        """Fetch news items from source."""
        pass

    @staticmethod
    def clean_text(text: Optional[str]) -> str:
        """Strip HTML tags, decode entities, and normalize whitespace."""
        if not text:
            return ""
        # Remove HTML tags first
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities
        text = html.unescape(text)
        # Remove multiple newlines and spaces
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def is_within_days(date_str: Optional[str], days: int = 3) -> bool:
        """Return True if publication date is within the last `days` (default 3 days)."""
        if not date_str:
            return True  # If date is missing, retain item by default
        from datetime import datetime, timezone, timedelta
        import email.utils
        dt = None
        try:
            from dateutil import parser
            dt = parser.parse(date_str)
        except Exception:
            try:
                dt = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except Exception:
                    return True

        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            return dt >= cutoff
        return True
