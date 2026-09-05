/**
 * 阿里云函数计算 FC 3.0 / 2.0: 飞书事件回调与 GitHub Actions 点火网关 (双向赋能版)
 * 
 * 核心功能：
 * 1. 【Web 函数端口监听】：启动 HTTP Server 监听 9000 端口，双模兼容 (Web 函数 / 事件函数)。
 * 2. 【50ms 秒级握手】：收到飞书 url_verification challenge 时，极速原样返回，杜绝超时。
 * 3. 【即时群内冒泡】：群内收到 @机器人 指令后，200ms 内先在群里发送“正在全网检索”提示，消除等待焦虑。
 * 4. 【⏰ 定时触发执行】：支持阿里云 FC 定时触发器（Timer Trigger / Cron），并在指定时间（如每天 09:00）自动唤醒 GitHub Actions 推送早报。
 * 5. 【🔗 HTTP 手动点火】：支持 GET/POST /cron 或 /timer，可由外部定时器（如 UptimeKuma/cron-job）或浏览器一键手动点火。
 * 6. 【异步点火】：调用 GitHub API 唤醒 GitHub Actions (repository_dispatch)，执行云端全流程抓取、AI 总结与大卡片推送。
 */

const http = require('http');
const https = require('https');

// 从环境变量读取配置
const GITHUB_REPO = process.env.GITHUB_REPO || 'vw101/NewsPush';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || '';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '';
const FEISHU_CHAT_ID = process.env.FEISHU_CHAT_ID || 'oc_41144adb848366fd8a1ac77bc8d40d7d';
const PORT = process.env.FC_SERVER_PORT || 9000;

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
        timeout: 8000,
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
async function triggerGitHubActions(chatId, rawText, triggerSource = 'aliyun_fc') {
  if (!GITHUB_TOKEN) {
    console.warn('未配置 GITHUB_TOKEN，跳过唤醒 GitHub Actions');
    return { ok: false, error: 'No GITHUB_TOKEN' };
  }
  try {
    const targetChat = chatId || FEISHU_CHAT_ID;
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
          chat_id: targetChat,
          raw_text: rawText,
          triggered_by: triggerSource,
        },
      }
    );
    console.log(`GitHub Actions 唤醒结果 HTTP: ${res.status} (来源: ${triggerSource}, 目标群: ${targetChat})`);
    return { ok: res.status >= 200 && res.status < 300, status: res.status };
  } catch (err) {
    console.error('唤醒 GitHub Actions 异常:', err);
    return { ok: false, error: err.message };
  }
}

// 业务核心处理逻辑
async function processRequest(method, rawBody, reqUrl = '/', reqHeaders = {}) {
  const urlPath = reqUrl.split('?')[0].toLowerCase();
  const isHttpCronPath = urlPath.includes('/cron') || urlPath.includes('/timer') || urlPath.includes('/schedule') || urlPath.includes('/trigger');

  // 处理 GET 请求
  if (method === 'GET') {
    if (isHttpCronPath) {
      console.log(`⏰ 收到 HTTP GET 定时/手动点火请求: ${reqUrl}`);
      const ghResult = await triggerGitHubActions(FEISHU_CHAT_ID, 'HTTP GET 定时早报点火', 'aliyun_fc_http_cron');
      return {
        statusCode: 200,
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({
          code: 0,
          msg: 'HTTP GET 早报定时任务点火成功',
          targetChatId: FEISHU_CHAT_ID,
          githubResult: ghResult,
          triggeredAt: new Date().toISOString(),
        }),
      };
    }

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      body: '🤖 阿里云 FC 飞书机器人转接器已就绪！\n- 支持飞书群 @机器人 事件回调\n- 支持阿里云 FC 定时触发器 (Timer Trigger)\n- 支持 HTTP GET/POST /cron 随时点火',
    };
  }

  let body = {};
  if (rawBody) {
    try {
      body = typeof rawBody === 'string' ? JSON.parse(rawBody) : rawBody;
    } catch (e) {
      console.warn('解析请求 Body 失败，当作原始字符串处理:', e.message);
      body = { rawText: String(rawBody) };
    }
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

  // 2. 识别并执行定时触发器 (阿里云 FC Timer Trigger 或 HTTP /cron 触发)
  const isTimerTrigger = Boolean(
    body.triggerTime ||
    body.triggerName ||
    (reqHeaders && (reqHeaders['x-fc-event'] === 'timer' || reqHeaders['x-fc-trigger-type'] === 'timer')) ||
    isHttpCronPath ||
    body.type === 'timer' ||
    body.action === 'timer' ||
    body.payload === 'timer'
  );

  if (isTimerTrigger) {
    let innerPayload = {};
    if (typeof body.payload === 'string' && body.payload.trim().startsWith('{')) {
      try { innerPayload = JSON.parse(body.payload); } catch (_) {}
    }

    const targetChatId = innerPayload.chat_id || body.chat_id || FEISHU_CHAT_ID;
    const triggerName = body.triggerName || 'daily-timer';
    console.log(`⏰ 收到定时触发器 [${triggerName}]，正在唤醒 GitHub Actions... (目标群: ${targetChatId})`);

    const ghResult = await triggerGitHubActions(targetChatId, '定时早报点火', 'aliyun_fc_timer');

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        code: 0,
        msg: 'Timer trigger processed successfully',
        triggerName,
        targetChatId,
        githubResult: ghResult,
        triggerTime: body.triggerTime || new Date().toISOString(),
      }),
    };
  }

  // 3. 处理飞书群内 @机器人 消息事件
  const eventType = body.header?.event_type || body.event?.type;
  if (eventType === 'im.message.receive_v1' || eventType === 'message') {
    const event = body.event || {};
    const message = event.message || event;
    const chatId = message.chat_id || FEISHU_CHAT_ID;
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
      // 并行执行群内回显与 GitHub 点火，加设 1.8 秒竞速截断，彻底杜绝飞书 3 秒超时重发
      const tasks = [
        sendQuickReply(
          chatId,
          '🤖 收到指令！正在全网检索近3天 AI 重磅动态、实战 Skill、前沿突破与安全资讯，请稍候约 1 分钟...'
        ),
        triggerGitHubActions(chatId, text, 'feishu_mention'),
      ];

      await Promise.race([
        Promise.allSettled(tasks),
        new Promise(resolve => setTimeout(resolve, 1800)),
      ]);
    }
  }

  return {
    statusCode: 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ msg: 'success' }),
  };
}

// 1. 创建 HTTP 服务器（监听 9000 端口，满足 FC Web 函数容器化要求）
const server = http.createServer((req, res) => {
  let bodyChunks = [];
  req.on('data', chunk => bodyChunks.push(chunk));
  req.on('end', async () => {
    try {
      const rawBody = Buffer.concat(bodyChunks).toString('utf-8');
      const result = await processRequest(req.method, rawBody, req.url, req.headers);
      res.writeHead(result.statusCode, result.headers);
      res.end(result.body);
    } catch (err) {
      console.error('Server 处理异常:', err);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ msg: 'error', detail: err.message }));
    }
  });
});

server.listen(PORT, () => {
  console.log(`🚀 阿里云 FC Web 函数服务正在监听端口: ${PORT}`);
});

// 2. 同时导出 exports.handler，兼容事件函数模式
exports.handler = async (arg1, arg2, context) => {
  // Case 1: FC HTTP 触发器 (req, res, context)
  if (arg2 && typeof arg2.send === 'function') {
    const result = await processRequest(arg1.method, arg1.body, arg1.path || arg1.url, arg1.headers);
    arg2.setStatusCode(result.statusCode);
    for (const [k, v] of Object.entries(result.headers)) {
      arg2.setHeader(k, v);
    }
    arg2.send(result.body);
    return;
  }
  // Case 2: FC 定时触发器 / 事件触发器 (event, context)
  let eventStr = arg1 ? (Buffer.isBuffer(arg1) ? arg1.toString('utf-8') : (typeof arg1 === 'string' ? arg1 : JSON.stringify(arg1))) : '{}';
  return await processRequest('POST', eventStr, '/timer', { 'x-fc-event': 'timer' });
};
