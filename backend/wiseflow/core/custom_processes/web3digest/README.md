# Web3 Daily Digest - 基于 WiseFlow 的 Web3 个性化信息聚合服务

## 📖 简介

Web3 Daily Digest 是一个基于 WiseFlow 框架构建的 Web3 个性化信息聚合服务。通过 AI 智能筛选，每天为用户推送个性化的 Web3 信息简报。

## ✨ 核心特点

- 🤖 **AI 驱动的个性化筛选** - 基于用户画像，LLM 语义理解
- 💬 **对话式偏好设置** - 3 轮 AI 对话完成偏好收集，无需填表
- 📊 **价值可感知** - 每份简报展示"扫描了多少、精选了多少、节省了多少时间"
- 🔄 **反馈学习闭环** - 用户反馈 → AI 学习 → 推送越来越准
- 📱 **Telegram Bot 推送** - 每日定时推送个性化简报

## 🏗️ 项目结构

```
web3digest/
├── main.py              # 主程序入口
├── bot/                 # Telegram Bot 模块
│   └── telegram_bot.py
├── core/                # 核心业务逻辑
│   ├── config.py        # 配置管理
│   ├── conversation_manager.py  # 对话管理
│   ├── digest_generator.py      # 简报生成
│   ├── llm_client.py            # LLM 客户端
│   ├── profile_manager.py      # 用户画像管理
│   ├── scheduler.py             # 任务调度
│   ├── user_manager.py          # 用户管理
│   └── wiseflow_client.py       # WiseFlow 客户端
├── utils/               # 工具函数
│   └── logger.py
└── requirements.txt     # 依赖列表
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.11+
- WiseFlow 框架已安装
- Telegram Bot Token
- LLM API Key (硅基流动/DeepSeek 等)

### 2. 安装依赖

```bash
cd backend/wiseflow/core/custom_processes/web3digest
pip install -r requirements.txt
```

### 3. 配置环境变量

创建 `.env` 文件（在 WiseFlow 项目根目录）：

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# LLM 配置（默认使用 Kimi API）
# Kimi API 文档: https://platform.moonshot.cn/docs/guide/use-kimi-k2-thinking-model
LLM_API_BASE=https://api.moonshot.cn/v1
LLM_API_KEY=your_kimi_api_key
PRIMARY_MODEL=kimi-k2-thinking-preview
LLM_CONCURRENT_NUMBER=3

# 或者使用其他 OpenAI 兼容的 API（如 SiliconFlow）
# LLM_API_BASE=https://api.siliconflow.cn/v1
# LLM_API_KEY=your_siliconflow_api_key
# PRIMARY_MODEL=Qwen/Qwen2.5-32B-Instruct

# 数据存储
DATA_DIR=./data/web3digest

# 调度配置
DAILY_PUSH_TIME=09:00
TIMEZONE=Asia/Shanghai

# 任务配置
MAX_INFO_PER_USER=20
MIN_INFO_PER_USER=5
```

### 4. 运行服务

```bash
# 从 WiseFlow 项目根目录运行
python core/custom_processes/web3digest/main.py
```

## 📝 使用说明

### 用户命令

- `/start` - 开始使用或重新设置偏好
- `/profile` - 查看和更新我的偏好
- `/sources` - 管理信息源
- `/feedback` - 主动反馈
- `/test` - 手动触发一次简报（测试用）
- `/help` - 查看帮助

### 工作流程

1. **用户注册** - 用户通过 `/start` 命令启动 Bot
2. **偏好收集** - 3 轮 AI 对话收集用户偏好
3. **信息抓取** - WiseFlow 定时抓取 Web3 信息
4. **AI 筛选** - 基于用户画像筛选个性化内容
5. **简报生成** - AI 生成个性化简报
6. **定时推送** - 每日固定时间推送给用户
7. **反馈学习** - 用户反馈 → AI 学习 → 画像更新

## 🔧 技术架构

- **核心框架**: WiseFlow (LLM 驱动的信息抓取)
- **AI 服务**: OpenAI 兼容 API (硅基流动/DeepSeek)
- **推送**: Telegram Bot
- **存储**: JSON 文件
- **调度**: APScheduler

## 📚 相关文档

- [🚀 启动指南](./START_GUIDE.md) - **推荐先看这个！**
- [快速开始指南](./QUICK_START.md)
- [第三方服务配置指南](./THIRD_PARTY_CONFIG.md)
- [RSS.app 使用指南](./RSS_APP_GUIDE.md) - **如何创建和管理 RSS 源**
- [Kimi API 配置指南](./KIMI_API_CONFIG.md)
- [用户鉴权配置指南](./AUTH_CONFIG.md)
- [产品需求文档](../../../../../../docs/产品需求文档_PRD_Final.md)
- [技术路线文档](../../../../../../docs/[仅参考]技术路线文档_Technical_Roadmap.md)
- [测试用例](../../../../../../docs/测试用例与验收标准_Test_Cases.md)

## 📄 License

MIT
