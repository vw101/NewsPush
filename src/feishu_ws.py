import inspect
import json
import logging
import ssl
import threading
import httpx
import lark_oapi as lark
import lark_oapi.ws.client
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
import websockets
from src.config import AppConfig, load_config
from src.pipeline import NewsPipeline

logger = logging.getLogger(__name__)


# 解决 macOS / 代理 / VPN 环境下 self-signed certificate in certificate chain 导致的 SSL 握手失败
def _patch_lark_ws_ssl():
    orig_kwargs_fn = getattr(lark_oapi.ws.client, "_ws_connect_kwargs", None)

    def _safe_kwargs():
        kw = orig_kwargs_fn() if orig_kwargs_fn else {}
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            kw["ssl"] = ctx
        except Exception as e:
            logger.warning(f"Failed to create unverified SSL context: {e}")
        return kw

    lark_oapi.ws.client._ws_connect_kwargs = _safe_kwargs


_patch_lark_ws_ssl()


class FeishuWebSocketListener:
    """
    Feishu official Long Connection (WebSocket) listener.
    Requires NO public IP, NO domain, NO server, and NO challenge validation.
    Receives real-time group @mention events and triggers news aggregation & reply.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.pipeline = NewsPipeline(config)
        self.app_id = config.feishu_app_id
        self.app_secret = config.feishu_app_secret

    def _send_quick_text_reply(self, chat_id: str, text: str) -> None:
        """Send a quick plain-text notification to the group."""
        try:
            token = self.pipeline.feishu_sender._get_tenant_access_token()
            if not token:
                return
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            }
            httpx.post(url, headers=headers, json=body, timeout=5.0)
        except Exception as e:
            logger.warning(f"Failed to send quick text reply: {e}")

    def _on_message_received(self, data: P2ImMessageReceiveV1) -> None:
        try:
            event = data.event
            message = event.message
            chat_id = message.chat_id
            content_str = message.content or "{}"

            text = ""
            try:
                content_json = json.loads(content_str)
                text = content_json.get("text", "")
            except Exception:
                text = content_str

            logger.info(f"Received Feishu group message in chat [{chat_id}]: {text}")

            lower_text = text.lower()
            if "新闻" in lower_text or "news" in lower_text:
                logger.info(f"Keyword matched ('新闻'/'news') in chat {chat_id}. Starting news pipeline...")
                # 1. Send immediate response so user sees feedback in Feishu right away
                self._send_quick_text_reply(
                    chat_id,
                    "🤖 收到指令！正在全网检索近3天 AI 重磅动态、实战 Skill、前沿突破与安全资讯，请稍候约 1 分钟...",
                )

                # 2. Run pipeline in background thread to avoid blocking WebSocket loop
                def task():
                    try:
                        res = self.pipeline.run(force_push=True, target_chat_id=chat_id)
                        logger.info(f"On-demand push completed: {res.get('status')}")
                    except Exception as err:
                        logger.error(f"Error running pipeline for chat {chat_id}: {err}", exc_info=True)

                thread = threading.Thread(target=task, daemon=True)
                thread.start()
        except Exception as e:
            logger.error(f"Error handling Feishu WebSocket message: {e}", exc_info=True)

    def start(self) -> None:
        if not self.app_id or not self.app_secret:
            logger.error(
                "❌ 无法启动长连接：请先在 .env 或环境变量中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET！"
            )
            print("\n❌ 启动失败：未检测到 FEISHU_APP_ID 和 FEISHU_APP_SECRET。")
            print("👉 请在 .env 文件中添加：")
            print("FEISHU_APP_ID=cli_xxxxxxxxxxxx")
            print("FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx\n")
            return

        print("=" * 60)
        print("⚡ 正在启动飞书官方「长连接」WebSocket 监听模式...")
        print(f" - App ID: {self.app_id[:6]}******")
        print(" - 监听事件: im.message.receive_v1 (群聊 @机器人 消息)")
        print(" - 触发关键词: '新闻', 'News', 'news'")
        print(" - 状态: 无需公网IP / 无需域名 / 无需Challenge校验")
        print("=" * 60)
        print("👉 注意：要成功接收群内 @消息，请确保在飞书开放平台已完成 3 个配置：")
        print("   1.「事件与回调」-> 点击「添加事件」-> 勾选「接收消息 (im.message.receive_v1)」")
        print("   2.「权限管理」-> 搜索并开通「获取群聊中所有@机器人的消息 (im:message:group_at_msg)」")
        print("   3.「版本管理与发布」->「创建版本」并点击「申请发布」（这一步最重要，发布后权限和事件才会真正生效！）")
        print("=" * 60 + "\n")

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_received)
            .build()
        )

        cli = lark.ws.Client(
            app_id=self.app_id,
            app_secret=self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        # 实时拦截并打印 WebSocket 数据帧，方便秒级排查
        orig_handle_data_frame = cli._handle_data_frame
        async def _debug_handle_data_frame(frame):
            try:
                pl = frame.payload.decode("utf-8", errors="ignore")
                if "im.message.receive_v1" in pl or "chat_id" in pl:
                    print(f"\n📩 [飞书长连接捕获到消息事件]:\n{pl}\n")
            except Exception:
                pass
            return await orig_handle_data_frame(frame)

        cli._handle_data_frame = _debug_handle_data_frame

        try:
            cli.start()
        except KeyboardInterrupt:
            print("\n👋 飞书长连接已停止。")


def start_ws():
    config = load_config()
    listener = FeishuWebSocketListener(config)
    listener.start()


if __name__ == "__main__":
    start_ws()
