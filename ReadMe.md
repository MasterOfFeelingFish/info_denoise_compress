# Web3 Daily Digest

> AI 驱动的 Web3 个性化信息聚合服务

每天自动抓取并筛选 Web3 信息，通过 AI 生成符合你偏好的个性化简报，节省 2+ 小时阅读时间。

## 核心特性

### AI 个性化筛选
- 3 轮 AI 对话式注册，深度理解用户偏好
- 两步处理流程：筛选（英文 prompt）→ 翻译（语言适配）
- 4 层内容分级：必读事件 / 行业大局 / 用户推荐 / 其他更新
- 跨源内容去重 + 来源多样性保证

### 智能反馈闭环
- 整体反馈（有帮助/没帮助）
- 单条反馈（👍/👎 按钮）
- 动态更新用户画像（固定篇幅，精细化描述），用户越用越精准
- 反馈趋势分析（近 30 天）

### 管理员控制台
- 白名单管理（增删查 + 开关）
- 多管理员支持（环境变量配置）
- AI 筛选分批处理（大数据量自动分批，避免超限）

### 多信息源聚合
- Twitter 账号监控（通过 RSS 转换）
- 网站 RSS 订阅（支持自动检测）
- 每用户独立信息源配置
- 批量导入默认信息源

### AI 智能助手
- 自然语言对话（支持联网搜索）
- 读取最近 3 天推送内容作为上下文
- 可配置对话历史保留天数（0/1/2 天）
- 基于用户画像的个性化回答
- 支持多 LLM 提供商（Gemini / OpenAI）

### 多语言支持
- 自动检测用户语言偏好
- 支持 8 种语言翻译（中/英/日/韩/俄/西/法/德）
- 保持原始链接，翻译标题和摘要

### 价值可感知
- 每日统计（信息源数 / 扫描条数 / 精选条数）
- 筛选率展示（节省时间可视化）
- 自然语言画像描述（用户偏好透明化）

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
| `/start` | 主菜单（新用户进入注册流程，管理员显示控制台入口） |
| `/help` | 帮助信息 |
| `/settings` | 偏好设置管理 |
| `/sources` | 信息源管理（添加/删除） |
| `/stats` | 查看统计（简报数据+反馈趋势） |
| `/clear` | 清空对话历史 |
| `/test` | 手动触发抓取（调试用） |
| `/testprofile` | 手动触发画像更新（调试用） |

**管理员功能**（通过主菜单「管理员控制台」按钮访问）：
- 白名单开关（启用/禁用访问控制）
- 查询白名单（显示用户详细信息）
- 添加/删除白名单用户

---

## 技术栈

| 技术层 | 选型 | 说明 |
|--------|------|------|
| **LLM 引擎** | Gemini / OpenAI / Kimi | 支持 Gemini 3 Pro、GPT-4 系列、Kimi K2 Thinking |
| **Bot 框架** | python-telegram-bot v22.0 | 官方推荐库 + 定时任务 + 对话流 |
| **RSS 抓取** | feedparser + httpx | 异步抓取 + 自动去重 |
| **数据存储** | JSON 文件 | MVP 轻量方案 + 多用户隔离 |
| **部署** | Docker Compose | 一键部署 + 数据卷持久化 |

---

## 项目结构

```
info_denoise_compress/
├── bot/                          # Telegram Bot
│   ├── main.py                   # 入口 + 定时任务 + handler 注册
│   ├── config.py                 # 环境变量配置 + 默认信息源解析
│   ├── handlers/                 # 用户交互层
│   │   ├── start.py              # 注册流程（3轮AI对话）+ 主菜单 + 统计
│   │   ├── chat.py               # AI 对话（联网+上下文+每日清理）
│   │   ├── feedback.py           # 反馈收集（整体+单条）
│   │   ├── sources.py            # 信息源管理（增删查）
│   │   ├── settings.py           # 偏好设置管理
│   │   └── admin.py              # 管理员控制台（白名单管理）
│   ├── services/                 # 业务逻辑层
│   │   ├── llm_provider.py       # LLM 抽象接口
│   │   ├── llm_factory.py        # LLM 工厂（选择提供商）
│   │   ├── gemini_provider.py    # Gemini API 实现
│   │   ├── openai_provider.py    # OpenAI API 实现
│   │   ├── digest_processor.py   # 简报处理（单用户）
│   │   ├── rss_fetcher.py        # RSS 抓取（ID 去重）
│   │   ├── content_filter.py     # AI 筛选逻辑
│   │   ├── report_generator.py   # 简报生成（多语言）
│   │   └── profile_updater.py    # 反馈学习闭环（每日更新）
│   ├── utils/                    # 工具层
│   │   ├── json_storage.py       # 数据存储（多用户隔离）+ 白名单管理
│   │   ├── telegram_utils.py     # Telegram 工具（限流器等）
│   │   ├── prompt_loader.py      # Prompt 模板加载
│   │   └── auth.py               # 白名单权限装饰器
│   ├── prompts/                  # Prompt 模板
│   │   ├── onboarding_*.txt      # 注册流程（3轮）
│   │   ├── filtering.txt         # 内容筛选（4层分级）
│   │   ├── translate.txt         # 语言适配（独立翻译）
│   │   ├── report.txt            # 简报生成
│   │   └── *_update.txt          # 画像/设置更新
│   ├── tests/
│   │   └── test_all_modules.py   # 自动化测试
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   └── .gitignore
│
├── data/                         # 数据存储 (JSON)
│   ├── users.json                # 用户基本信息
│   ├── user_sources/             # 每用户信息源配置
│   ├── profiles/                 # 用户画像
│   ├── feedback/                 # 反馈记录（按日期）
│   ├── daily_stats/              # 每日统计（每用户子目录）
│   ├── raw_content/              # 原始抓取内容（每用户子目录）
│   ├── prefetch_cache/           # 预抓取缓存（解决 RSS 时效问题）
│   └── logs/                     # 日志文件
│
├── docker-compose.yml            # Docker 一键部署配置
└── README.md                     # 本文件
```

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/info_denoise_compress.git
cd info_denoise_compress
```

### 2. 配置环境变量

```bash
cp bot/.env.example bot/.env
```

编辑 `bot/.env`:

```bash
# ============================================================================
# 🤖 LLM 配置（必填，三选一）
# ============================================================================
# 提供商选择: gemini / openai (含 Kimi 等兼容 API)
LLM=openai

# --- Gemini 配置 ---
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3-pro-preview

# --- OpenAI / Kimi 配置 ---
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o                              # 或 kimi-k2-thinking
OPENAI_API_URL=                                   # Kimi: https://api.moonshot.cn/v1/chat/completions

# ============================================================================
# 📱 Telegram Bot 配置（必填）
# ============================================================================
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# ============================================================================
# ⏰ 推送配置
# ============================================================================
PUSH_HOUR=9                      # 推送时间（小时，北京时间）
PUSH_MINUTE=0                    # 推送时间（分钟）

# ============================================================================
# 📊 简报配置
# ============================================================================
MIN_DIGEST_ITEMS=15              # 每日精选最少条数
MAX_DIGEST_ITEMS=30              # 每日精选最多条数
MAX_AI_INPUT_ITEMS=800           # AI单次输入最大条数（0=不限制，超过则分批处理）

# 并发处理用户数（推送简报时同时处理多少用户）
CONCURRENT_USERS=100

# ============================================================================
# 🛡️ 管理员配置
# ============================================================================
ADMIN_TELEGRAM_IDS=123456789     # 管理员 Telegram ID（多个用逗号分隔）
WHITELIST_ENABLED=true           # 白名单开关（true=仅白名单用户可用）

# ============================================================================
# 🗄️ 数据保留配置
# ============================================================================
# 超过保留天数后自动清理，每日 00:30 执行
RAW_CONTENT_RETENTION_DAYS=7     # 原始抓取内容保留天数
DAILY_STATS_RETENTION_DAYS=30    # 每日统计保留天数
FEEDBACK_RETENTION_DAYS=30       # 反馈记录保留天数

# ============================================================================
# 💬 AI 对话配置
# ============================================================================
CHAT_CONTEXT_DAYS=1              # 对话上下文保留天数 (0=当天, 1=昨天, 2=前天)

# ============================================================================
# 📝 日志配置
# ============================================================================
LOG_ROTATE_DAYS=1                # 日志轮转间隔（天）
LOG_BACKUP_COUNT=30              # 日志备份保留数量

# ============================================================================
# 🌐 默认信息源（新用户注册时使用）
# ============================================================================
DEFAULT_WEBSITE_SOURCES=Cointelegraph|https://cointelegraph.com/rss,CoinDesk|https://www.coindesk.com/arc/outboundfeeds/rss/,The Block Beats|https://api.theblockbeats.news/v1/open-api/home-xml,TechFlow Post|https://techflowpost.substack.com/feed
DEFAULT_TWITTER_SOURCES=Twitter Bundle 1|https://rss.app/feeds/G6dip9YSp1NzQMls.xml,Twitter Bundle 2|https://rss.app/feeds/HVg722x6SI7tChWQ.xml
```

### 3. Docker 部署 (推荐)

```bash
# 创建数据目录
mkdir -p data

# 启动服务
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

预置 8 个 Web3 媒体:

- Cointelegraph: `https://cointelegraph.com/rss`
- CoinDesk: `https://www.coindesk.com/arc/outboundfeeds/rss/`
- The Block Beats: `https://api.theblockbeats.news/v1/open-api/home-xml`
- TechFlow Post: `https://techflowpost.substack.com/feed`
- DeFi Rate: `https://defirate.com/feed`
- Prediction News: `https://predictionnews.com/rss/`
- Event Horizon: `https://nexteventhorizon.substack.com/feed`
- un.Block (吴说): `https://unblock256.substack.com/feed`

可通过 `/sources` 命令添加更多。

---

## 定时任务

| 时间（北京） | 任务 | 说明 |
|-------------|------|------|
| **每小时** | 预抓取 RSS | 解决 RSS.app 只返回最近 25 条的问题 |
| **09:00** | 每日简报推送 | 从缓存读取 → 筛选 → 翻译 → 推送 |
| **00:00** | 用户画像更新 | 基于反馈批量更新 |
| **00:30** | 数据清理 | 删除过期文件 + 清理缓存 |

---

## 使用指南

### 新用户注册流程

1. 发送 `/start` 进入主菜单
2. 点击「开始设置」进入 3 轮 AI 对话：
   - **Round 1**：询问区块链生态系统偏好（Ethereum/Solana/Layer2）
   - **Round 2**：询问内容类型偏好（DeFi/NFT/交易/开发）
   - **Round 3**：生成画像摘要，用户确认
3. 配置信息源（自定义/使用默认/暂时跳过）
4. 等待每日推送（默认 9:00）

### 信息源管理

#### 添加 Twitter 账号
1. 进入「信息源管理」→「Twitter」
2. 输入 Twitter 用户名（格式：`@username` 或 `username`）
3. 系统自动转换为 RSS 源

#### 添加网站 RSS
1. 进入「信息源管理」→「网站」
2. 输入网站域名或完整 RSS URL
3. 系统自动检测 RSS 地址（支持多种路径）

### AI 对话

直接向 Bot 发送消息即可开始对话，AI 会：
- 读取你的用户画像
- 调用 Google Search 获取实时信息（Gemini）
- 参考最近 3 天推送内容回答问题

**示例**：
- "最近 Ethereum Layer2 有什么重大更新？"
- "帮我总结昨天简报中的 DeFi 协议动态"
- "解释一下 EIP-4844 的技术细节"

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

## 多语言支持

Bot 自动检测用户语言并翻译简报内容，支持：
- 中文（zh）
- 英语（en）
- 日语（ja）
- 韩语（ko）
- 俄语（ru）
- 西班牙语（es）
- 法语（fr）
- 德语（de）

---

## 核心数据流

```
用户注册 → AI 对话收集偏好 → 配置信息源
                                    ↓
                            【每小时】预抓取 + 去重缓存
                                    ↓
                            【09:00】从缓存读取
                                    ↓
                    Step 1: AI 筛选（英文 prompt，4 层分级）
                                    ↓
                    Step 2: 语言适配（独立翻译步骤）
                                    ↓
                    Telegram 推送（分条发送）
                                    ↓
    用户反馈（👍/👎）→ 每日更新画像 ──┘
```

---

## MVP 目标

| 指标 | 目标 |
|------|------|
| 支持用户数 | 100 人 |
| 信息源 | Twitter + 网站 RSS |
| 推送渠道 | Telegram |
| 推送频率 | 每日 1 次 |
| 筛选率 | 85-95%（200+ 条 → 15-30 条）|

---

## 扩展性

### 数据库升级
JSON 文件适合 MVP（100 用户），规模扩展可迁移至：
- PostgreSQL（结构化数据）
- MongoDB（用户画像）
- Redis（缓存 + 实时数据）

### 功能扩展
- 多平台推送（Discord/Slack/Email）
- 实时推送（突发事件）
- 社区功能（用户间分享）
- 数据分析（行业趋势报告）

---

## 开发指南

### 查看日志
```bash
# 本地运行
tail -f data/logs/bot.log

# Docker 运行
docker-compose logs -f
```

### 手动触发推送
```bash
# 在 Telegram 中向 Bot 发送
/test
```

### 调试模式
修改 `main.py` 中的日志级别：
```python
logger.setLevel(logging.DEBUG)
```

---

## 贡献

欢迎提交 Issue 和 Pull Request！

## License

MIT

---

**问题反馈**: 请提交 [Issue](https://github.com/your-repo/info_denoise_compress/issues)
