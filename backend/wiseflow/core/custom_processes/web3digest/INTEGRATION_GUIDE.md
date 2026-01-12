# 信息抓取集成指南

## 📋 概述

本文档说明如何配置和使用信息抓取功能，包括 RSS.app 集成、WiseFlow 抓取引擎集成和完整流程测试。

## 🔧 配置步骤

### 1. RSS.app 配置（可选）

RSS.app 用于将 Twitter 账号转换为 RSS 源。

**方式1：使用免费 RSS URL（推荐）**
- 无需配置，直接使用 RSS.app 的公开 RSS URL
- 格式：`https://rss.app/feeds/v1.1/{username}.xml`
- 限制：可能有频率限制

**方式2：使用 RSS.app API（可选）**
- 注册 RSS.app 账号：https://rss.app
- 获取 API Token
- 在 `.env` 文件中配置：
  ```bash
  RSS_APP_TOKEN=your_rss_app_token
  ```

### 2. 环境变量配置

在 WiseFlow 项目根目录的 `.env` 文件中添加：

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# LLM 配置
LLM_API_BASE=https://api.siliconflow.cn/v1
LLM_API_KEY=your_llm_api_key
PRIMARY_MODEL=Qwen/Qwen2.5-32B-Instruct

# RSS 配置（可选）
RSS_APP_TOKEN=your_rss_app_token

# 数据存储
DATA_DIR=./data/web3digest

# 调度配置
DAILY_PUSH_TIME=09:00
TIMEZONE=Asia/Shanghai
```

### 3. 信息源配置

信息源配置在 `core/config.py` 中的 `DefaultRSSSources` 类：

- **Twitter 账号**：`TWITTER_ACCOUNTS` 列表
- **网站 RSS**：`WEBSITE_RSS` 列表

可以修改这些列表来添加或删除信息源。

## 🚀 使用方法

### 运行测试脚本

测试抓取功能：

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/test_crawler.py
```

测试脚本会：
1. 测试 RSS.app 客户端
2. 测试 WiseFlow 客户端
3. 测试完整工作流程（可选）

### 启动完整服务

启动包含抓取调度器的完整服务：

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/main.py
```

服务会自动：
- 每小时执行一次信息抓取
- 每日固定时间推送简报

### 手动触发抓取

在代码中手动触发抓取：

```python
from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient

client = WiseFlowClient()
await client.initialize()
result = await client.trigger_crawl()
```

## 📊 工作流程

```
1. 抓取调度器（每小时）
   ↓
2. RSS.app 客户端生成 RSS URL
   ↓
3. WiseFlow 抓取引擎
   ├── 抓取 RSS 源
   ├── 抓取网站内容
   └── 存储到数据库
   ↓
4. 简报生成器（每日）
   ├── 从数据库获取今日信息
   ├── AI 筛选个性化内容
   └── 生成简报
   ↓
5. Telegram 推送
```

## 🔍 调试和监控

### 查看日志

日志文件位置：`{DATA_DIR}/logs/web3digest.log`

### 检查数据库

WiseFlow 使用 SQLite 数据库存储信息，位置通常在 WiseFlow 数据目录。

### 常见问题

**Q: RSS URL 无法访问？**
- 检查网络连接
- 验证 RSS URL 格式是否正确
- 某些 RSS.app URL 可能需要登录

**Q: 抓取失败？**
- 检查 WiseFlow 数据库是否正常初始化
- 查看日志文件了解详细错误
- 确认 LLM API 配置正确

**Q: 没有抓取到信息？**
- 检查信息源是否有效
- 确认抓取时间范围（默认24小时）
- 查看 WiseFlow 日志

## 📝 下一步

- [ ] 配置更多信息源
- [ ] 优化抓取频率
- [ ] 实现信息源管理功能
- [ ] 添加抓取统计和监控
