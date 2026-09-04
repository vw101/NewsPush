/**
 * 阿里云函数计算 FC 3.0 / 2.0: 飞书事件回调与 GitHub Actions 点火网关
 * 
 * 核心设计：
 * 1. 【双模自适应】：同时兼容 Web 函数 (req, resp) 与事件函数 (event, context)，开箱即用零踩坑。
 * 2. 【50ms 秒级握手】：收到飞书 url_verification challenge 时，极速原样返回，彻底解决“3秒超时”问题。
 * 3. 【即时群内冒泡】：群内收到 @指令 后，200ms 内先在群里发送“正在全网检索”提示，消除等待焦虑。
 * 4. 【异步点火】：调用 GitHub API 唤醒 GitHub Actions (repository_dispatch)，启动云端容器抓取、AI 总结并推送大卡片。
 * 5. 【环境变量注入】：通过 process.env 安全读取密钥，代码无任何硬编码。
 */

const https = require('https');

// 从环境变量读取配置
const GITHUB_REPO = process.env.GITHUB_REPO || 'vw101/NewsPush';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || '';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '';

// 基础 HTTPS POST 请求封装（纯原生，零第三方 npm 依赖）
function httpsPost(urlStr, headers, bodyObj) {
  return new Promise((resolve, reject) => {
    try {
      const url = new URL(urlStr);
      const postData = JSON.stringify(bodyObj);
      const req = https.request({
        hostname: url.hostname,
        port: 443,
        path: url.pathname + url.search,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Length': Buffer.byteLength(postData),
          ...headers,
        },
        timeout: 5000,
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          } catch (e) {
            resolve({ status: res.statusCode, text: data });
          }
        });
      });

      req.on('error', err => reject(err));
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('HTTPS Request Timeout'));
      });
      req.write(postData);
      req.end();
    } catch (e) {
      reject(e);
    }
  });
}

// 获取飞书 tenant_access_token
async function getTenantAccessToken() {
  if (!FEISHU_APP_ID || !FEISHU_APP_SECRET) return null;
  try {
    const res = await httpsPost(
      'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
      {},
      { app_id: FEISHU_APP_ID, app_secret: FEISHU_APP_SECRET }
    );
    return res.data?.tenant_access_token || null;
  } catch (err) {
    console.error('获取飞书 tenant_access_token 失败:', err);
    return null;
  }
}

// 快速向飞书群发送预热文字反馈
async function sendQuickReply(chatId, text) {
  try {
    const token = await getTenantAccessToken();
    if (!token) return;

    await httpsPost(
      'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id',
      { 'Authorization': `Bearer ${token}` },
      {
        receive_id: chatId,
        msg_type: 'text',
        content: JSON.stringify({ text }),
      }
    );
    console.log(`已向飞书群 [${chatId}] 发送即时反馈消息`);
  } catch (err) {
    console.error('发送飞书即时回复失败:', err);
  }
}

// 唤醒 GitHub Actions 点火执行
async function triggerGitHubActions(chatId, rawText) {
  if (!GITHUB_TOKEN) {
    console.warn('未配置 GITHUB_TOKEN，跳过唤醒 GitHub Actions');
    return;
  }
  try {
    const res = await httpsPost(
      `https://api.github.com/repos/${GITHUB_REPO}/dispatches`,
      {
        'Authorization': `token ${GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Aliyun-FC-Feishu-Relay',
      },
      {
        event_type: 'feishu_mention_news',
        client_payload: {
          chat_id: chatId,
          raw_text: rawText,
          triggered_by: 'aliyun_fc',
        },
      }
    );
    console.log(`GitHub Actions 唤醒结果 HTTP: ${res.status}`);
  } catch (err) {
    console.error('唤醒 GitHub Actions 异常:', err);
  }
}

// 业务核心入口
async function processRequest(method, rawBody) {
  if (method === 'GET') {
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      body: '🤖 阿里云 FC 飞书机器人转接器已就绪！',
    };
  }

  let body = {};
  if (rawBody) {
    body = typeof rawBody === 'string' ? JSON.parse(rawBody) : rawBody;
  }

  // 1. 响应飞书开放平台 URL 校验 Challenge 请求 (50ms 秒级响应)
  if (body.type === 'url_verification' || body.challenge) {
    console.log('通过飞书 URL 校验 Challenge 握手');
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ challenge: body.challenge }),
    };
  }

  // 2. 处理群内 @机器人 消息事件
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
      // A. 先在群里回显预热提示（约 150ms 完成）
      await sendQuickReply(
        chatId,
        '🤖 收到指令！正在全网检索近3天 AI 重磅动态、实战 Skill、前沿突破与安全资讯，请稍候约 1 分钟...'
      );

      // B. 异步点火唤醒 GitHub Actions
      await triggerGitHubActions(chatId, text);
    }
  }

  return {
    statusCode: 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ msg: 'success' }),
  };
}

/**
 * 阿里云 FC 入口（双模自适应）
 */
exports.handler = async (arg1, arg2, context) => {
  // 判断是否为 Web 函数模式：arg1 是 req，arg2 是 resp
  if (arg2 && typeof arg2.send === 'function') {
    const req = arg1;
    const resp = arg2;
    try {
      const result = await processRequest(req.method, req.body);
      resp.setStatusCode(result.statusCode);
      for (const [k, v] of Object.entries(result.headers)) {
        resp.setHeader(k, v);
      }
      resp.send(result.body);
    } catch (err) {
      console.error('处理发生异常:', err);
      resp.setStatusCode(200);
      resp.setHeader('Content-Type', 'application/json');
      resp.send(JSON.stringify({ msg: 'error', detail: err.message }));
    }
    return;
  }

  // 事件函数 (Event Function) 模式：arg1 是 event Buffer/string
  try {
    let eventStr = arg1 ? (Buffer.isBuffer(arg1) ? arg1.toString('utf-8') : arg1) : '{}';
    let eventObj = {};
    try { eventObj = JSON.parse(eventStr); } catch (e) { eventObj = {}; }

    const method = eventObj.httpMethod || eventObj.method || 'POST';
    const rawBody = eventObj.body || eventStr;

    return await processRequest(method, rawBody);
  } catch (err) {
    console.error('事件函数处理异常:', err);
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg: 'error', detail: err.message }),
    };
  }
};
