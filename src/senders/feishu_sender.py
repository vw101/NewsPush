import logging
import time
from typing import Any, Dict
import httpx

logger = logging.getLogger(__name__)


class FeishuSender:
    """
    Sends interactive card payloads to Feishu Webhook with retry and diagnostic handling.
    """

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip()

    def send(self, card_payload: Dict[str, Any], max_retries: int = 3) -> bool:
        if not self.webhook_url or self.webhook_url == "your_token_here":
            logger.error("Feishu Webhook URL is not configured. Skipping sending.")
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

                    # Feishu returns {"code": 0, "msg": "success"} on success
                    code = res_data.get("code")
                    if code == 0 or res_data.get("StatusCode") == 0:
                        logger.info("Successfully pushed daily digest to Feishu!")
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
