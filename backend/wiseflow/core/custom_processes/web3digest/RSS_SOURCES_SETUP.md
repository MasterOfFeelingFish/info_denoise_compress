# RSS 源配置指南 - 根据需求文档

## 📋 需求分析

根据产品需求文档，系统需要监控以下信息源：

### 信息源分类

1. **Twitter 账号**（需要通过 RSS.app 转换为 RSS）
2. **网站 RSS**（可直接使用或通过 RSS.app 创建）

---

## 🎯 需要配置的 RSS 源

### 一、Twitter 账号（16 个）

这些需要通过 RSS.app 转换为 RSS 源。

#### 1. 行业领袖（3 个）

| Twitter 账号 | 说明 | RSS.app 操作 |
|-------------|------|-------------|
| `VitalikButerin` | 以太坊创始人 | 需要创建 RSS 源 |
| `cz_binance` | Binance CEO | 需要创建 RSS 源 |
| `brian_armstrong` | Coinbase CEO | 需要创建 RSS 源 |

#### 2. 链上数据（4 个）

| Twitter 账号 | 说明 | RSS.app 操作 |
|-------------|------|-------------|
| `whale_alert` | 大额转账监控 | 需要创建 RSS 源 |
| `lookonchain` | 链上数据分析 | 需要创建 RSS 源 |
| `EmberCN` | 链上数据分析（中文） | 需要创建 RSS 源 |
| `ai_9684xtpa` | 聪明钱追踪（中文） | 需要创建 RSS 源 |

#### 3. 项目官方（4 个）

| Twitter 账号 | 说明 | RSS.app 操作 |
|-------------|------|-------------|
| `ethereum` | 以太坊官方 | 需要创建 RSS 源 |
| `solana` | Solana 官方 | 需要创建 RSS 源 |
| `arbitrum` | Arbitrum 官方 | 需要创建 RSS 源 |
| `optimism` | Optimism 官方 | 需要创建 RSS 源 |

#### 4. 媒体（5 个）

| Twitter 账号 | 说明 | RSS.app 操作 |
|-------------|------|-------------|
| `CoinDesk` | 加密媒体 | 需要创建 RSS 源 |
| `TheBlock__` | 加密媒体 | 需要创建 RSS 源 |
| `WuBlockchain` | 吴说区块链 | 需要创建 RSS 源 |
| `BlockBeatsAsia` | 律动 BlockBeats | 需要创建 RSS 源 |

---

### 二、网站 RSS（5 个）

这些可以直接使用网站提供的 RSS，或通过 RSS.app 创建更稳定的版本。

| 网站名称 | RSS URL | 是否需要 RSS.app |
|---------|---------|----------------|
| The Block | `https://www.theblock.co/rss.xml` | 可选（已有原生 RSS） |
| CoinDesk | `https://www.coindesk.com/arc/outboundfeeds/rss/` | 可选（已有原生 RSS） |
| Foresight News | `https://foresightnews.pro/feed` | 可选（已有原生 RSS） |
| 律动 BlockBeats | `https://www.theblockbeats.info/feed` | 可选（已有原生 RSS） |
| 金色财经 | `https://www.jinse.com/rss` | 可选（已有原生 RSS） |

**建议**：如果网站原生 RSS 不稳定，可以通过 RSS.app 重新创建。

---

## 🚀 操作步骤

### 方式 1: 使用免费 RSS URL（最简单，推荐）

**优点**：无需注册，无需手动创建，系统自动生成

**操作**：
1. **无需任何操作** - 系统已自动配置
2. 系统会自动使用格式：`https://rss.app/feeds/v1.1/{username}.xml`

**示例**：
- VitalikButerin: `https://rss.app/feeds/v1.1/VitalikButerin.xml`
- whale_alert: `https://rss.app/feeds/v1.1/whale_alert.xml`

**当前状态**：✅ 已配置，可直接使用

---

### 方式 2: 通过 RSS.app 网页界面创建（推荐用于自定义源）

如果您想：
- 添加更多 Twitter 账号
- 创建自定义过滤规则
- 获得更稳定的 RSS 源

**操作步骤**：

#### Step 1: 访问 RSS.app

打开 https://rss.app/new-rss-feed

#### Step 2: 选择源类型

选择 **"Twitter"** 或 **"Twitter User"**

#### Step 3: 输入 Twitter 账号

对于每个需要创建的 Twitter 账号：

1. **输入账号名**（不含 @）
   - 例如：`VitalikButerin`（不是 `@VitalikButerin`）

2. **配置过滤规则**（可选）
   - 关键词过滤：只包含特定关键词
   - 排除规则：排除特定内容
   - 日期范围：只获取最近的内容

3. **点击 "Create Feed"**

#### Step 4: 获取 RSS URL

创建成功后，RSS.app 会生成一个 RSS URL，格式类似：
```
https://rss.app/feeds/{feed_id}.xml
```

#### Step 5: 在系统中使用

**方法 A：通过配置文件添加**

编辑 `backend/wiseflow/core/custom_processes/web3digest/core/config.py`：

```python
# 添加到 DefaultRSSSources.WEBSITE_RSS
WEBSITE_RSS = [
    {
        "name": "VitalikButerin (自定义)",
        "url": "https://rss.app/feeds/{feed_id}.xml",  # 从 RSS.app 获取
        "type": "website",
        "category": "行业领袖"
    },
    # ... 更多源
]
```

**方法 B：通过 Telegram Bot 添加**

1. 在 Telegram Bot 中发送 `/sources`
2. 选择 "➕ 添加网站 RSS"
3. 输入从 RSS.app 获取的 RSS URL
4. 系统会自动验证并添加

---

### 方式 3: 批量创建（使用脚本）

如果您需要批量创建多个 RSS 源，可以：

1. **使用 RSS.app API**（需要 API Token）
2. **编写脚本**批量创建

**示例脚本**（需要实现）：

```python
# 批量创建 Twitter RSS 源
twitter_accounts = [
    "VitalikButerin",
    "cz_binance",
    "brian_armstrong",
    # ... 更多账号
]

for account in twitter_accounts:
    # 调用 RSS.app API 创建源
    # 获取 RSS URL
    # 保存到配置
```

---

## 📊 当前配置状态

### ✅ 已配置的源

查看 `backend/wiseflow/core/custom_processes/web3digest/core/config.py`：

**Twitter 账号**（16 个）：
- ✅ 行业领袖：3 个
- ✅ 链上数据：4 个
- ✅ 项目官方：4 个
- ✅ 媒体：5 个

**网站 RSS**（5 个）：
- ✅ The Block
- ✅ CoinDesk
- ✅ Foresight News
- ✅ 律动 BlockBeats
- ✅ 金色财经

**总计**：21 个信息源

---

## 🎯 推荐操作方案

### 方案 A：最小化操作（推荐）

**适合**：快速启动，使用默认配置

1. ✅ **无需操作** - 系统已配置好所有源
2. ✅ **直接使用** - 系统会自动使用免费 RSS URL
3. ✅ **开始测试** - 运行测试脚本验证

**操作**：
```bash
cd backend/wiseflow
python core/custom_processes/web3digest/test_crawler.py
```

---

### 方案 B：优化配置（推荐用于生产环境）

**适合**：需要更稳定的 RSS 源，或需要自定义过滤

1. **访问 RSS.app**：https://rss.app/new-rss-feed
2. **创建关键源**（建议优先创建）：
   - VitalikButerin（行业领袖）
   - whale_alert（链上数据）
   - ethereum（项目官方）
   - CoinDesk（媒体）
3. **获取 RSS URL** 并更新配置
4. **验证源有效性**

---

### 方案 C：完整自定义

**适合**：需要完全控制 RSS 源，添加更多自定义源

1. **注册 RSS.app 账号**
2. **批量创建所有需要的 RSS 源**
3. **配置 API Token**（可选）
4. **更新系统配置**

---

## 🔍 验证 RSS 源

### 方法 1: 使用系统验证脚本

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/verify_rss_sources.py
```

### 方法 2: 浏览器直接访问

在浏览器中打开 RSS URL，应该能看到 XML 格式的内容。

**示例**：
- https://rss.app/feeds/v1.1/VitalikButerin.xml
- https://rss.app/feeds/v1.1/whale_alert.xml

---

## ⚠️ 注意事项

### 1. Twitter 账号格式

- ✅ 正确：`VitalikButerin`（不含 @）
- ✅ 正确：`@VitalikButerin`（系统会自动移除 @）
- ❌ 错误：`https://twitter.com/VitalikButerin`

### 2. 源可用性

- 某些 Twitter 账号可能无法转换为 RSS（如私密账号）
- 某些账号可能不存在或已改名
- 建议定期验证 RSS 源的有效性

### 3. 请求频率

- 免费 RSS URL 可能有请求频率限制
- 建议使用抓取调度器，避免频繁请求
- 如需更高频率，考虑使用 RSS.app API Token

---

## 📝 下一步

1. **验证当前配置**：
   ```bash
   python core/custom_processes/web3digest/verify_rss_sources.py
   ```

2. **测试抓取功能**：
   ```bash
   python core/custom_processes/web3digest/test_crawler.py
   ```

3. **启动服务**：
   ```bash
   python core/custom_processes/web3digest/main.py
   ```

4. **添加自定义源**（如需要）：
   - 通过 Telegram Bot 的 `/sources` 命令
   - 或直接编辑配置文件

---

## 📚 相关文档

- [RSS.app 使用指南](./RSS_APP_GUIDE.md) - 详细的 RSS.app 使用说明
- [第三方服务配置](./THIRD_PARTY_CONFIG.md) - 完整的配置指南
- [产品需求文档](../../../../../../docs/产品需求文档_PRD_Final.md) - 原始需求文档

---

## 💡 总结

**根据您的需求文档，系统需要：**

- ✅ **16 个 Twitter 账号** - 已配置，使用免费 RSS URL
- ✅ **5 个网站 RSS** - 已配置，使用原生 RSS

**当前状态**：✅ **所有必需的信息源已配置完成**

**建议操作**：
1. 直接使用当前配置（方案 A）
2. 如需优化，可选择性创建更稳定的 RSS 源（方案 B）
3. 验证源有效性后即可开始使用
