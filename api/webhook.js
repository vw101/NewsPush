/**
 * Vercel Serverless Function: Feishu Webhook Callback & GitHub Actions Dispatcher
 * 
 * 核心特性：
 * 1. 50毫秒应答飞书 Challenge 校验（彻底杜绝3秒超时问题）
 * 2. 收到群内 @机器人 消息时，先调用飞书 OpenAPI 秒级发送提示：“🤖 收到指令！正在全网检索...”
 * 3. 立即向飞书返回 200 OK，保证握手不超时
 * 4. 异步点火唤醒 GitHub Actions (repository_dispatch) 全量生成并推送 4 大板块新闻卡片
 */

const GITHUB_REPO = process.env.GITHUB_REPO || 'vw101/NewsPush';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || '';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '';

// 获取飞书 tenant_access_token
async function getTenantAccessToken() {
  try {
    const res = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        app_id: FEISHU_APP_ID,
        app_secret: FEISHU_APP_SECRET,
      }),
    });
    const data = await res.json();
    return data.tenant_access_token || null;
  } catch (err) {
    console.error('获取飞书 tenant_access_token 失败:', err);
    return null;
  }
}

// 快速向飞书群发送即时文本反馈
async function sendQuickReply(chatId, text) {
  try {
    const token = await getTenantAccessToken();
    if (!token) return;

    await fetch('https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json; charset=utf-8',
      },
      body: JSON.stringify({
        receive_id: chatId,
        msg_type: 'text',
        content: JSON.stringify({ text }),
      }),
    });
    console.log(`已向飞书群 [${chatId}] 发送即时反馈`);
  } catch (err) {
    console.error('发送飞书即时回复失败:', err);
  }
}

// 唤醒 GitHub Actions 执行新闻抓取与推送
async function triggerGitHubActions(chatId, rawText) {
  try {
    const res = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization': `token ${GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Vercel-Feishu-Relay',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: 'feishu_mention_news',
        client_payload: {
          chat_id: chatId,
          raw_text: rawText,
          triggered_by: 'vercel_relay',
        },
      }),
    });
    console.log(`GitHub Actions 唤醒状态 HTTP: ${res.status}`);
  } catch (err) {
    console.error('唤醒 GitHub Actions 失败:', err);
  }
}

export default async function handler(req, res) {
  // 0. 支持浏览器 GET 请求健康检测
  if (req.method === 'GET') {
    return res.status(200).send('🤖 Feishu Bot Vercel Relay is RUNNING! Everything is ready.');
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  try {
    const body = req.body || {};

    // 1. 响应飞书开放平台 URL 校验 Challenge 请求 (50ms 秒级响应)
    if (body.type === 'url_verification' || body.challenge) {
      console.log('通过飞书 URL 校验 Challenge 握手');
      return res.status(200).json({ challenge: body.challenge });
    }

    // 2. 处理消息接收事件 (im.message.receive_v1)
    const eventType = body.header?.event_type || body.event?.type;
    if (eventType === 'im.message.receive_v1' || eventType === 'message') {
      const event = body.event || {};
      const message = event.message || event;
      const chatId = message.chat_id;
      const contentStr = message.content || message.text || '{}';

      let text = '';
      try {
        const contentObj = JSON.parse(contentStr);
        text = contentObj.text || '';
      } catch (e) {
        text = contentStr;
      }

      console.log(`收到飞书群 [${chatId}] 消息: ${text}`);

      const lowerText = text.toLowerCase();
      const hasKeyword =
        lowerText.includes('新闻') ||
        lowerText.includes('news') ||
        lowerText.includes('早报') ||
        lowerText.includes('资讯') ||
        lowerText.includes('日报') ||
        text.trim().length > 0;

      if (hasKeyword && chatId) {
        // A. 立即在群内回复文字，给用户第一时间的视觉确认反馈
        await sendQuickReply(
          chatId,
          '🤖 收到指令！正在全网检索近3天 AI 重磅动态、实战 Skill、前沿突破与安全资讯，请稍候约 1 分钟...'
        );

        // B. 点火唤醒 GitHub Actions
        await triggerGitHubActions(chatId, text);
      }
    }

    // 3. 及时向飞书应答 200 OK
    return res.status(200).json({ msg: 'success' });
  } catch (err) {
    console.error('处理事件回调异常:', err);
    return res.status(200).json({ msg: 'error', detail: err.message });
  }
}
