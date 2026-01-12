# 第三方服务配置指南

## 📋 概述

本项目依赖以下第三方服务，需要配置相应的 API Key 或 Token。

## 🔑 必需配置

### 1. Telegram Bot Token

**用途**: Telegram Bot 推送和用户交互

**获取方式**:
1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 命令创建新 Bot
3. 按提示设置 Bot 名称和用户名
4. 获取 Token（格式：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）

**配置**:
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

**文档**: https://core.telegram.org/bots/api

---

### 2. Kimi API Key (LLM)

**用途**: AI 驱动的信息筛选、简报生成、用户画像分析

**获取方式**:
1. 访问 [Kimi 开放平台](https://platform.moonshot.cn/)
2. 注册/登录账号
3. 在左侧导航栏点击"API Key 管理"
4. 点击"新建"创建 API Key
5. 复制 API Key（格式：`sk-...`）

**已配置的 API Key**:
```bash
LLM_API_BASE=https://api.moonshot.cn/v1
LLM_API_KEY=sk-Nu4nsNqZtsD1cmm1hJG2wrgc0eG1cQXe77bxZ226uolR2Idu
PRIMARY_MODEL=kimi-k2-thinking-preview
```

**文档**: 
- [Kimi K2 思考模型使用指南](https://platform.moonshot.cn/docs/guide/use-kimi-k2-thinking-model)
- [API 平台](https://platform.moonshot.cn/)

**替代方案**: 可以使用其他 OpenAI 兼容的 API
- SiliconFlow: `https://api.siliconflow.cn/v1`
- DeepSeek: `https://api.deepseek.com/v1`
- OpenAI: `https://api.openai.com/v1`

---

## 🔧 可选配置

### 3. RSS.app Token（可选）

**用途**: 将 Twitter 账号转换为 RSS 源（可选，可使用免费 RSS URL）

**获取方式**:
1. 访问 [RSS.app](https://rss.app/)
2. 注册/登录账号
3. 在账户设置中获取 API Token

**配置**:
```bash
RSS_APP_TOKEN=your_rss_app_token
```

**说明**:
- **不配置也可以使用**: 系统默认使用 RSS.app 的免费 RSS URL 格式
- **配置后优势**: 
  - 更高的请求频率限制
  - 更稳定的服务
  - 支持更多高级功能
  - 支持通过 API 创建和管理 RSS 源

**免费 RSS URL 格式**:
```
https://rss.app/feeds/v1.1/{username}.xml
```

**创建自定义 RSS 源**:
- 通过网页界面: https://rss.app/new-rss-feed
- 支持 Twitter、Reddit、YouTube 等多种源类型
- 支持高级过滤和转换功能

**详细文档**: 查看 [RSS.app 使用指南](./RSS_APP_GUIDE.md)

---

## 📝 完整配置示例

在 WiseFlow 项目根目录的 `.env` 文件中：

```bash
# ============================================
# 必需配置
# ============================================

# Telegram Bot Token
# 从 @BotFather 获取
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Kimi API (LLM)
LLM_API_BASE=https://api.moonshot.cn/v1
LLM_API_KEY=sk-Nu4nsNqZtsD1cmm1hJG2wrgc0eG1cQXe77bxZ226uolR2Idu
PRIMARY_MODEL=kimi-k2-thinking-preview
LLM_CONCURRENT_NUMBER=3

# ============================================
# 可选配置
# ============================================

# RSS.app Token (可选)
# 如果不配置，将使用免费 RSS URL
RSS_APP_TOKEN=your_rss_app_token

# ============================================
# 其他配置（使用默认值即可）
# ============================================

# 数据存储目录
DATA_DIR=./data/web3digest

# 日志级别
LOG_LEVEL=INFO

# 调度配置
DAILY_PUSH_TIME=09:00
TIMEZONE=Asia/Shanghai

# 任务配置
MAX_INFO_PER_USER=20
MIN_INFO_PER_USER=5

# 反馈配置
FEEDBACK_UPDATE_THRESHOLD=5

# 鉴权配置
ADMIN_TELEGRAM_IDS=123456789,987654321  # 管理员 Telegram ID（逗号分隔）
ENABLE_WHITELIST=false  # 是否启用白名单模式
```

---

## ✅ 配置检查清单

在启动服务前，请确认：

- [ ] **Telegram Bot Token** 已配置
- [ ] **Kimi API Key** 已配置
- [ ] **RSS.app Token** 已配置（可选）
- [ ] 所有环境变量已添加到 `.env` 文件
- [ ] `.env` 文件已添加到 `.gitignore`（避免泄露密钥）

---

## 🔍 验证配置

### 方法 1: 运行测试脚本

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/test_crawler.py
```

### 方法 2: 启动服务测试

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/main.py
```

然后在 Telegram Bot 中使用 `/test` 命令测试完整流程。

---

## 🛠️ 故障排查

### Telegram Bot Token 无效

**症状**: Bot 无法启动，提示 `Unauthorized`

**解决**:
1. 检查 Token 是否正确（格式：`数字:字母数字组合`）
2. 确认 Token 未过期
3. 在 @BotFather 中重新生成 Token

### Kimi API Key 无效

**症状**: LLM 调用失败，提示 `401 Unauthorized`

**解决**:
1. 检查 API Key 是否正确
2. 确认 API Key 是否已激活
3. 访问 https://platform.moonshot.cn/ 验证账户状态
4. 检查账户余额是否充足

### RSS.app 访问受限

**症状**: Twitter RSS URL 无法访问

**解决**:
1. 配置 RSS.app Token（推荐）
2. 或使用其他 RSS 转换服务
3. 或直接使用网站 RSS 源

---

## 📚 相关文档

- [Kimi API 配置指南](./KIMI_API_CONFIG.md)
- [快速开始指南](./QUICK_START.md)
- [集成指南](./INTEGRATION_GUIDE.md)

---

## 🔐 安全建议

1. **不要提交密钥到代码仓库**
   - 确保 `.env` 文件在 `.gitignore` 中
   - 使用环境变量而非硬编码

2. **定期轮换密钥**
   - 定期更新 API Key
   - 发现泄露立即更换

3. **限制 API 使用**
   - 设置合理的并发数
   - 监控 API 调用量和费用

4. **使用密钥管理服务**（生产环境）
   - AWS Secrets Manager
   - Azure Key Vault
   - HashiCorp Vault
