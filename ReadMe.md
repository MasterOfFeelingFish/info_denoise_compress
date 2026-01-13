# Web3 Daily Digest

> AI 驱动的 Web3 个性化信息聚合服务

每天从海量信息中筛选出真正有价值的内容，10 分钟看完，不错过任何重要信息。

## 核心特点

- **AI 个性化筛选** - 基于用户画像的 LLM 语义理解，不是关键词匹配
- **对话式偏好设置** - 3 轮 AI 对话完成偏好收集，无需填表
- **价值可感知** - 每份简报展示"扫描了多少、精选了多少、节省了多少时间"
- **反馈学习闭环** - 用户反馈 → AI 分析 → 画像更新 → 推送越来越准
- **自然语言画像** - 用户偏好以自然语言描述，AI 自己决定如何使用

---

## 功能概览

```
用户注册 → AI 对话收集偏好 → 每日自动抓取 → AI 智能筛选 → 生成简报 → Telegram 推送
                                    ↑                                         ↓
                                    └──────── AI 分析反馈，更新用户画像 ←──────┘
```

### Bot 命令

| 命令 | 功能 |
|------|------|
| `/start` | 主菜单 / 新用户注册流程 |
| `/settings` | 查看/更新/重置偏好设置 |
| `/sources` | 管理信息源 (Twitter/网站) |
| `/stats` | 查看个人统计 |
| `/help` | 帮助信息 |

### 已实现功能

- [x] Telegram Bot 完整交互
- [x] 3 轮 AI 对话注册流程
- [x] RSS 异步抓取 (Twitter + 网站)
- [x] AI 内容筛选与排序
- [x] 个性化简报生成
- [x] 每日定时推送
- [x] 用户反馈收集
- [x] AI 反馈学习闭环
- [x] Docker 部署

---

## 技术栈

| 模块 | 技术 |
|------|------|
| Bot 框架 | python-telegram-bot v22 |
| HTTP 客户端 | httpx (异步) |
| RSS 解析 | feedparser |
| 定时任务 | telegram JobQueue |
| LLM | Google Gemini 3 Pro REST API |
| 数据存储 | JSON 文件 |

---

## 项目结构

```
.
├── bot/                          # Telegram Bot (Python)
│   ├── main.py                   # 入口 + 定时任务
│   ├── config.py                 # 配置管理
│   ├── handlers/                 # 命令处理器
│   │   ├── start.py              # /start + 注册流程
│   │   ├── settings.py           # /settings 偏好管理
│   │   ├── feedback.py           # 反馈收集
│   │   └── sources.py            # /sources 信息源
│   ├── services/                 # 业务服务
│   │   ├── gemini.py             # Gemini API 封装
│   │   ├── rss_fetcher.py        # RSS 抓取
│   │   ├── content_filter.py     # AI 筛选
│   │   ├── report_generator.py   # 简报生成
│   │   └── profile_updater.py    # 画像更新
│   ├── utils/
│   │   ├── json_storage.py       # JSON 存储
│   │   └── prompt_loader.py      # Prompt 加载
│   ├── prompts/                  # Prompt 模板
│   ├── tests/                    # 测试用例
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── data/                         # 数据存储
│   ├── users.json                # 用户列表
│   ├── sources.json              # 信息源配置
│   ├── profiles/                 # 用户画像
│   ├── feedback/                 # 反馈记录
│   └── daily_stats/              # 每日统计
│
├── docker-compose.yml            # Docker 编排
├── CLAUDE.md                     # 项目规范
└── README.md                     # 本文件
```

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/web3-daily-digest.git
cd web3-daily-digest
```

### 2. 配置环境变量

```bash
cp bot/.env.example bot/.env
```

编辑 `bot/.env`:

```bash
# ============ 必填 ============
GEMINI_API_KEY=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_bot_token

# ============ Gemini 配置 (可选) ============
# 自定义 API URL (代理或不同区域)
# 支持两种格式:
#   1. Base URL: https://your-proxy.com (自动补全路径)
#   2. 完整 URL: https://your-proxy.com/v1beta/models/gemini-3-pro:generateContent
GEMINI_API_URL=

# 模型选择 (默认: gemini-3-pro)
GEMINI_MODEL=gemini-3-pro

# 推理深度 (仅 Gemini 3 Pro): LOW = 更快, HIGH = 更好
GEMINI_THINKING_LEVEL=HIGH

# ============ 推送配置 (可选) ============
PUSH_HOUR=9          # 推送时间 (小时，北京时间)
PUSH_MINUTE=0        # 推送时间 (分钟)

# ============ 数据存储 (可选) ============
DATA_DIR=./data      # 数据目录
```

### 3. Docker 部署 (推荐)

```bash
docker-compose up -d
```

查看日志:

```bash
docker-compose logs -f
```

### 4. 本地开发

```bash
cd bot
pip install -r requirements.txt
python main.py
```

---

## 配置信息源

### Twitter 源

Twitter 不提供公开 RSS，需要使用 [RSS.app](https://rss.app) 服务转换。

1. 在 RSS.app 创建 Twitter Feed
2. 获取 RSS URL
3. 通过 Bot `/sources` 命令添加

### 网站 RSS 源

预置 4 个 Web3 媒体:

- The Block: `https://www.theblock.co/rss.xml`
- CoinDesk: `https://www.coindesk.com/arc/outboundfeeds/rss/`
- Decrypt: `https://decrypt.co/feed`
- Cointelegraph: `https://cointelegraph.com/rss`

可通过 `/sources` 命令添加更多。

---

## 测试

```bash
cd bot
python -m pytest tests/ -v
```

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [产品需求文档](./产品需求文档_PRD_Final.md) | 产品定位、功能设计 |
| [测试用例](./测试用例与验收标准_Test_Cases.md) | 测试用例、验收标准 |

---

## MVP 目标

| 指标 | 目标 |
|------|------|
| 支持用户数 | 100 人 |
| 信息源 | Twitter + 网站 |
| 推送渠道 | Telegram |
| 推送频率 | 每日 1 次 |

---

## License

MIT

---

**问题反馈**: 请提交 Issue
