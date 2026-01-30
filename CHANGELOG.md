# Changelog

All notable changes to this project will be documented in this file.

## [v1.6.2] - 2026-01-30

### Summary
修复多个Bug并优化用户体验：查看原文按钮支持点击追踪、活跃用户统计修正、新用户引导流程优化、运营数据增加说明文字。

---

### Fixed

#### 1. 查看原文按钮无法追踪点击 (P0)
**问题**：用户点击"查看原文"按钮后无法追踪行为，且标题超链接可绕过监控。

**解决方案**：
- 将按钮改为两步操作：点击 → 记录埋点 → 显示URL按钮 → 打开原文
- 移除标题超链接，用户必须通过按钮访问原文

**修改文件**：
- `bot/handlers/feedback.py` - 恢复callback类型，点击后显示URL按钮
- `bot/services/digest_processor.py` - 存储 item_id → item_url 映射
- `bot/services/report_generator.py` - 移除标题超链接，添加本地化字符串

#### 2. 活跃用户数统计错误 (P0)
**问题**：活跃用户数(79)超过总用户数(58)，统计包含了已删除/未注册用户。

**解决方案**：
- 修改 `get_events_summary()` 只统计在 `users.json` 中存在的注册用户
- 新增 `total_event_users` 字段保留原始统计（用于对比）

**修改文件**：
- `bot/utils/json_storage.py` - 过滤非注册用户的事件统计

---

### Changed

#### 3. 用户画像更新逻辑增强
**改进**：将用户"点击查看原文"的行为如实告诉AI，让AI自行解读其含义。

点击原文是高价值的正向信号（用户愿意深入阅读），现在会传递给AI：
```
📖 User clicked to read (2 items): 白宫召集加密行业高管会议, Tether每周买入黄金
👎 User marked not interested (1 items): 某个不感兴趣的新闻
```

**修改文件**：
- `bot/services/profile_updater.py` - 修改 `format_feedbacks_for_ai()` 包含click事件

#### 4. 运营统计面板增加指标说明 (P1)
**改进**：为每个统计指标添加详细解释，让运营更清楚数据含义。

| 指标 | 说明 |
|------|------|
| 总事件数 | 统计周期内所有用户操作的总次数 |
| 活跃用户 | 有过任意操作的注册用户 / 总注册用户 |
| 人均事件 | 平均每个活跃用户的操作次数 |
| 活跃率 | 活跃用户占总用户的比例 |
| 查看原文 | 用户点击查看原文按钮（新增事件类型） |
| 整体满意度 | 简报末尾"有帮助"的占比 |
| 内容吸引力 | 用户主动查看原文的占比 |

**修改文件**：
- `bot/handlers/admin.py` - 添加指标说明文字

#### 5. 新用户引导流程优化 (P1)
**改进**：简化信息源选择界面，引导用户快速上手。

- 主按钮改为"🚀 立即开始（推荐）"
- 增加说明："建议先体验默认源，之后可随时在设置中添加"
- 预览更多默认源名称，让用户了解内容质量

**修改文件**：
- `bot/handlers/start.py` - 优化文案和按钮布局

---

### Technical Details

#### 活跃用户定义说明
只有以下操作会被记录为"活跃"：
- `/start` 命令 → session_start
- 点击查看原文 → item_click（新增）
- 简报反馈 → feedback_positive/negative
- 单条内容反馈 → item_dislike
- 设置变更 → settings_changed
- 信息源增删 → source_added/removed

**注意**：被动接收简报、只翻看不点击不会被记录为活跃（Telegram平台限制）。

---

## [v1.6.1] - 2026-01-29

### Summary
优化默认 RSS 信息源配置：移除失效源，新增 TechFlow 官方快讯 RSS。

---

### Changed

#### 默认 RSS 信息源优化 (`bot/.env`)

| 操作 | 源名称 | 原因 |
|------|--------|------|
| ❌ 移除 | Prediction News | HTTP 403 Cloudflare 防护，无法访问 |
| ➕ 新增 | TechFlow 快讯 | 官方 7x24h 快讯 RSS |

**更新后的信息源列表：**
- Cointelegraph ✅
- CoinDesk ✅
- The Block Beats (律动) ✅
- TechFlow Post (Substack 深度文章) ✅
- **TechFlow 快讯** (官方 7x24h 快讯) 🆕
- DeFi Rate ✅
- Event Horizon ✅
- un.Block 吴说 ✅

---

### Technical Details

#### RSS 源可用性检查结果

| 源 | URL | 状态 |
|----|-----|------|
| Cointelegraph | `cointelegraph.com/rss` | ✅ HTTP 200 |
| CoinDesk | `coindesk.com/arc/outboundfeeds/rss/` | ✅ HTTP 200 |
| The Block Beats | `api.theblockbeats.news/v1/open-api/home-xml` | ✅ HTTP 200 |
| TechFlow Post | `techflowpost.substack.com/feed` | ✅ HTTP 200 |
| TechFlow 快讯 | `techflowpost.com/api/client/common/rss.xml` | ✅ HTTP 200 |
| DeFi Rate | `defirate.com/feed` | ✅ HTTP 200 |
| Prediction News | `predictionnews.com/rss/` | ❌ HTTP 403 |
| Event Horizon | `nexteventhorizon.substack.com/feed` | ✅ HTTP 200 |
| un.Block | `unblock256.substack.com/feed` | ✅ HTTP 200 |

---

### Migration Notes

1. **新用户** - 注册时自动获得更新后的默认信息源
2. **现有用户** - 不受影响，保持原有订阅配置
3. **无需代码变更** - 仅环境变量配置更新

---

## [v1.6.0] - 2026-01-29

### Summary
推送策略从固定时间改为按用户间隔推送，分散系统负载；测试命令改为管理员专用；修复翻译截断问题。

---

### Added

#### 按用户间隔推送策略 (`config.py`, `main.py`)
- **PUSH_MODE**: 推送模式（`fixed_time` / `user_interval`）
- **PUSH_INTERVAL_HOURS**: 推送周期（默认 24 小时）
- **PUSH_QUIET_START/END**: 静默时段（默认 00:00-07:00 不推送）
- **PUSH_CHECK_INTERVAL**: 检查频率（默认每 30 分钟）

#### 新增函数
| 函数 | 文件 | 功能 |
|------|------|------|
| `interval_digest_check_job()` | main.py | 定期检查到期用户并推送 |

---

### Changed

#### 推送策略优化
- **之前**：所有用户在固定时间（09:00）同时推送
- **现在**：每个用户按各自注册时间，24小时周期循环推送
- **好处**：分散系统负载，避免API限流

#### 测试命令权限收紧
- `/test`、`/testprofile`、`/testprefetch` 改为**管理员专用**
- 非管理员使用会提示"此命令仅限管理员使用"
- 引导流程中移除所有 `/test` 相关提示

#### 引导文案更新
- "每天 09:00 推送" → "每天自动推送（约 24 小时一次）"
- 移除"使用 /test 立即体验"按钮和提示

#### 翻译稳定性修复
- `maxOutputTokens` 从 8192 增加到 16384
- 解决翻译 25 条内容时 JSON 截断问题

---

### Configuration

新增可选环境变量：
```bash
PUSH_MODE=user_interval        # 推送模式：fixed_time / user_interval
PUSH_INTERVAL_HOURS=24         # 推送周期（小时）
PUSH_QUIET_START=0             # 静默开始时间（0-23）
PUSH_QUIET_END=7               # 静默结束时间（0-23）
PUSH_CHECK_INTERVAL=30         # 检查频率（分钟）
```

---

### Migration Notes

1. **默认启用 user_interval 模式** - 新部署自动生效
2. **老用户迁移** - 系统会根据 `last_push_time` 计算下次推送时间
3. **切换回固定时间** - 设置 `PUSH_MODE=fixed_time` 即可

---

## [v1.5.0] - 2026-01-27

### Summary
引入两阶段筛选算法（v2.1），提升大数据量场景下的筛选质量和去重效果。

---

### Added

#### 两阶段筛选算法 (`services/content_filter.py`)

**Stage 1: 粗筛**
- 将原始内容按 `BATCH_SIZE` 分批处理
- 每批独立调用 AI 进行价值评估
- 按比例（`STAGE1_RATIO`）筛选进入候选池

**Stage 2: 精选去重**
- 新增 `_stage2_select()` 函数
- 对候选池进行跨批次去重（标题相似度）
- AI 综合评估，输出最终结果

#### 新增函数

| 函数 | 文件 | 功能 |
|------|------|------|
| `_stage2_select()` | content_filter.py | Stage 2 精选去重 |
| `_filter_content_batched()` | content_filter.py | 分批处理入口 |
| `_filter_single_batch()` | content_filter.py | 单批次筛选 |

---

### Changed

#### 筛选流程优化
- **之前**：所有内容一次性送入 AI（大数据量易超 token 限制）
- **现在**：分批粗筛 → 汇总候选池 → 精选去重

#### 配置自动推导
- `STAGE1_RATIO` 基于 `MAX_DIGEST_ITEMS` 和 `BATCH_SIZE` 自动计算
- 减少手动配置项，降低配置出错风险

---

### Technical Details

#### 算法流程
```
1000条原始数据
    ↓ 分 10 批，每批 100 条
    ↓ Stage 1: 每批 AI 粗筛（选 10-15%）
100条候选池
    ↓ Stage 2: 去重 + AI 精选
25条最终输出
```

#### Files Modified

| File | Changes |
|------|---------|
| `bot/services/content_filter.py` | 新增两阶段筛选逻辑 |
| `bot/config.py` | 新增 STAGE1_RATIO 自动计算 |

---

### Migration Notes

1. **无破坏性变更** - 向后兼容
2. **自动生效** - 重启 Bot 后新算法自动启用
3. **性能提升** - 大数据量（500+ 条）筛选质量显著提升

---

## [v1.4.0] - 2026-01-24

### Summary
新增用户行为埋点系统和管理员数据分析面板，为产品迭代提供数据驱动支持。

---

### Added

#### 用户行为埋点系统
- **事件追踪函数** `track_event()` - 记录用户行为到 JSONL 文件
- **事件汇总函数** `get_events_summary()` - 统计事件分布、活跃用户
- **用户事件查询** `get_user_events()` - 按用户查询历史事件
- **自动清理函数** `cleanup_old_events()` - 清理过期事件文件

#### 埋点事件类型
| 事件 | 触发时机 | 记录数据 |
|------|---------|----------|
| `session_start` | 用户发送 /start | 命令类型 |
| `feedback_positive` | 点击"有帮助" | 报告 ID |
| `feedback_negative` | 点击"没帮助"并选原因 | 原因文本 |
| `item_like` | 单条内容点赞 | 内容 ID、标题 |
| `item_dislike` | 单条内容踩 | 内容 ID、标题 |
| `settings_changed` | 更新/重置偏好 | 操作类型 |
| `source_added` | 添加信息源 | 类别、名称 |
| `source_removed` | 删除信息源 | 类别、名称 |

#### 管理员数据分析面板
- **📊 数据分析** 入口（管理员控制台新增按钮）
- **时间周期选择**：今日 / 7天 / 30天
- **概览统计**：总事件数、活跃用户、人均事件
- **事件分布**：各类型事件次数
- **反馈分析**：整体满意度、内容满意度百分比
- **活跃排行**：Top 5 活跃用户
- **详细报表**：运营洞察 + 优化建议 + 流失预警

#### 运营报表脚本
- `scripts/generate_analytics_report.py` - 生成 Markdown 格式报表

---

### Changed

#### 管理员控制台 (`handlers/admin.py`)
- 新增"📊 数据分析"按钮
- 新增 `admin_analytics()` 处理函数
- 新增 `show_analytics()` 显示统计数据
- 新增 `show_analytics_detail()` 显示运营建议

#### 配置文件 (`config.py`)
- 新增 `EVENTS_DIR` 事件存储目录
- 新增 `EVENTS_RETENTION_DAYS` 事件保留天数（默认 90 天）

#### 数据存储 (`utils/json_storage.py`)
- 新增事件追踪相关函数
- 导入 `EVENTS_DIR` 和 `EVENTS_RETENTION_DAYS`

---

### Security

- 所有分析功能均有 `is_admin()` 权限验证
- 管理员按钮仅对管理员显示（前端隐藏）
- 后端二次验证防止 callback_data 伪造攻击

---

### Technical Details

#### 数据存储格式
```
data/events/
└── events_2026-01.jsonl   # 按月分文件，JSONL 格式
```

事件格式：
```json
{"ts": "2026-01-24T09:00:00", "uid": "123456", "event": "feedback_positive", "data": {"report_id": "xxx"}}
```

#### Files Modified

| File | Changes |
|------|---------|
| `bot/config.py` | 新增 EVENTS_DIR, EVENTS_RETENTION_DAYS |
| `bot/utils/json_storage.py` | 新增埋点相关函数 |
| `bot/handlers/admin.py` | 新增数据分析面板 |
| `bot/handlers/feedback.py` | 添加反馈埋点 |
| `bot/handlers/settings.py` | 添加设置变更埋点 |
| `bot/handlers/sources.py` | 添加信息源增删埋点 |
| `bot/handlers/start.py` | 添加会话开始埋点 |
| `bot/scripts/generate_analytics_report.py` | 新增报表生成脚本 |

#### Configuration

新增可选环境变量：
```bash
EVENTS_RETENTION_DAYS=90  # 事件保留天数，默认 90
```

---

### Migration Notes

1. **无破坏性变更** - 所有新功能向后兼容
2. **自动生效** - 重启 Bot 后埋点自动开始记录
3. **存储空间** - 预计每 500 用户每月约 22MB

---

## [v1.3.0] - 2026-01-22

### Summary
Major improvements to AI reliability, language consistency, and user experience.

---

### Added

#### AI Reliability (Task 1)
- **Automatic retry mechanism** for AI filtering with up to 4 attempts
- **Model switching**: Primary model failure automatically switches to fallback model
- Retry strategy: Primary(temp=1.0) → Primary(temp=0.8) → Fallback(temp=1.0) → Fallback(temp=0.8)
- New `_call_ai_with_retry()` function in `content_filter.py`
- New `get_fallback_provider()` method in `llm_factory.py`

#### Twitter Author Extraction (Task 3)
- **Extract real Twitter handle** from tweet links (e.g., `@VitalikButerin`)
- New `extract_twitter_author()` function in `rss_fetcher.py`
- Added `author` field to content items for Twitter sources
- Source display now shows actual author instead of "Twitter Bundle 1"

#### Localization (Task 2)
- New locale strings: `reason_prefix`, `source_prefix`, `btn_like`, `btn_not_interested`
- New `LANG_CODE_TO_NAME` mapping for translation API
- New `get_translation_language()` helper function

---

### Changed

#### Language Processing (Task 2) - **Breaking Change**
- **All AI processing now uses English** (prompts, outputs, intermediate data)
- Translation happens **only at final output stage**
- Improved `get_user_target_language()` function with better detection
- Default language changed to Chinese (was English for empty profiles)
- `translate_content()` now handles all cases including mixed-language content
- Updated `filtering.txt` prompt to enforce English reason output
- Updated `translate.txt` to preserve `author` field

#### Report Format (Task 4)
- **New item format** with recommendation reason display:
  ```
  🔴 1. Title (clickable)
  Summary text...
  💡 Recommendation reason
  Source: @author
  ```
- Section-based priority indicators: 🔴 (must_read), 🟠 (macro_insights), 🔵 (others)
- `format_single_item()` now displays `reason` and `author` fields

#### Feedback Buttons (Task 5)
- **Changed dislike button** from "👎" to "不感兴趣" / "Not interested"
- `create_item_feedback_keyboard()` now accepts `lang` parameter
- Feedback buttons are now localized based on user language

#### UI Consistency
- All UI elements (buttons, prompts, headers) now respect user language setting
- `helpful_prompt` now uses locale strings instead of hardcoded check

---

### Fixed

- Fixed language mixing issue where users received mixed Chinese/English content
- Fixed AI filtering instability causing "Fallback selection" on some days
- Fixed inconsistent `reason` language (sometimes Chinese, sometimes English)

---

### Technical Details

#### Files Modified

| File | Changes |
|------|---------|
| `bot/services/content_filter.py` | Added retry logic, improved language functions |
| `bot/services/llm_factory.py` | Added fallback provider support |
| `bot/services/rss_fetcher.py` | Added Twitter author extraction |
| `bot/services/report_generator.py` | Added locale strings, updated format |
| `bot/services/digest_processor.py` | Updated translation flow |
| `bot/handlers/feedback.py` | Localized feedback buttons |
| `bot/prompts/filtering.txt` | Enforced English reason output |
| `bot/prompts/translate.txt` | Updated translation rules |

#### Configuration

No new environment variables required. Existing `OPENAI_API_KEY` enables fallback model.

---

### Migration Notes

1. **No breaking changes for users** - All changes are backward compatible
2. **Fallback model**: If you have both `GEMINI_API_KEY` and `OPENAI_API_KEY` configured, the system will automatically use the other as fallback
3. **Language**: Users with empty profiles will now default to Chinese (previously defaulted to English)

---

## [v1.2.x] - Previous versions

(See git history for previous changes)
