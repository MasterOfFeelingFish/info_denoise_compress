# 快速开始指南

## 🚀 5 分钟快速开始

### 步骤 1：配置环境变量

在 WiseFlow 项目根目录创建或编辑 `.env` 文件：

```bash
# 必需配置
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
LLM_API_KEY=your_llm_api_key

# LLM 配置（默认使用 Kimi API）
LLM_API_BASE=https://api.moonshot.cn/v1
PRIMARY_MODEL=kimi-k2-thinking-preview

# 或者使用其他 OpenAI 兼容的 API
# LLM_API_BASE=https://api.siliconflow.cn/v1
# PRIMARY_MODEL=Qwen/Qwen2.5-32B-Instruct

# 可选配置（使用默认值）
DATA_DIR=./data/web3digest
DAILY_PUSH_TIME=09:00
```

### 步骤 2：安装依赖

```bash
cd backend/wiseflow
pip install -r core/custom_processes/web3digest/requirements.txt
```

### 步骤 3：测试抓取功能

```bash
python core/custom_processes/web3digest/test_crawler.py
```

这会测试：
- ✅ RSS.app 客户端（生成 Twitter RSS URL）
- ✅ WiseFlow 客户端（信息抓取）
- ✅ 完整工作流程（可选）

### 步骤 4：启动服务

```bash
# 确保在 WiseFlow 项目根目录
cd backend/wiseflow

# 启动服务
python core/custom_processes/web3digest/main.py
```

**预期输出**:
```
✅ Telegram Bot 已启动
🚀 Web3 Daily Digest 服务启动中...
```

服务启动后会：
- 🤖 启动 Telegram Bot
- 📡 每小时自动抓取信息
- 📰 每日固定时间推送简报

**详细启动说明**: 查看 [启动指南](./START_GUIDE.md)

## 📱 使用 Telegram Bot

1. 在 Telegram 中搜索你的 Bot
2. 发送 `/start` 开始使用
3. 完成 3 轮对话设置偏好
4. 等待每日简报推送

## 🔧 常见问题

**Q: 如何添加更多信息源？**

编辑 `core/config.py` 中的 `DefaultRSSSources` 类。

**Q: 如何修改抓取频率？**

编辑 `core/crawler_scheduler.py` 中的 CronTrigger 配置。

**Q: 如何查看日志？**

日志文件：`{DATA_DIR}/logs/web3digest.log`

## 📚 更多文档

- [集成指南](./INTEGRATION_GUIDE.md) - 详细的配置和集成说明
- [README](./README.md) - 项目概述和架构说明
- [迁移说明](./MIGRATION.md) - 重构迁移说明
