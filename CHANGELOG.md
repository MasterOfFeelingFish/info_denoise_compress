# Changelog

All notable changes to this project will be documented in this file.

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
