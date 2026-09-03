# 🤖 AI Daily Pulse · 每日 AI 资讯聚合与飞书卡片推送系统

一个专为开发者和 AI 爱好者设计的全自动 AI 资讯聚合与精炼推送工具。每天定时自动从全球顶尖官方博客、Hacker News、GitHub Trending、Hugging Face Papers、arXiv 及国内前沿科技媒体抓取最新资讯，经由大模型（LLM）进行智能降噪、评分与精简提炼，最后以**高颜值飞书富文本交互卡片**的形式推送到飞书群中。

---

## ✨ 核心特性

- 🌐 **全网一手信源覆盖**：预置 OpenAI/DeepMind 官方博客、Hacker News 热点、GitHub Trending 开源项目、Hugging Face 顶会论文、arXiv、量子位与机器之心。
- 🧠 **大模型智能甄别与降噪**：自动过滤公关水文与广告，提炼 **Top 3 今日重磅头条** 与 4 大分类要点（一句话核心 + 为什么重要 + 原文直达）。
- 🔌 **兼容 OpenAI 协议的通用 LLM 引擎**：支持 DeepSeek、OpenAI、Claude、Gemini、智谱 GLM、硅基流动或本地 Ollama，自由无缝切换。
- 📱 **飞书富文本交互卡片**：精心设计的卡片排版，支持分类、标签、重点高亮与一键跳转，移动端/桌面端阅读体验极佳。
- 🔄 **智能增量去重**：内置历史记录缓存机制，自动过滤已推送文章，避免重复打扰。
- ☁️ **GitHub Actions 零成本定时运行**：无需购买服务器，利用 GitHub Actions 每天早上 08:30（北京时间）全自动无服务器运行并归档。
- 📦 **本地 Markdown 每日归档**：自动在 `archives/` 目录下生成每日简报 Markdown 文件，方便随时回溯与知识库检索。

---

## 🏗️ 飞书卡片效果预览

```text
┌────────────────────────────────────────────────────────┐
│ 🤖 AI Daily Pulse · 每日早报 (2026年09月02日 星期三)   │
├────────────────────────────────────────────────────────┤
│ 🔥 今日最重磅头条 (Top Headlines)                      │
│ 1. [DeepSeek 发布全新开源推理架构]                     │
│    💡 核心要点：大幅降低长文本推理显存占用 60%        │
│    🎯 关键影响：轻量化部署门槛显著降低，利好终端落地    │
│    🏷️ 信源：GitHub Trending · 直达原文 ↗              │
│ ────────────────────────────────────────────────────── │
│ 🏢 行业大厂与重磅发布                                   │
│ • [OpenAI 新版 API 正式开放结构化调用]                │
│   全面提升 JSON schema 遵循度与长链路稳定性            │
│ ────────────────────────────────────────────────────── │
│ 💻 开源生态与开发者工具                                 │
│ • [vLLM 发布新版本支持多模态流水线并行]                │
│ ────────────────────────────────────────────────────── │
│ 🔬 学术前沿与热门论文                                   │
│ • [HuggingFace 论文精选：高效 Agent 规划算法]          │
│ ────────────────────────────────────────────────────── │
│ 🤖 AI Daily Pulse 自动化聚合 · 本期扫描 42 篇信源      │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 快速上手 (本地运行)

### 1. 克隆与安装依赖

```bash
cd NewsApp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件填入你的配置：

```ini
# OpenRouter 模型配置 (https://openrouter.ai/)
LLM_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-chat  # 也可填 anthropic/claude-3.5-sonnet, google/gemini-2.5-flash 等

# 飞书群自定义机器人 Webhook
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 3. 测试与运行

```bash
# 测试飞书 Webhook 连通性（向群内发送一张测试欢迎卡片）
python run.py --test-feishu

# 演练预览模式（抓取 + LLM提炼 + 生成本地 Markdown，但不推送到飞书）
python run.py --dry-run

# 正式执行并推送到飞书
python run.py

# 强制推送（忽略历史去重缓存）
python run.py --force
```

---

## 🤖 飞书机器人 Webhook 获取指南（1 分钟）

1. 打开飞书群聊，点击右上角 **「设置」 -> 「群机器人」 -> 「添加机器人」**。
2. 选择 **「自定义机器人」**，设置名称为例如 `AI 资讯早报`，头像可上传 AI 相关图标。
3. 添加后复制生成的 **Webhook 地址**。
4. 将该地址粘贴至 `.env` 中的 `FEISHU_WEBHOOK_URL` 即可。

---

## ☁️ 100% 部署到 GitHub Actions (0 成本无服务器自动运行)

本项目预置了 GitHub Actions 工作流文件 [`.github/workflows/daily_push.yml`](.github/workflows/daily_push.yml)，每天北京时间 **09:00** 自动触发抓取、提炼与推送。

### 部署步骤：

1. 将本项目推送到你的 GitHub 私有/公开仓库 `https://github.com/vw101/NewsPush.git`
2. 在 GitHub 仓库页面中，进入 **Settings -> Secrets and variables -> Actions**。
3. 点击 **New repository secret**，添加以下密钥：
   - `LLM_API_KEY`: 你的大模型 API 密钥（如 DeepSeek key）
   - `LLM_BASE_URL`: API 地址（如 `https://openrouter.ai/api/v1`）
   - `LLM_MODEL`: 模型名称（如 `deepseek/deepseek-chat`）
   - `FEISHU_WEBHOOK_URL`: 你的飞书群 Webhook 地址
   - `FEISHU_SECRET`: （可选）如启用了安全加签则填写
4. 开启仓库自动提交权限（用于 Actions 自动同步历史去重记录）：
   - 进入 **Settings -> Actions -> General -> Workflow permissions**。
   - 勾选 **「Read and write permissions」** 并保存。
5. 点击仓库顶部 **Actions** 标签页，在左侧选择 **AI Daily News Push**，点击 **Run workflow** 即可随时手动触发一次测试！

---

## ⚡ 100% GitHub 原生：飞书 @机器人 消息唤醒指南

当你在飞书群内 `@机器人` 并且消息包含 **“新闻”**、**“News”** 或 **“news”** 时，可以直接通过 GitHub 官方 REST API 秒级唤醒 GitHub Actions 云端 Runner 执行全量新闻收集与卡片推送：

```bash
# 唤醒 GitHub Actions 的标准 REST API 请求
curl -X POST \
  -H "Authorization: token YOUR_GITHUB_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/vw101/NewsPush/dispatches \
  -d '{"event_type": "feishu_mention_news"}'
```

---

## ⚙️ 自定义与扩展数据源

所有数据源均集中在 [`config/sources.yaml`](config/sources.yaml) 中进行管理。你可以随时添加你喜欢的 RSS 链接或关闭不关注的源：

```yaml
sources:
  - name: "OpenAI Blog"
    category: "industry" # 分类：industry / opensource / research / tools
    type: "rss"
    url: "https://openai.com/news/rss.xml"
    enabled: true
    max_items: 5
```

---

## 📁 目录结构

```text
NewsApp/
├── .github/workflows/daily_push.yml   # GitHub Actions 定时任务
├── config/
│   ├── config.yaml                    # 全局参数配置（标题、分类、条数）
│   └── sources.yaml                   # 采集源列表配置
├── data/
│   └── history.json                   # 历史已推送文章缓存（去重用）
├── archives/                          # 每日生成的 Markdown 归档
├── src/
│   ├── fetchers/                      # RSS、GitHub、HuggingFace 采集器
│   ├── processors/                    # 历史去重与 LLM 智能分类提炼
│   ├── formatters/                    # 飞书卡片与 Markdown 格式化
│   ├── senders/                       # 飞书 Webhook 消息发送
│   ├── config.py                      # 配置解析
│   └── pipeline.py                    # 核心流水线
├── run.py                             # 命令行入口
├── requirements.txt                   # 依赖列表
└── README.md                          # 说明文档
```

---

## 📄 License

MIT License.
