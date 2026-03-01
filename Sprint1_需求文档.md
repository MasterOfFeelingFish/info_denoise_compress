# Sprint 1 需求文档

> **版本**: v1.1  
> **日期**: 2026-01-23  
> **状态**: 待确认  
> **任务数**: 8  

---

## 开发原则（重要 — AI 开发前必读）

### 隔离原则

**所有开发必须独立于生产环境，不干扰线上业务：**

1. **代码隔离**：在独立分支（如 `feature/sprint1`）上开发，不直接修改主分支
2. **数据隔离**：使用独立的测试 Bot Token + 独立的 `data_test/` 目录，不接触生产数据
3. **配置隔离**：通过 `.env.test` 配置测试环境，生产的 `.env` 不改动
4. **功能开关**：新功能通过环境变量 Feature Flag 控制，部署后默认关闭，手动开启验证
5. **兼容性**：新代码必须向后兼容现有数据格式，不改变现有 JSON 文件结构（可以新增字段，不删除字段）
6. **现有用户数据兼容**：新增字段时，代码中必须用 `.get("new_field", default_value)` 方式读取，确保老数据不报错

### 测试环境准备

**第一步：创建测试 Bot**

在 Telegram 中找 @BotFather，创建一个专门用于开发测试的 Bot（和生产 Bot 不同），获取测试 Bot Token。**绝对不能用生产 Bot Token 做开发测试。**

**第二步：准备测试环境**

```bash
# 创建测试分支
git checkout -b feature/sprint1

# 复制测试配置
cp bot/.env bot/.env.test

# 修改 .env.test 中的以下配置：
# TELEGRAM_BOT_TOKEN=测试bot的token（不是生产bot！）
# DATA_DIR=./data_test
# ADMIN_TELEGRAM_IDS=测试管理员的ID
```

**第三步：修改 `config.py` 支持加载 `.env.test`**

在 `config.py` 开头的 `.env` 加载逻辑中增加判断：

```python
# 优先加载 .env.test（如果存在），否则加载 .env
test_env_path = os.path.join(os.path.dirname(__file__), '.env.test')
env_path = os.path.join(os.path.dirname(__file__), '.env')

if os.path.exists(test_env_path):
    load_dotenv(test_env_path, override=True)
    print("⚠️  Loaded .env.test (TEST MODE)")
elif os.path.exists(env_path):
    load_dotenv(env_path, override=True)
else:
    load_dotenv(override=True)
```

**注意**：部署到生产时，确保 bot/ 目录下没有 `.env.test` 文件，否则会加载测试配置。`.env.test` 必须加入 `.gitignore`。

**第四步：启动测试 Bot**

```bash
cd bot
python main.py
# 看到 "⚠️ Loaded .env.test (TEST MODE)" 确认是测试环境
```

### Feature Flag 机制

通过环境变量控制新功能的开关，在 `config.py` 中统一定义：

```python
# Feature Flags（新功能开关，默认全部关闭）
FEATURE_SOURCE_HEALTH = os.getenv("FEATURE_SOURCE_HEALTH", "false").lower() == "true"
FEATURE_PAYMENT = os.getenv("FEATURE_PAYMENT", "false").lower() == "true"
FEATURE_GROUP_CHAT = os.getenv("FEATURE_GROUP_CHAT", "false").lower() == "true"
```

在代码中使用：
```python
from config import FEATURE_SOURCE_HEALTH
if FEATURE_SOURCE_HEALTH:
    # 执行新功能逻辑
```

**测试环境** `.env.test` 中打开所有开关：
```bash
FEATURE_SOURCE_HEALTH=true
FEATURE_PAYMENT=true
FEATURE_GROUP_CHAT=true
```

**生产环境** `.env` 中默认全部关闭，验证通过后逐个打开。

### 文件修改冲突提醒

以下文件被多个任务修改，必须按文档的开发顺序执行，避免冲突：

| 文件 | 涉及任务 | 注意事项 |
|------|---------|---------|
| `prompts/report.txt` | T1, T2 | T1 先改（加去重指令），T2 再改（改结构） |
| `handlers/start.py` | T6, T8 | T8 先改（修 Bug），T6 再改（翻译补全） |
| `main.py` | T3, T5, T7 | 按 T3→T5→T7 顺序，各自新增独立的 handler 注册和定时任务 |
| `services/rss_fetcher.py` | T1, T2, T3 | T3 加健康记录钩子，T1/T2 只改数据清洗逻辑，互不影响 |

### 合并与部署流程

1. 每个任务完成后在测试环境验证，通过验收标准
2. 所有任务完成后，在 `feature/sprint1` 分支上做最终集成测试
3. 集成测试通过后，合并到主分支：`git merge feature/sprint1`
4. 部署前：
   - 确保删除 `bot/.env.test`（或确认 `.gitignore` 已排除）
   - 在生产 `.env` 中逐个开启 Feature Flag
   - 重新构建 Docker：`docker compose build && docker compose up -d`
5. 部署后观察 24 小时，确认无异常

---

## 任务总览与依赖关系

```
优先级 1（快速修复，无依赖）：
  T6: /help 社群入口 + 翻译补全
  T8: Bug修复 - 新用户偏好消息消除

优先级 2（核心体验，可并行）：
  T1: 内容去重优化 ─────────────┐
  T2: 简报视觉重构 ←────────────┘（T2 依赖 T1 的去重逻辑）

优先级 3（基础设施，有顺序）：
  T3: RSS 错误处理 + AI 自修复 + 通知
  T4: 信息源健康看板 + 管理工具 ←── 依赖 T3 的健康数据

优先级 4（商业化，依赖 T3/T4）：
  T5: 付费体系（权限组件化 + Telegram 支付）

优先级 5（增长，依赖 T5）：
  T7: 群聊功能 ←── 依赖 T5 的权限系统判断免费/付费
```

### 建议开发顺序

| 阶段 | 任务 | 预估时间 | 可并行 |
|------|------|---------|--------|
| **第一阶段** | T6 + T8 | 0.5 天 | 是（两个互相独立） |
| **第二阶段** | T1 → T2 | 2 天 | T1 完成后再做 T2 |
| **第三阶段** | T3 → T4 | 2-3 天 | T3 完成后再做 T4 |
| **第四阶段** | T5 | 2-3 天 | 独立开发 |
| **第五阶段** | T7 | 2 天 | 依赖 T5 |

---

## T1：内容去重优化（语义级）

### 需求背景

当前系统只做 RSS 条目 ID 去重，用户反馈仍有两类重复：
- 不同信息源报道同一事件（如 CoinDesk 和 Cointelegraph 都发了 "ETH 突破 4000"）
- 标题内容和摘要正文重复叙述

### 需求详情

#### 1. 跨源语义去重

- **位置**：两阶段筛选的 Stage 2（精选去重阶段），修改 `services/content_filter.py`
- **逻辑**：在 Stage 2 的 AI prompt 中明确要求：
  - 识别语义相同的新闻条目（不同源报道同一事件）
  - 只保留最早发布 / 内容最完整的那条
  - 保留的条目标注"综合多家媒体报道"或列出其他来源
- **不改变**：Stage 1 粗筛逻辑不变，去重在 Stage 2 做

#### 2. 标题-摘要互补

- **位置**：简报生成阶段，修改 `prompts/report.txt`
- **逻辑**：在 prompt 中明确要求：
  - 如果标题已经概括核心信息，摘要应补充标题未涵盖的细节
  - 摘要不应重复标题中已有的内容

#### 3. 输出后处理

- **位置**：`services/report_generator.py`，在 AI 输出后加一步检查
- **逻辑**：
  - 对 AI 输出的所有条目标题做相似度比对（简单字符串相似度 > 80% 则标记）
  - 发现高度相似条目时合并为一条
  - 这是兜底机制，防止 AI 漏掉

### 技术实现要点

- 修改文件：`services/content_filter.py`、`prompts/filtering.txt`、`prompts/report.txt`、`services/report_generator.py`
- 新增函数：`deduplicate_by_similarity(items)` — 基于标题相似度的后处理去重
- 不新增依赖：相似度比对用 Python 标准库 `difflib.SequenceMatcher`

### 测试用例

| # | 测试场景 | 输入 | 预期结果 |
|---|---------|------|---------|
| 1 | 同事件不同源 | 3 条来自不同源但描述同一事件的新闻 | 只输出 1 条，标注多家报道 |
| 2 | 标题-摘要重复 | 标题 "ETH 突破 4000"，摘要也从 "ETH 突破 4000" 开始 | 摘要应补充额外信息 |
| 3 | 无重复内容 | 5 条完全不同的新闻 | 全部保留，无误删 |
| 4 | 相似标题兜底 | 2 条标题相似度 > 90% 的条目通过 AI 筛选 | 后处理合并为 1 条 |

### 验收标准

- [ ] 同一事件的多源报道合并为 1 条（抽测 3 天简报，重复率 < 5%）
- [ ] 标题和摘要不存在明显重复叙述
- [ ] 不误删真正不同的新闻条目
- [ ] 不影响现有筛选性能（处理时间增加 < 10%）

---

## T2：简报视觉重构

### 需求背景

用户反馈简报排版问题：第二部分占 3/4 篇幅但重点应是 AI 摘要；链接重复；有信息源前缀噪音。

### 需求详情

#### 1. AI 摘要部分重构（简报主体）

- **目标**：AI 摘要从"简单罗列"变为"分主题段落式总结"
- **位置**：修改 `prompts/report.txt`
- **新结构**：
  ```
  📰 Web3 每日简报
  📅 2026年X月X日

  ━━━━━━━━━━━━━━━━━━━━━

  🔥 今日核心摘要

  【DeFi 动态】
  今日 DeFi 领域最值得关注的是...（2-3 句连贯总结）

  【Layer2 进展】
  Arbitrum 和 Optimism 方面...（2-3 句连贯总结）

  【市场要闻】
  ...

  ━━━━━━━━━━━━━━━━━━━━━

  📋 详细信息（共 N 条）

  1. 标题 — 来源 🔗
  2. 标题 — 来源 🔗
  ...

  ━━━━━━━━━━━━━━━━━━━━━

  📊 今日统计
  ...
  ```

#### 2. 噪音前缀过滤

- **位置**：`services/content_filter.py` 或 `services/rss_fetcher.py`（抓取时清洗）
- **过滤列表**（可配置）：
  ```python
  NOISE_PREFIXES = [
      "blockbeats 消息，",
      "BlockBeats 消息，",
      "转发 ",
      "深潮 TechFlow 消息，",
      "Odaily 星球日报讯，",
      "金色财经报道，",
      "PANews ",
  ]
  ```
- 在 RSS 抓取后或 AI 筛选前，自动清除这些前缀

#### 3. 链接去重

- **规则**：每条新闻只保留一个链接入口（标题即链接），去掉底部重复的"查看原文"

#### 4. 排版细节

- 破折号统一使用 `—`（em dash），避免 `——` 占两行
- Telegram 消息中的分割线统一风格

### 技术实现要点

- 修改文件：`prompts/report.txt`、`services/report_generator.py`、`services/rss_fetcher.py`
- 新增配置：`NOISE_PREFIXES` 列表（在 `config.py` 中，可通过 .env 配置）
- 修改简报的 Telegram 消息格式化逻辑

### 测试用例

| # | 测试场景 | 输入 | 预期结果 |
|---|---------|------|---------|
| 1 | 摘要分主题 | 15 条涵盖 DeFi/L2/市场的新闻 | 摘要部分按主题分段总结 |
| 2 | 前缀过滤 | 标题 "blockbeats 消息，ETH 突破 4000" | 过滤后 "ETH 突破 4000" |
| 3 | 链接不重复 | 一条带链接的新闻 | 标题处有链接，无额外"查看原文" |
| 4 | 破折号排版 | 包含 "——" 的内容 | 显示为 "—"，不换行 |

### 验收标准

- [ ] AI 摘要部分按主题分段落展示，为简报的主要内容区域
- [ ] 详细列表部分精简，每条仅一行（标题 + 来源 + 链接）
- [ ] 无 "blockbeats 消息" 等噪音前缀出现
- [ ] 每条新闻只有一个链接入口
- [ ] 破折号不出现占两行的情况

---

## T3：RSS 源错误处理 + AI 自修复 + 通知机制

### 需求背景

多个网站 RSS 获取持续失败但无人知晓；用户自定义源失效后用户不知情。

### 需求详情

#### 1. 错误检测与记录

- **新增数据目录**：`data/source_health/`
- **每次抓取后记录**：
  ```json
  {
    "source_name": "Odaily",
    "url": "https://...",
    "category": "websites",
    "owner": "default",          // "default" 或 用户 telegram_id
    "status": "error",           // "ok" / "error" / "timeout" / "invalid_content"
    "error_type": "404",
    "error_detail": "HTTP 404 Not Found",
    "timestamp": "2026-01-23T10:00:00",
    "consecutive_failures": 3
  }
  ```
- 存储方式：每个源一个 JSON 文件（`data/source_health/{source_hash}.json`），记录最近 30 天的状态历史

#### 2. AI 自动修复流程

- **触发条件**：某个源连续失败 >= 3 次
- **修复流程**：
  1. 收集错误信息（状态码、错误类型、响应内容前 200 字符）
  2. 调用 AI 分析，prompt 包含：错误信息 + 源 URL + 常见 RSS 路径模板
  3. AI 返回：诊断原因 + 建议的新 URL 列表（最多 5 个）
  4. 自动逐一测试建议的 URL
  5. 找到可用的 → 更新源配置 + 标记状态为 "ai_repaired_observing"
  6. 全部失败 → 标记为 "repair_failed" + 触发通知
- **修复次数限制**：每个源最多 3 轮 AI 修复（每轮 AI 给 5 个建议 = 最多测 15 个 URL）
- **观察期**：修复后连续 3 天成功 → 状态变为 "stable"
- **再次失败**：已修复的源再次失败 → 重新进入修复流程；累计修复失败 > 3 轮 → 标记 "permanently_failed"

#### 3. 通知机制

| 事件 | 通知对象 | 通知方式 | 消息内容 |
|------|---------|---------|---------|
| 公共源连续失败 3 次 | 管理员 | Bot 消息 | "⚠️ 公共信息源 {name} 连续 3 次获取失败（{error_type}），正在尝试 AI 修复..." |
| 公共源 AI 修复成功 | 管理员 | Bot 消息 | "✅ {name} 已自动修复，新地址：{new_url}，观察中..." |
| 公共源 AI 修复失败 | 管理员 | Bot 消息 | "❌ {name} 自动修复失败，需要人工处理。错误：{error}" |
| 用户自定义源失败 3 次 | 该用户 | Bot 消息 | "你添加的信息源 {name} 近期获取失败，可能需要更新链接。使用 /sources 管理你的信息源。" |
| 用户源 AI 修复成功 | 该用户 | Bot 消息 | "✅ 你的信息源 {name} 已自动修复，无需操作。" |

- 通知频率限制：同一个源的相同状态通知，24 小时内只发一次

### 技术实现要点

- 新增文件：`services/source_health_monitor.py` — 健康检测 + AI 修复 + 通知
- 修改文件：`services/rss_fetcher.py` — 在 `fetch_single_source()` 函数中，每次抓取结束后调用健康记录
- 新增目录：`data/source_health/`
- 新增 prompt 文件：`prompts/source_repair.txt` — AI 修复用的 prompt
- 定时任务：在现有预抓取任务（`prefetch_all_user_sources`）执行后，加一步健康检查和修复

#### AI 修复 Prompt 框架（`prompts/source_repair.txt`）

```
你是一个 RSS 源诊断专家。一个 RSS 信息源获取失败了，请分析原因并建议修复方案。

## 失败信息
- 源名称: {source_name}
- 当前 URL: {current_url}
- 错误类型: {error_type}
- 错误详情: {error_detail}
- 响应内容前 200 字符: {response_preview}
- 连续失败次数: {consecutive_failures}

## 常见 RSS 路径模板
/rss.xml, /rss, /feed, /feed.xml, /atom.xml, /index.xml, /feed/rss,
/blog/rss, /news/rss, /?feed=rss2, /arc/outboundfeeds/rss/

## 请输出 JSON 格式：
{
  "diagnosis": "简短诊断原因（1-2句话）",
  "suggested_urls": [
    "建议尝试的新 URL 1",
    "建议尝试的新 URL 2",
    ...最多 5 个
  ],
  "confidence": "high/medium/low"
}

注意：
- 基于域名和错误信息推测可能的新路径
- 如果是 WAF/反爬问题，建议可能需要添加 User-Agent
- 如果是永久性的（网站关闭），confidence 设为 low
```

### 测试方式

使用 pytest mock 模拟 RSS 抓取失败：

```python
# 在 tests/ 中编写测试
import pytest
from unittest.mock import patch, AsyncMock

async def test_source_health_failure_detection():
    """模拟源连续失败 3 次，验证触发 AI 修复"""
    with patch('services.rss_fetcher.fetch_single_source') as mock_fetch:
        # 模拟返回空列表（抓取失败）
        mock_fetch.return_value = []
        # ... 执行 3 次抓取并验证健康状态
```

不要用真实的外部 URL 做测试（网络不可控），全部用 mock。

### 测试用例

| # | 测试场景 | 操作 | 预期结果 |
|---|---------|------|---------|
| 1 | 正常源 | mock 抓取成功 | 记录 status="ok"，不触发修复 |
| 2 | 源连续失败 3 次 | mock 3 次 HTTPStatusError(404) | 触发 AI 修复流程 |
| 3 | AI 修复成功 | mock AI 返回可用 URL + mock URL 测试成功 | 自动更新源 + 通知管理员 |
| 4 | AI 修复失败 | mock AI 返回的 URL 全部不可用 | 标记 repair_failed + 通知管理员 |
| 5 | 公共源失败通知 | mock 公共源连续失败 | 管理员收到 Bot 消息通知 |
| 6 | 用户源失败通知 | mock 用户自定义源连续失败 | 该用户收到 Bot 消息通知 |
| 7 | 修复后再次失败 | 已修复源再次 mock 连续失败 | 重新进入修复流程 |
| 8 | 通知频率限制 | 同一源 1 小时内多次失败 | 24 小时内只通知一次 |

### 验收标准

- [ ] 每个 RSS 源的抓取状态被正确记录到 `data/source_health/`
- [ ] 连续失败 3 次自动触发 AI 修复
- [ ] AI 修复成功后源配置被正确更新
- [ ] 公共源问题通知到管理员、用户源问题通知到用户
- [ ] 通知不会重复发送（24h 内同一状态只发一次）
- [ ] 不影响正常源的抓取性能

---

## T4：信息源健康看板 + 管理员工具

### 需求背景

管理员缺少信息源状态的可视化工具和批量管理能力。

### 依赖

- 依赖 T3（使用 T3 记录的健康数据）

### 需求详情

#### 1. 管理员信息源看板

- **入口**：管理员控制台 → 新增按钮「📡 信息源管理」
- **展示内容**：

  ```
  📡 信息源状态
  ━━━━━━━━━━━━━━━━━━━━━

  ✅ 正常（6 个）
    Cointelegraph — 100% — 最后: 10:00
    CoinDesk — 98% — 最后: 10:00
    Block Beats — 95% — 最后: 10:00
    ...

  ⚠️ 降级（1 个）
    TechFlow — 67% — 最后: 08:00
    → 原因: 间歇性超时

  ❌ 失败（2 个）
    Odaily — 0% — 最后成功: 3天前
    → AI 修复中...
    Foresight — 0% — 需人工处理

  ━━━━━━━━━━━━━━━━━━━━━
  总计: 9 个源 | 成功率: 78%
  ```

- **操作按钮**：
  - 「🔄 刷新」— 重新抓取所有源状态
  - 「➕ 批量添加」— 进入批量添加流程
  - 「📋 待处理请求」— 查看用户提交的信息源请求

#### 2. 批量添加/管理

- 管理员发送格式：
  ```
  名称1 | https://xxx/rss.xml
  名称2 | https://yyy/feed
  ```
- 系统自动逐条验证 URL：
  - ✅ 可用 → 添加到默认源
  - ❌ 不可用 → 返回失败原因
- 管理员可以一键禁用/启用某个源（不删除，只是暂时停止抓取）

#### 3. 用户请求队列

- 用户通过"推荐信息源"提交的请求统一存到 `data/source_requests.json`
- 管理员看到待处理列表：
  ```
  📋 待处理信息源请求（3 条）

  1. user_023 申请添加: @thejayden
     时间: 2026-01-20
     [✅ 批准并配置] [❌ 拒绝]

  2. user_025 申请添加: decrypt.co
     时间: 2026-01-21
     [✅ 批准并配置] [❌ 拒绝]
  ```
- **批准流程**：
  - 管理员点击「批准」后，系统提示管理员输入 RSS URL
  - 对于网站类型：系统先自动尝试检测 RSS（调用 `auto_detect_rss`），检测到则自动填入；未检测到则让管理员手动输入
  - 对于 Twitter 账号：管理员需要手动提供 RSS.app 生成的 RSS URL
  - URL 验证通过后，自动添加到该用户的信息源
- 拒绝 → 通知用户原因

### 技术实现要点

- 修改文件：`handlers/admin.py` — 新增信息源管理入口和交互逻辑
- 新增文件：`data/source_requests.json` — 用户请求队列
- 读取 T3 的 `data/source_health/` 数据来展示看板
- 新增配置字段：源的 `enabled` 开关（在 DEFAULT_USER_SOURCES 中增加状态标记）

### 测试用例

| # | 测试场景 | 操作 | 预期结果 |
|---|---------|------|---------|
| 1 | 查看看板 | 管理员点击「信息源管理」 | 显示分级别的源列表和成功率 |
| 2 | 批量添加 | 发送 3 条 "名称\|URL" | 系统验证并返回成功/失败结果 |
| 3 | 禁用源 | 点击某个源的「禁用」按钮 | 该源不再被抓取，下次看板标记为已禁用 |
| 4 | 查看请求队列 | 有用户提交了信息源建议 | 管理员看到待处理列表 |
| 5 | 批准请求 | 批准一条用户请求 | 源被添加到该用户配置，用户收到通知 |

### 验收标准

- [ ] 管理员可在 Bot 中查看所有信息源的实时状态（成功率 + 最后抓取时间）
- [ ] 管理员可批量添加/禁用信息源
- [ ] 用户提交的信息源请求有统一的队列和处理流程
- [ ] 看板数据与实际抓取状态一致

---

## T5：付费体系（权限组件化 + Telegram 支付）

### 需求背景

需要实现免费/付费功能区分，且权限边界要可配置而非硬编码。

### 依赖

- 建议在 T3/T4 完成后开发（付费功能需要信息源管理基础稳定）

### 需求详情

#### 1. 权限组件化系统

- **新增配置文件**：`data/plan_config.json`
  ```json
  {
    "plans": {
      "free": {
        "label": "Free",
        "price_monthly_usd": 0,
        "features": {
          "public_sources": true,
          "custom_sources": false,
          "ai_chat": true,
          "ai_chat_daily_limit": 5,
          "max_digest_items": 15
        }
      },
      "pro": {
        "label": "Pro",
        "price_monthly_usd": 20,
        "features": {
          "public_sources": true,
          "custom_sources": true,
          "ai_chat": true,
          "ai_chat_daily_limit": -1,
          "max_digest_items": 30
        }
      }
    },
    "default_plan": "free"
  }
  ```
- **权限检查工具函数**：
  ```python
  # utils/permissions.py（新增）
  def check_feature(telegram_id: str, feature: str) -> bool:
      """检查用户是否有某个功能权限"""
      plan = get_user_plan(telegram_id)
      config = load_plan_config()
      return config["plans"][plan]["features"].get(feature, False)

  def get_feature_limit(telegram_id: str, feature: str) -> int:
      """获取用户某个功能的限额"""
      ...

  def require_plan(feature: str):
      """装饰器：功能执行前检查权限，无权限则提示升级"""
      ...
  ```
- **各功能模块接入**：在需要权限控制的地方加上 `@require_plan("custom_sources")` 装饰器
- **管理员可修改**：管理员通过 Bot 命令修改 `plan_config.json`，调整免费/付费边界

#### 2. 用户订阅状态管理

- **用户数据扩展**（在 `users.json` 中新增字段）：
  ```json
  {
    "telegram_id": "123456",
    "plan": "free",
    "plan_expires": null,
    "payment_history": []
  }
  ```
- **向后兼容**：老用户数据没有 `plan` 字段时，代码中必须用 `user.get("plan", "free")` 读取，默认为 "free"
- 用户可查看当前计划：设置页面 → 显示 "当前: 免费版" 或 "当前: Pro (到期: 2026-02-23)"

#### 3. 订阅到期处理

- **定时检查**：在每日数据清理任务（`00:30`）中增加一步：扫描所有用户，检查 `plan_expires`
- **到期处理**：
  - `plan_expires` 非空且已过期 → 自动将 `plan` 改为 "free"
  - 通知用户："你的 Pro 订阅已到期，已恢复为免费版。续费请使用设置菜单。"
- **使用时检查**（双保险）：`check_feature()` 函数中也检查到期时间，避免定时任务漏掉

#### 4. Telegram Payments 集成

- 使用 `python-telegram-bot` 内置的 Payments 支持
- **支付流程**：
  1. 用户在设置页面点击「⭐ 升级到 Pro」
  2. Bot 发送包含价格信息的 Invoice
  3. 用户通过 Telegram 内置支付完成付款
  4. Bot 收到 `successful_payment` 回调 → 更新用户 plan 为 "pro"，设置 `plan_expires` 为 30 天后
  5. 记录支付历史
- **需要配置**：Telegram Payment Provider Token（通过 @BotFather → /mybots → Payments 设置）
- **测试支付**：
  - 在 @BotFather 中选择 "Stripe TEST" 作为支付提供商（测试环境）
  - 测试卡号：`4242 4242 4242 4242`，有效期任意未来日期，CVV 任意 3 位
  - 测试环境的 `.env.test` 中配置：`PAYMENT_PROVIDER_TOKEN=测试provider的token`
  - 生产环境切换为正式 Stripe（或其他 provider）的 token
- **订阅管理**：查看当前计划、到期时间；暂不做自动续费，到期后手动续费

#### 4. 免费用户升级引导

- 免费用户尝试使用付费功能时（如点击"添加自定义信息源"）：
  ```
  🔒 此功能需要 Pro 版

  升级到 Pro 可享受：
  • 自定义信息源（Twitter/网站）
  • 无限 AI 对话
  • 更多精选内容

  [⭐ 升级 Pro — $20/月]
  ```
- 邀请奖励：用户邀请新用户注册，邀请者可获得 1 次免费体验（数据存在 users.json 的 `referral_credits` 字段）

### 技术实现要点

- 新增文件：
  - `utils/permissions.py` — 权限检查工具
  - `handlers/payment.py` — 支付流程处理
  - `data/plan_config.json` — 权限配置表
- 修改文件：
  - `handlers/sources.py` — 添加自定义源前检查权限
  - `handlers/chat.py` — AI 聊天前检查每日限额
  - `handlers/settings.py` — 新增"我的计划"入口
  - `utils/json_storage.py` — 新增 plan 相关存储函数
  - `main.py` — 注册 payment handler
- 注意事项：
  - Telegram Payments 需要 Payment Provider Token（在 @BotFather 中配置）
  - 测试阶段使用 Telegram 的测试支付 provider（Stripe Test）

### 测试用例

| # | 测试场景 | 操作 | 预期结果 |
|---|---------|------|---------|
| 1 | 免费用户受限 | 免费用户尝试添加自定义源 | 显示升级提示 + 升级按钮 |
| 2 | 升级支付 | 点击升级按钮并完成支付 | 用户 plan 变为 "pro"，功能解锁 |
| 3 | Pro 用户功能 | Pro 用户添加自定义源 | 正常添加，无限制 |
| 4 | 权限配置修改 | 管理员修改 plan_config.json | 权限边界即时生效 |
| 5 | AI 聊天限额 | 免费用户一天内发 6 条消息 | 第 6 条提示"今日免费额度已用完" |
| 6 | 计划查看 | 用户在设置中查看计划 | 显示当前计划和到期时间 |
| 7 | 邀请奖励 | 用户 A 邀请用户 B 注册 | 用户 A 获得 1 次免费体验 |

### 验收标准

- [ ] 权限配置表 `plan_config.json` 可由管理员灵活修改
- [ ] 免费用户受限功能正确拦截并展示升级引导
- [ ] Telegram 支付流程完整可用（测试环境下）
- [ ] 支付成功后用户权限即时升级
- [ ] 用户可查看自己的当前计划和到期时间
- [ ] 各功能模块的权限检查不影响已有功能的正常运行

---

## T6：/help 社群入口 + 翻译补全

### 需求背景

/help 没有社群入口；部分 UI 有未翻译的中英混杂文案。

### 依赖

无，独立任务。

### 需求详情

#### 1. /help 添加社群入口

- 在 /help 输出末尾增加一行：
  - 中文：`更多问题，加入用户群：https://t.me/voiverse`
  - 英文：`For more help, join our community: https://t.me/voiverse`
  - 日/韩：相应翻译
- 在 `locales/ui_strings.py` 中新增 `help_community_link` 键

#### 2. 翻译补全扫描

- 扫描所有 handler 文件，找出直接写死的中文或英文字符串
- 特别关注 `retry_round_2_callback` 函数中已发现的硬编码（`start.py` 第 348-362 行有硬编码的中文）
- 迁移到 `locales/ui_strings.py`，确保 zh/en/ja/ko 四种语言完整

### 技术实现要点

- 修改文件：`handlers/start.py`（修复已发现的硬编码）、所有 handlers 文件（扫描）、`locales/ui_strings.py`
- 新增翻译键：`help_community_link`、以及扫描发现的其他硬编码

### 测试用例

| # | 测试场景 | 操作 | 预期结果 |
|---|---------|------|---------|
| 1 | 中文用户 /help | 中文用户发送 /help | 底部有中文社群链接 |
| 2 | 英文用户 /help | 英文用户发送 /help | 底部有英文社群链接 |
| 3 | 硬编码检查 | 切换到日文环境遍历所有功能 | 无中文/英文硬编码出现 |

### 验收标准

- [ ] /help 输出包含社群链接，根据用户语言自动适配
- [ ] `handlers/` 目录下无硬编码的中文或英文 UI 文案（全部使用 `ui_strings.py`）
- [ ] zh/en/ja/ko 四种语言的 UI 文案完整无缺失

---

## T7：群聊功能

### 需求背景

Bot 无法被拉入群聊，缺少通过群聊获取新用户的增长渠道。

### 依赖

- 依赖 T5（权限系统用于判断群聊的免费/付费能力）

### 需求详情

#### 1. Bot 群聊支持

- **BotFather 设置**：确保 Bot 的 Group Privacy 设置为 "Disable"（允许 bot 读取群内所有消息/命令）
- **群内行为规则**：
  - Bot 在群里**不响应**普通文字消息（不做 AI 聊天）
  - Bot 在群里**只做**：每日定时推送公共简报 + 响应 `/setup` 命令
  - 只有**群管理员**可发送 `/setup` 配置群的偏好

#### 2. 群配置流程

- 群管理员在群内发送 `/setup`
- **权限检查**：使用 Telegram API `context.bot.get_chat_administrators(chat_id)` 获取群管理员列表，验证发送者是否在列表中。非管理员发 `/setup` → 回复"此命令仅群管理员可用"
- Bot 回复配置选项（使用 InlineKeyboard）：
  - 选择群偏好领域（多选）
  - 选择推送时间
  - 选择语言
- 配置存储到 `data/group_configs/{group_id}.json`：
  ```json
  {
    "group_id": "-100123456789",
    "group_title": "Web3 中文社区",
    "admin_id": "345396984",
    "profile": "关注 DeFi、Layer2、以太坊生态...",
    "push_hour": 9,
    "language": "zh",
    "created": "2026-01-23T10:00:00",
    "enabled": true
  }
  ```

#### 3. 群内公共简报

- 推送内容：基于群配置的画像，从公共信息源中筛选（不使用个人信息源）
- 推送格式与个人版一致，但末尾附带引导文案：
  ```
  ━━━━━━━━━━━━━━━━━━━━━
  🤖 想获得个性化推荐？
  私聊发送 /start，配置属于您自己偏好的 Web3 信息降噪 Bot
  Send "/start" in a private message to configure your own preferred web3 noise reduction bot.
  ━━━━━━━━━━━━━━━━━━━━━
  ```

#### 4. 群管理

- 管理员可通过 Bot 控制台查看已加入的群列表
- 可远程启用/禁用某个群的推送
- **Bot 被移出群时**：监听 `ChatMemberUpdated` 事件，当 Bot 的状态变为 "left" 或 "kicked" 时，自动将该群配置标记为 `enabled: false`

### 技术实现要点

- 新增文件：
  - `handlers/group.py` — 群聊相关 handler
  - `data/group_configs/` — 群配置目录
- 修改文件：
  - `main.py` — 注册群聊 handler + 群推送定时任务
  - `services/digest_processor.py` — 支持基于群画像生成公共简报
  - `handlers/admin.py` — 新增群管理入口
- 群消息过滤：使用 `filters.ChatType.GROUPS` 区分私聊和群聊
- 定时任务：在现有推送循环中增加群推送逻辑

### 测试用例

| # | 测试场景 | 操作 | 预期结果 |
|---|---------|------|---------|
| 1 | Bot 入群 | 将 Bot 拉入测试群 | Bot 正常加入，发送欢迎消息 |
| 2 | 群配置 | 群管理员发送 /setup | 显示配置选项，可设置偏好 |
| 3 | 群内推送 | 到达推送时间 | 群内收到公共简报 + 引导文案 |
| 4 | 不响应普通消息 | 群内有人发普通消息 | Bot 不回复 |
| 5 | 引导转化 | 用户看到引导，私聊发 /start | 正常进入个人注册流程 |
| 6 | 管理员查看群 | 管理员在控制台查看群列表 | 显示已加入群的列表和状态 |

### 验收标准

- [ ] Bot 可被拉入群聊并正常工作
- [ ] 群管理员可配置群的偏好和推送时间
- [ ] 群内每日推送公共简报
- [ ] 群内简报末尾有中英双语引导文案
- [ ] Bot 在群内不响应普通消息
- [ ] 管理员可在控制台管理群列表

---

## T8：Bug 修复 — 新用户偏好消息自动消除

### 需求背景

运营反馈：新用户完成 3 轮 AI 对话后，系统生成的偏好摘要消息随后被自动消除了。

### 根因分析

已定位到 `handlers/start.py` 的 `confirm_profile` 函数（第 366-464 行）：

1. **第 309 行**：Round 3 结束，AI 生成偏好摘要，通过 `reply_text` 发送给用户，附带"确认"按钮
2. **第 387 行**：用户点击"确认"后，`query.edit_message_text("⏳ 保存中...")` **直接覆盖了偏好摘要消息**
3. **第 449 行**：保存完成后，再次 `query.edit_message_text("✅ 偏好已保存")` **再次覆盖**

**结果**：用户的偏好摘要始终被 `edit_message_text` 覆盖掉了，用户翻回去看不到自己的偏好。

### 修复方案

- **不使用 `edit_message_text` 覆盖偏好摘要**
- 改为：
  1. 用户点击"确认"后，偏好摘要消息**保留不动**（不 edit）
  2. 通过 `context.bot.send_message()` **新发一条消息**显示"⏳ 保存中..."
  3. 保存完成后，edit 这条"保存中"的消息为"✅ 偏好已保存 + 信息源选择"

### 技术实现要点

- 修改文件：`handlers/start.py` 的 `confirm_profile` 函数
- 核心改动：将 `query.edit_message_text` 改为 `context.bot.send_message`（新发消息）
- 保留偏好摘要消息不被覆盖

### 测试用例

| # | 测试场景 | 操作 | 预期结果 |
|---|---------|------|---------|
| 1 | 完成注册 | 走完 3 轮对话并确认偏好 | 偏好摘要消息保留在聊天记录中 |
| 2 | 回看偏好 | 注册完成后往上翻聊天记录 | 能看到 AI 生成的偏好摘要 |
| 3 | 确认后流程 | 确认偏好后 | 新消息显示"保存成功" + 信息源选择 |

### 验收标准

- [ ] 注册完成后，偏好摘要消息在聊天记录中可见、不被删除/覆盖
- [ ] "保存中"和"保存成功"的进度提示正常显示（不影响偏好消息）
- [ ] 后续流程（信息源选择等）不受影响

---

## 附录 A：文件修改清单

| 任务 | 新增文件 | 修改文件 |
|------|---------|---------|
| T1 | — | `services/content_filter.py`, `services/report_generator.py`, `prompts/filtering.txt`, `prompts/report.txt` |
| T2 | — | `prompts/report.txt`, `services/report_generator.py`, `services/rss_fetcher.py`, `config.py` |
| T3 | `services/source_health_monitor.py`, `prompts/source_repair.txt`, `data/source_health/` | `services/rss_fetcher.py`, `main.py` |
| T4 | `data/source_requests.json` | `handlers/admin.py` |
| T5 | `utils/permissions.py`, `handlers/payment.py`, `data/plan_config.json` | `handlers/sources.py`, `handlers/chat.py`, `handlers/settings.py`, `utils/json_storage.py`, `main.py` |
| T6 | — | `handlers/start.py`, `locales/ui_strings.py`, 其他 handlers |
| T7 | `handlers/group.py`, `data/group_configs/` | `main.py`, `services/digest_processor.py`, `handlers/admin.py` |
| T8 | — | `handlers/start.py` |

## 附录 B：环境隔离 Checklist

开发前确认（每个任务开始前检查）：

- [ ] 当前在 `feature/sprint1` 分支上（不是 main/master）
- [ ] `bot/.env.test` 存在且配置了测试 Bot Token
- [ ] `bot/.env.test` 中 `DATA_DIR=./data_test`
- [ ] `.gitignore` 包含 `.env.test` 和 `data_test/`
- [ ] 启动后看到 "⚠️ Loaded .env.test (TEST MODE)" 提示
- [ ] 测试 Bot 和生产 Bot 是**不同的** Bot（不同 Token）

部署前确认：

- [ ] `bot/.env.test` 不存在或已从部署目录删除
- [ ] Feature Flag 在生产 `.env` 中按需开启
- [ ] 运行 `python -m pytest tests/ -v` 全部通过
- [ ] 在测试环境完成了所有验收标准的检查

## 附录 C：每个任务开始前 AI 必须做的事

1. **读取相关代码**：先用 Read 工具读取该任务涉及的所有"修改文件"的当前内容，理解现有逻辑
2. **读取相关 prompt**：如果涉及 prompt 修改，先读取 `prompts/` 目录下的当前 prompt 内容
3. **读取相关测试**：先读取 `tests/test_all_modules.py` 了解现有测试结构
4. **确认分支**：确认在 `feature/sprint1` 分支上
5. **确认不影响生产**：新增文件放在正确目录，不修改 `.env`（只修改 `.env.test`）

---

**文档版本**: v1.1  
**文档状态**: 待确认  
**下一步**: 确认后按开发顺序逐个实施（T6+T8 → T1→T2 → T3→T4 → T5 → T7）
