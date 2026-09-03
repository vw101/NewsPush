from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, List, Optional
from src.config import AppConfig, load_config
from src.fetchers import NewsItem, get_fetcher
from src.formatters import FeishuCardFormatter, MarkdownFormatter
from src.processors import Deduplicator, DigestResult, NewsSummarizer
from src.senders import FeishuSender

logger = logging.getLogger(__name__)


class NewsPipeline:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        self.deduplicator = Deduplicator(
            history_file=self.config.history_file,
            retention_days=self.config.history_retention_days,
        )
        self.summarizer = NewsSummarizer(self.config)
        self.feishu_formatter = FeishuCardFormatter(self.config)
        self.markdown_formatter = MarkdownFormatter(self.config)
        self.feishu_sender = FeishuSender(
            webhook_url=self.config.feishu_webhook_url,
            app_id=self.config.feishu_app_id,
            app_secret=self.config.feishu_app_secret,
            chat_id=self.config.feishu_chat_id,
        )

    def fetch_all(self) -> List[NewsItem]:
        """Fetch news concurrently from all enabled sources."""
        all_items: List[NewsItem] = []
        enabled_sources = [s for s in self.config.sources if s.enabled]
        logger.info(f"Starting news fetching from {len(enabled_sources)} sources...")

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_source = {
                executor.submit(get_fetcher(source).fetch): source
                for source in enabled_sources
                if get_fetcher(source) is not None
            }

            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    items = future.result()
                    logger.info(f"[{source.name}] Fetched {len(items)} items.")
                    all_items.extend(items)
                except Exception as e:
                    logger.error(f"[{source.name}] Failed to fetch: {e}")

        logger.info(f"Total raw items fetched: {len(all_items)}")
        return all_items

    def run(self, dry_run: bool = False, force_push: bool = False, target_chat_id: Optional[str] = None) -> Dict[str, any]:
        """
        Execute full pipeline:
        Fetch -> Deduplicate -> Summarize -> Format -> Send -> Archive -> Update History.
        """
        start_time = datetime.now()
        logger.info(f"Pipeline started at {start_time.isoformat()}")

        # 1. Fetch
        raw_items = self.fetch_all()
        if not raw_items:
            logger.warning("No news items fetched from any source.")
            return {"status": "empty", "scanned": 0, "pushed": 0}

        # 2. Deduplicate
        if force_push:
            logger.info("Force push enabled: bypassing deduplication filter.")
            filtered_items = raw_items
        else:
            filtered_items = self.deduplicator.filter_unseen(raw_items)
            logger.info(
                f"Deduplication complete: {len(filtered_items)} new items remaining out of {len(raw_items)}."
            )

        if not filtered_items:
            logger.info("All fetched news items were already pushed recently. Nothing new to report.")
            return {"status": "no_new_items", "scanned": len(raw_items), "pushed": 0}

        # 3. Summarize with LLM
        logger.info("Starting AI summarization and classification...")
        digest = self.summarizer.summarize(filtered_items)

        # 4. Format
        card_payload = self.feishu_formatter.format_card(digest)
        markdown_content = self.markdown_formatter.format_markdown(digest)

        # 5. Archive Markdown locally
        archive_path = self._save_archive(markdown_content)
        logger.info(f"Daily archive saved to: {archive_path}")

        # 6. Push to Feishu
        send_success = False
        if dry_run:
            logger.info("[DRY RUN] Skipping Feishu push.")
        else:
            logger.info("Pushing interactive card to Feishu...")
            send_success = self.feishu_sender.send(card_payload, chat_id=target_chat_id)

        # 7. Update history
        if not dry_run:
            if send_success:
                self.deduplicator.mark_pushed(filtered_items)
                logger.info("History cache updated.")
            else:
                logger.error("Feishu push failed, skipping history update so items can be retried.")

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Pipeline finished in {duration:.2f}s.")

        pipeline_status = "success" if (dry_run or send_success) else "send_failed"

        return {
            "status": pipeline_status,
            "scanned": len(raw_items),
            "new_items": len(filtered_items),
            "headlines": len(digest.top_headlines),
            "dry_run": dry_run,
            "send_success": send_success,
            "archive_path": str(archive_path),
            "duration_sec": duration,
        }

    def _save_archive(self, content: str) -> Path:
        """Save markdown digest into archives directory with YYYY-MM-DD.md format."""
        archive_dir = Path(self.config.archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        date_filename = datetime.now().strftime("%Y-%m-%d") + ".md"
        filepath = archive_dir / date_filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath
