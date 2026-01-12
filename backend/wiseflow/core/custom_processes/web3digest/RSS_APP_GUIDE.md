# RSS.app 使用指南

## 📋 概述

RSS.app 是一个强大的 RSS 源生成和管理服务，可以将 Twitter、Reddit、YouTube 等社交媒体平台转换为 RSS 源。本项目使用 RSS.app 将 Twitter 账号转换为 RSS 源，以便通过 WiseFlow 抓取引擎进行信息采集。

**官网**: https://rss.app/

---

## 🚀 快速开始

### 方式 1: 使用免费 RSS URL（推荐，无需注册）

无需注册，直接使用 RSS.app 提供的免费 RSS URL：

```
https://rss.app/feeds/v1.1/{username}.xml
```

**示例**:
- Vitalik Buterin: `https://rss.app/feeds/v1.1/VitalikButerin.xml`
- CoinDesk: `https://rss.app/feeds/v1.1/CoinDesk.xml`

**优点**:
- ✅ 无需注册
- ✅ 无需配置
- ✅ 开箱即用

**限制**:
- ⚠️ 可能有请求频率限制
- ⚠️ 功能相对基础

---

### 方式 2: 通过网页界面创建 RSS 源（推荐用于自定义源）

1. **访问 RSS.app**
   - 打开 https://rss.app/new-rss-feed
   - 或访问 https://rss.app/ 并点击 "New Feed"

2. **创建 RSS 源**
   - 选择源类型（Twitter、Reddit、YouTube 等）
   - 输入账号或 URL
   - 配置过滤规则（可选）
   - 点击 "Create Feed"

3. **获取 RSS URL**
   - 创建成功后，RSS.app 会生成一个唯一的 RSS URL
   - 格式：`https://rss.app/feeds/{feed_id}.xml`
   - 复制此 URL 用于配置

4. **在系统中使用**
   - 将 RSS URL 添加到 `DefaultRSSSources.WEBSITE_RSS` 配置中
   - 或通过 Telegram Bot 的 `/sources` 命令添加自定义源

**优点**:
- ✅ 可视化界面，易于操作
- ✅ 支持高级过滤和转换
- ✅ 可以管理多个 RSS 源
- ✅ 更稳定的服务

---

### 方式 3: 使用 RSS.app API（高级用户）

如果您需要批量创建或程序化管理 RSS 源，可以使用 RSS.app API。

1. **注册 RSS.app 账号**
   - 访问 https://rss.app/
   - 注册并登录账号

2. **获取 API Token**
   - 进入账户设置
   - 找到 "API" 或 "Developer" 部分
   - 创建新的 API Token

3. **配置 Token**
   ```bash
   # 在 .env 文件中添加
   RSS_APP_TOKEN=your_rss_app_token
   ```

4. **使用 API 创建 RSS 源**
   ```python
   # 示例代码（需要实现）
   import httpx
   
   async def create_rss_feed(twitter_username: str):
       async with httpx.AsyncClient() as client:
           response = await client.post(
               "https://api.rss.app/v1/feeds",
               headers={"Authorization": f"Bearer {RSS_APP_TOKEN}"},
               json={
                   "source": "twitter",
                   "username": twitter_username
               }
           )
           return response.json()
   ```

**优点**:
- ✅ 程序化管理
- ✅ 批量操作
- ✅ 更高的请求频率限制
- ✅ 完整的 API 功能

---

## 🔧 在项目中使用

### 当前实现

项目中的 `RSSAppClient` 类使用方式 1（免费 RSS URL），无需配置即可使用：

```python
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient

client = RSSAppClient()

# 获取 Twitter 账号的 RSS URL
rss_url = client.get_twitter_rss_url("VitalikButerin")
# 返回: https://rss.app/feeds/v1.1/VitalikButerin.xml

# 验证 RSS URL 是否有效
is_valid = await client.verify_rss_url(rss_url)
```

### 添加自定义 RSS 源

#### 方法 1: 通过配置文件添加

编辑 `core/config.py` 中的 `DefaultRSSSources.WEBSITE_RSS`:

```python
WEBSITE_RSS = [
    {
        "name": "自定义源名称",
        "url": "https://rss.app/feeds/{feed_id}.xml",  # 从 RSS.app 获取
        "type": "website",
        "category": "媒体"
    },
    # ... 更多源
]
```

#### 方法 2: 通过 Telegram Bot 添加

1. 在 Telegram Bot 中发送 `/sources` 命令
2. 选择 "➕ 添加网站 RSS"
3. 输入从 RSS.app 获取的 RSS URL
4. 系统会自动验证并添加

---

## 📚 RSS.app 支持的信息源

RSS.app 支持多种信息源类型：

### 社交媒体
- ✅ **Twitter** - 用户推文、列表、搜索
- ✅ **Reddit** - 子版块、用户、搜索
- ✅ **YouTube** - 频道、播放列表
- ✅ **Instagram** - 用户、标签
- ✅ **Facebook** - 页面、群组

### 新闻和博客
- ✅ **RSS/Atom** - 任何 RSS 源
- ✅ **网站** - 通过网页抓取生成 RSS
- ✅ **新闻网站** - 支持多种新闻平台

### 其他
- ✅ **GitHub** - 仓库、用户活动
- ✅ **Medium** - 用户、标签
- ✅ **Tumblr** - 博客、标签

---

## 🎯 高级功能

### 1. 过滤规则

在 RSS.app 网页界面创建源时，可以配置过滤规则：

- **关键词过滤**: 只包含特定关键词的内容
- **排除规则**: 排除包含特定关键词的内容
- **日期范围**: 只获取特定时间范围的内容
- **数量限制**: 限制每次获取的数量

### 2. 内容转换

RSS.app 可以转换内容格式：

- **HTML 转 Markdown**: 将 HTML 内容转换为 Markdown
- **图片处理**: 提取或转换图片
- **链接处理**: 处理相对链接和重定向

### 3. 定时更新

RSS.app 会自动定时更新 RSS 源：

- **更新频率**: 根据源类型自动调整
- **实时推送**: 支持 Webhook 实时推送
- **历史记录**: 保留历史内容

---

## 🔍 验证 RSS 源

### 方法 1: 使用系统验证功能

```python
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient

client = RSSAppClient()
is_valid = await client.verify_rss_url("https://rss.app/feeds/v1.1/VitalikButerin.xml")
```

### 方法 2: 使用测试脚本

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/verify_rss_sources.py
```

### 方法 3: 浏览器直接访问

在浏览器中打开 RSS URL，应该能看到 XML 格式的内容。

---

## ⚠️ 注意事项

### 1. 请求频率限制

- **免费版**: 可能有请求频率限制
- **付费版**: 更高的请求频率限制
- **建议**: 使用抓取调度器，避免频繁请求

### 2. Twitter 账号格式

- ✅ 正确: `VitalikButerin`（不含 @）
- ✅ 正确: `@VitalikButerin`（系统会自动移除 @）
- ❌ 错误: `https://twitter.com/VitalikButerin`

### 3. RSS URL 格式

RSS.app 提供多种 URL 格式：

- **免费版**: `https://rss.app/feeds/v1.1/{username}.xml`
- **API 版**: `https://api.rss.app/v1/feeds/{feed_id}`
- **自定义**: `https://rss.app/feeds/{feed_id}.xml`

### 4. 源可用性

- 某些 Twitter 账号可能无法转换为 RSS（如私密账号）
- 某些网站可能不支持 RSS.app 抓取
- 建议定期验证 RSS 源的有效性

---

## 🛠️ 故障排查

### 问题 1: RSS URL 无法访问

**症状**: 验证 RSS URL 时返回 `False`

**解决**:
1. 检查 URL 格式是否正确
2. 在浏览器中直接访问 URL，确认是否可访问
3. 检查网络连接
4. 确认 Twitter 账号是否存在且为公开账号

### 问题 2: RSS 源内容为空

**症状**: 抓取到的内容为空

**解决**:
1. 检查 RSS.app 源是否正常更新
2. 检查过滤规则是否过于严格
3. 确认源类型是否正确

### 问题 3: 请求频率过高

**症状**: 收到 429 错误（Too Many Requests）

**解决**:
1. 降低抓取频率
2. 使用 RSS.app API Token（提高限制）
3. 考虑升级 RSS.app 账户

---

## 📖 相关文档

- [RSS.app 官网](https://rss.app/)
- [RSS.app 创建新源](https://rss.app/new-rss-feed)
- [RSS.app API 文档](https://rss.app/docs)（如果可用）
- [项目集成指南](./INTEGRATION_GUIDE.md)
- [第三方服务配置](./THIRD_PARTY_CONFIG.md)

---

## 💡 最佳实践

1. **优先使用免费 RSS URL**: 对于大多数场景，免费 URL 已足够
2. **定期验证源**: 使用 `verify_rss_sources.py` 定期检查源有效性
3. **合理设置抓取频率**: 避免过于频繁的请求
4. **使用网页界面管理**: 对于复杂的过滤需求，使用 RSS.app 网页界面
5. **备份重要源**: 记录重要 RSS 源的 URL，避免丢失

---

## 🔄 更新日志

- **2025-01**: 初始版本，支持免费 RSS URL 和基础验证
- **未来**: 计划支持 RSS.app API 创建和管理功能
