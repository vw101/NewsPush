import json
import logging
import time
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


class FeishuSender:
    """
    Sends interactive card payloads to Feishu via:
    1. Enterprise App OpenAPI (tenant_access_token to specific chat_id)
    2. Custom Bot Webhook (with signature verification if secret present)
    """

    def __init__(
        self,
        webhook_url: str = "",
        app_id: str = "",
        app_secret: str = "",
        chat_id: str = "",
    ):
        self.webhook_url = webhook_url.strip() if webhook_url else ""
        self.app_id = app_id.strip() if app_id else ""
        self.app_secret = app_secret.strip() if app_secret else ""
        self.chat_id = chat_id.strip() if chat_id else ""
        self._tenant_token: Optional[str] = None
        self._token_expires_at: float = 0

    def _get_tenant_access_token(self) -> Optional[str]:
        """Obtain or refresh tenant_access_token for Enterprise App."""
        if not self.app_id or not self.app_secret:
            return None

        if self._tenant_token and time.time() < self._token_expires_at:
            return self._tenant_token

        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            resp = httpx.post(
                url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10.0,
            )
            data = resp.json()
            if data.get("code") == 0:
                self._tenant_token = data.get("tenant_access_token")
                self._token_expires_at = time.time() + data.get("expire", 7200) - 60
                return self._tenant_token
            else:
                logger.error(f"Feishu token acquisition failed: {data.get('msg')}")
                return None
        except Exception as e:
            logger.error(f"Error requesting tenant_access_token: {e}")
            return None

    def send_to_chat(self, chat_id: str, card_payload: Dict[str, Any], max_retries: int = 3) -> bool:
        """Send interactive card to a specific Feishu chat group using Enterprise App OpenAPI."""
        token = self._get_tenant_access_token()
        if not token:
            logger.error("Unable to obtain Feishu tenant_access_token. Check FEISHU_APP_ID and FEISHU_APP_SECRET.")
            return False

        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        card_content = card_payload.get("card", card_payload)
        body = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content),
        }

        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("code") == 0:
                        logger.info(f"Successfully pushed digest card to Feishu chat: {chat_id}!")
                        return True
                    else:
                        logger.error(f"Feishu OpenAPI error: {data.get('code')} - {data.get('msg')}")
                        return False
            except Exception as e:
                logger.warning(f"[Attempt {attempt}/{max_retries}] Failed to send to chat {chat_id}: {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
        return False

    def send(self, card_payload: Dict[str, Any], chat_id: Optional[str] = None, max_retries: int = 3) -> bool:
        target_chat = chat_id or self.chat_id
        if self.app_id and self.app_secret and target_chat:
            return self.send_to_chat(target_chat, card_payload, max_retries=max_retries)

        if not self.webhook_url or self.webhook_url == "your_token_here":
            if self.app_id and self.app_secret and not target_chat:
                logger.error("FEISHU_APP_ID configured but FEISHU_CHAT_ID is missing. Please set FEISHU_CHAT_ID.")
            else:
                logger.error("Neither Feishu Webhook URL nor App ID/Chat ID is configured. Skipping sending.")
            return False

        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        self.webhook_url,
                        json=card_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    res_data = resp.json()

                    code = res_data.get("code")
                    if code == 0 or res_data.get("StatusCode") == 0:
                        logger.info("Successfully pushed daily digest to Feishu Webhook!")
                        return True
                    else:
                        msg = res_data.get("msg", "")
                        error_hint = ""
                        if code == 19021:
                            error_hint = (
                                "\n👉 原因诊断 [19021 签名校验失败]:\n"
                                "   1. 你的飞书机器人在创建时开启了「签名校验」安全设置。\n"
                                "   2. 解决方案 A (推荐): 打开飞书群 -> 设置 -> 群机器人 -> 点击你的机器人 -> 查看「安全设置」-> 取消勾选「签名校验」即可立即生效。\n"
                                "   3. 解决方案 B: 复制飞书机器人设置中的「密钥」，填入 .env 的 FEISHU_SECRET=你的密钥"
                            )
                        elif code == 19024:
                            error_hint = (
                                "\n👉 原因诊断 [19024 IP白名单拦截]:\n"
                                "   你的飞书机器人开启了 IP 白名单限制，请在飞书机器人设置中移除 IP 限制或添加本机 IP。"
                            )
                        elif code == 19022:
                            error_hint = (
                                "\n👉 原因诊断 [19022 关键词匹配失败]:\n"
                                "   你的飞书机器人开启了「自定义关键词」限制，请在设置中取消勾选。"
                            )

                        logger.error(
                            f"Feishu webhook responded with error code {code}: {msg}{error_hint}"
                        )
                        return False
            except Exception as e:
                logger.warning(
                    f"[Attempt {attempt}/{max_retries}] Failed to send Feishu message: {e}"
                )
                if attempt < max_retries:
                    time.sleep(2 * attempt)

        logger.error(f"Failed to send Feishu message after {max_retries} attempts.")
        return False
