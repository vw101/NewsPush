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
                verify=False,
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

    def send_text_to_chat(self, chat_id: str, text: str) -> bool:
        """Fallback method: send plain text directly to chat group."""
        token = self._get_tenant_access_token()
        if not token:
            return False
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text[:3000]}),
        }
        try:
            with httpx.Client(timeout=15.0, verify=False) as client:
                resp = client.post(url, headers=headers, json=body)
                data = resp.json()
                if data.get("code") == 0:
                    logger.info("Successfully pushed text fallback to Feishu chat!")
                    return True
                logger.error(f"Feishu text fallback failed: {data.get('code')} - {data.get('msg')}")
                return False
        except Exception as e:
            logger.error(f"Error sending text fallback: {e}")
            return False

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
                with httpx.Client(timeout=15.0, verify=False) as client:
                    resp = client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    code = data.get("code")
                    if code == 0:
                        logger.info(f"Successfully pushed digest card to Feishu chat: {chat_id}!")
                        return True
                    else:
                        hint = ""
                        if code == 11310:
                            hint = " (11310: 卡片内容超出飞书限制，如组件数超过200个)"
                        logger.error(f"Feishu OpenAPI error: {code} - {data.get('msg')}{hint}")
                        return False
            except Exception as e:
                logger.warning(f"[Attempt {attempt}/{max_retries}] Failed to send to chat {chat_id}: {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
        return False

    def send(
        self,
        card_payload: Dict[str, Any],
        chat_id: Optional[str] = None,
        max_retries: int = 3,
        fallback_card: Optional[Dict[str, Any]] = None,
        fallback_text: Optional[str] = None,
    ) -> bool:
        """
        Main delivery entry point with automatic fallback.
        1. Try primary card_payload
        2. On failure (e.g. 11310 element limit), try fallback_card (compact card)
        3. If still failing, try fallback_text (plain/markdown text)
        """
        target_chat = chat_id or self.chat_id
        success = False

        if self.app_id and self.app_secret and target_chat:
            success = self.send_to_chat(target_chat, card_payload, max_retries=max_retries)
            if not success and fallback_card:
                logger.warning("Primary card failed. Triggering Tier-2 Fallback: sending compact card...")
                success = self.send_to_chat(target_chat, fallback_card, max_retries=1)
            if not success and fallback_text:
                logger.warning("Compact card failed. Triggering Tier-3 Fallback: sending text message...")
                success = self.send_text_to_chat(target_chat, fallback_text)
            return success

        if not self.webhook_url or self.webhook_url == "your_token_here":
            if self.app_id and self.app_secret and not target_chat:
                logger.error("FEISHU_APP_ID configured but FEISHU_CHAT_ID is missing. Please set FEISHU_CHAT_ID.")
            else:
                logger.error("Neither Feishu Webhook URL nor App ID/Chat ID is configured. Skipping sending.")
            return False

        # Webhook delivery path
        def _post_webhook(payload: Dict[str, Any]) -> bool:
            for attempt in range(1, max_retries + 1):
                try:
                    with httpx.Client(timeout=15.0, verify=False) as client:
                        resp = client.post(
                            self.webhook_url,
                            json=payload,
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
                            if code == 11310:
                                error_hint = "\n👉 原因诊断 [11310 卡片创建失败]: 卡片元素超过飞书 200 上限或组件嵌套结构异常。"
                            elif code == 19021:
                                error_hint = (
                                    "\n👉 原因诊断 [19021 签名校验失败]: 飞书机器人开启了签名校验，请在机器人安全设置检查或配置 FEISHU_SECRET。"
                                )
                            elif code == 19024:
                                error_hint = "\n👉 原因诊断 [19024 IP白名单拦截]: 飞书机器人开启了 IP 白名单限制。"
                            elif code == 19007:
                                error_hint = "\n👉 原因诊断 [19007 机器人已被停用或删除]: 请更新 Webhook URL 或改用企业自建应用推送。"

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
            return False

        success = _post_webhook(card_payload)
        if not success and fallback_card:
            logger.warning("Primary webhook card failed. Triggering Tier-2 Fallback: sending compact card...")
            success = _post_webhook(fallback_card)
        if not success and fallback_text:
            logger.warning("Compact card failed. Triggering Tier-3 Fallback: sending text...")
            text_payload = {"msg_type": "text", "content": {"text": fallback_text[:3000]}}
            success = _post_webhook(text_payload)

        return success
