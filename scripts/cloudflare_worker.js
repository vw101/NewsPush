/**
 * Cloudflare Worker: 飞书群 @机器人 消息监听与 GitHub Actions 点火转接器
 * 部署说明：直接在 Cloudflare Workers 网页控制台中创建服务并粘贴此代码。
 * 环境变量配置（在 Cloudflare Worker 设置中添加）：
 * - GITHUB_TOKEN: 具有 repo 权限的 GitHub Personal Access Token
 * - GITHUB_REPO: 你的仓库，例如 "vw101/NewsPush"
 */

export default {
  async fetch(request, env, ctx) {
    // 0. 支持浏览器直接打开 GET 检查健康状态
    if (request.method === "GET") {
      return new Response("🤖 Feishu Bot GitHub Actions Relay is RUNNING! Everything is ready.", {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    try {
      const body = await request.json();

      // 1. 响应飞书开放平台 URL 校验 Challenge 请求 (支持各种版本)
      if (body.type === "url_verification" || body.challenge) {
        return new Response(JSON.stringify({ challenge: body.challenge }), {
          headers: { "Content-Type": "application/json" },
        });
      }

      // 2. 监听消息接收事件 (兼容 schema 2.0 的 im.message.receive_v1 与 schema 1.0)
      const eventType = body.header?.event_type || body.event?.type;
      if (eventType === "im.message.receive_v1" || eventType === "message") {
        const event = body.event || {};
        const message = event.message || event;
        const contentStr = message.content || message.text || "{}";

        let text = "";
        try {
          const contentObj = JSON.parse(contentStr);
          text = contentObj.text || "";
        } catch (e) {
          text = contentStr;
        }

        // 检测包含 "新闻", "早报", "资讯", "news" 等关键字，或群内直接 @ 机器人
        const lowerText = text.toLowerCase();
        const hasKeyword =
          lowerText.includes("新闻") ||
          lowerText.includes("news") ||
          lowerText.includes("早报") ||
          lowerText.includes("资讯") ||
          lowerText.includes("日报") ||
          text.trim().length > 0;

        if (hasKeyword) {
          console.log("检测到飞书群 @机器人 新闻触发消息，准备唤醒 GitHub Actions...");

          const repo = env.GITHUB_REPO || "vw101/NewsPush";
          const ghToken = env.GITHUB_TOKEN;

          if (ghToken) {
            ctx.waitUntil(
              fetch(`https://api.github.com/repos/${repo}/dispatches`, {
                method: "POST",
                headers: {
                  "Authorization": `token ${ghToken}`,
                  "Accept": "application/vnd.github.v3+json",
                  "User-Agent": "Cloudflare-Worker-Feishu-Bot",
                },
                body: JSON.stringify({
                  event_type: "feishu_mention_news",
                  client_payload: {
                    triggered_by: event.sender?.sender_id?.open_id || "feishu_user",
                    raw_text: text,
                  },
                }),
              }).then(res => {
                console.log(`GitHub Actions 唤醒结果 HTTP ${res.status}`);
              }).catch(err => {
                console.error("唤醒 GitHub Actions 失败:", err);
              })
            );
          } else {
            console.warn("未设置 GITHUB_TOKEN 环境变量，无法唤醒 GitHub Actions");
          }
        }
      }

      // 3. 秒级响应飞书 200 OK
      return new Response(JSON.stringify({ msg: "success" }), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (err) {
      console.error("处理事件回调发生异常:", err);
      return new Response(JSON.stringify({ msg: "error", detail: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
