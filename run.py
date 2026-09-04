#!/usr/bin/env python3
"""
AI Daily Pulse - CLI Entry Point
Usage:
    python run.py                     # Run daily digest & push to Feishu
    python run.py --dry-run           # Run fetch & summarize without pushing
    python run.py --force             # Force run ignoring deduplication
    python run.py --test-feishu       # Send a test card to verify webhook connection
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from src.config import AppConfig, load_config
from src.pipeline import NewsPipeline
from src.senders.feishu_sender import FeishuSender


def setup_logging(verbose: bool = False) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def test_feishu(config: AppConfig) -> None:
    webhook_url = config.feishu_webhook_url
    if not webhook_url or webhook_url == "your_token_here":
        print("❌ 错误: 请先在 .env 或环境变量中配置有效的 FEISHU_WEBHOOK_URL")
        sys.exit(1)

    print(f"📡 正在向飞书 Webhook 发送测试卡片...")
    sender = FeishuSender(webhook_url)
    test_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "🎉 AI Daily Pulse 机器人连通性测试"},
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**恭喜！飞书机器人 Webhook 配置成功！**\n\n"
                            "✅ 机器人已就绪，每天早上将按时向本群推送最新的 AI 每日早报。\n"
                            "💡 您也可以在本地随时执行 `python run.py` 立即触发推送。"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "连通性测试成功 · AI Daily Pulse"}
                    ],
                },
            ],
        },
    }

    if config.feishu_secret:
        import time
        from src.formatters.feishu_card import FeishuCardFormatter
        timestamp = str(int(time.time()))
        sign = FeishuCardFormatter._generate_sign(timestamp, config.feishu_secret)
        test_payload["timestamp"] = timestamp
        test_payload["sign"] = sign

    success = sender.send(test_payload)
    if success:
        print("✅ 飞书测试卡片发送成功！请在飞书群中查看效果。")
    else:
        print("❌ 发送失败，请检查 Webhook 地址及签名密钥。")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Daily Pulse - 每日 AI 资讯聚合与飞书卡片推送系统"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="演练模式：抓取并提炼资讯，输出预览结果，不向飞书实际发送，不记录已读去重",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制推送：忽略历史已读去重缓存，抓取最新全部数据并推送",
    )
    parser.add_argument(
        "--test-feishu",
        action="store_true",
        help="仅测试飞书 Webhook 连通性，发送一张测试卡片",
    )
    parser.add_argument(
        "-s",
        "--server",
        action="store_true",
        help="启动飞书事件监听 Web 服务 (FastAPI Server)，支持响应群内 @机器人 消息",
    )
    parser.add_argument(
        "-w",
        "--ws",
        action="store_true",
        help="启动飞书官方「长连接」WebSocket 监听模式，支持群内 @机器人 实时自动响应（无需公网IP/域名/服务器）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="指定配置文件路径 (默认 config/config.yaml)",
    )
    parser.add_argument(
        "--chat-id",
        type=str,
        default=None,
        help="指定推送的目标飞书群 Chat ID",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="开启详细调试日志",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    config = load_config(config_path=args.config)

    if args.ws:
        from src.feishu_ws import start_ws
        start_ws()
        return

    if args.server:
        from src.server import start_server
        start_server()
        return

    if args.test_feishu:
        test_feishu(config)
        return

    print("=" * 60)
    print(f"🚀 启动 {config.app_title}")
    print(f"模式: {'[DRY RUN 预览模式]' if args.dry_run else '[正式推送模式]'}")
    print("=" * 60)

    pipeline = NewsPipeline(config)
    result = pipeline.run(dry_run=args.dry_run, force_push=args.force, target_chat_id=args.chat_id)

    print("\n" + "=" * 60)
    print("📊 执行结果汇总:")
    print(f" - 状态: {result.get('status')}")
    print(f" - 抓取文章总数: {result.get('scanned', 0)}")
    print(f" - 新增待推文章: {result.get('new_items', 0)}")
    print(f" - 今日头条数量: {result.get('headlines', 0)}")
    if result.get("archive_path"):
        print(f" - 简报归档路径: {result.get('archive_path')}")
    print(f" - 耗时: {result.get('duration_sec', 0):.2f} 秒")
    print("=" * 60)

    if result.get("status") == "send_failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
