import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from src.fetchers.base import NewsItem

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Deduplicator tracks previously pushed news items to prevent duplicate notifications.
    Persists history to a JSON file.
    """

    def __init__(self, history_file: str, retention_days: int = 7):
        self.history_file = Path(history_file)
        self.retention_days = retention_days
        self.history: Dict[str, str] = {}  # item_id -> iso_timestamp
        self._load_history()

    def _load_history(self) -> None:
        if not self.history_file.exists():
            self.history = {}
            return

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.history = data.get("pushed_items", {})
            self._prune_expired()
        except Exception as e:
            logger.warning(f"Could not load history file {self.history_file}: {e}. Initializing empty history.")
            self.history = {}

    def _prune_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        pruned = {}
        for item_id, ts_str in self.history.items():
            try:
                # Parse ISO timestamp
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    pruned[item_id] = ts_str
            except Exception:
                continue
        self.history = pruned

    def filter_unseen(self, items: List[NewsItem]) -> List[NewsItem]:
        """Filter out items that have already been pushed or seen within retention period."""
        unseen: List[NewsItem] = []
        for item in items:
            if item.id not in self.history:
                unseen.append(item)
            else:
                logger.debug(f"Skipping duplicate item: {item.title} ({item.id})")
        return unseen

    def mark_pushed(self, items: List[NewsItem]) -> None:
        """Record items as pushed and save history to disk."""
        now_str = datetime.now(timezone.utc).isoformat()
        for item in items:
            self.history[item.id] = now_str

        self._prune_expired()
        self._save_history()

    def _save_history(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "retention_days": self.retention_days,
                        "pushed_items": self.history,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"Failed to save history file {self.history_file}: {e}")
