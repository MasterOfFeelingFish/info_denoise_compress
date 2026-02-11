# Debug 指南 - Web3 Daily Digest

> 本文档帮助你快速搭建开发环境并开始 debug 工作。
> Bug 任务清单请参考 [BUG_TRACKER.md](./BUG_TRACKER.md)。

---

## 1. 你需要自行准备的东西

| 项目 | 说明 | 获取方式 |
|------|------|----------|
| **Telegram 测试 Bot Token** | 用于开发测试，不要使用生产 Bot | 在 Telegram 中找 @BotFather，发送 `/newbot` 创建 |
| **LLM API Key** | Gemini 或 Kimi/OpenAI 任选其一 | Gemini: [Google AI Studio](https://aistudio.google.com/) 免费申请; Kimi: [Moonshot](https://platform.moonshot.cn/) |
| **你自己的 Telegram ID** | 用于配置管理员权限 | 在 Telegram 中找 @userinfobot，发送任意消息获取 |

---

## 2. 环境搭建

### 2.1 克隆代码

```bash
git clone git@github.com:WFHTask/info_denoise_compress.git
cd info_denoise_compress
git checkout sprint2-dev
```

### 2.2 配置环境变量

```bash
cp bot/.env.example bot/.env
```

编辑 `bot/.env`，填写以下**必填项**:

```bash
# 你创建的测试 Bot Token
TELEGRAM_BOT_TOKEN=你的测试Bot_Token

# 你的 Telegram ID（作为管理员）
ADMIN_TELEGRAM_IDS=你的Telegram_ID

# LLM 配置（二选一）

# 方案 A: Gemini（推荐，免费额度够用）
LLM=gemini
GEMINI_API_KEY=你的Gemini_API_Key
GEMINI_MODEL=gemini-2.0-flash
GEMINI_THINKING_LEVEL=HIGH

# 方案 B: Kimi（国内可用）
# LLM=openai
# OPENAI_API_KEY=你的Kimi_API_Key
# OPENAI_MODEL=kimi-k2-thinking
# OPENAI_API_URL=https://api.moonshot.cn/v1/chat/completions
```

> `.env.example` 中已经包含了可用的 RSS 信息源，无需修改。

### 2.3 安装依赖 & 运行

**方式一：本地运行（推荐 debug 用）**

```bash
cd bot
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**方式二：Docker 运行**

```bash
docker compose up -d
docker compose logs -f
```

### 2.4 验证环境

启动后，用 Telegram 给你的测试 Bot 发送 `/start`：
- 如果 Bot 回复了主菜单 → 环境搭建成功
- 如果没有回复 → 检查 `data/logs/bot.log` 的错误日志

---

## 3. 项目结构速览

```
bot/
├── main.py                  # 入口，定时任务注册
├── config.py                # 环境变量加载
├── handlers/                # 用户交互（每个文件对应一个功能模块）
│   ├── start.py             # 注册流程（3轮AI对话）+ 主菜单
│   ├── sources.py           # 信息源管理（BUG-001 在这里）
│   ├── group.py             # 群聊功能（BUG-002 在这里）
│   ├── feedback.py          # 反馈收集
│   ├── settings.py          # 偏好设置
│   ├── payment.py           # 付费功能
│   └── admin.py             # 管理员控制台
├── services/                # 业务逻辑
│   ├── content_filter.py    # AI 筛选（BUG-004 去重在这里）
│   ├── report_generator.py  # 简报生成（BUG-008 视觉问题在这里）
│   ├── digest_processor.py  # 简报处理流程
│   ├── rss_fetcher.py       # RSS 抓取
│   └── profile_updater.py   # 用户画像更新
├── locales/ui_strings.py    # 多语言文字（BUG-005/006 在这里）
├── prompts/                 # AI Prompt 模板
├── utils/                   # 工具函数
└── tests/                   # 自动化测试
```

---

## 4. Debug 工作流程

### 4.1 认领 Bug

1. 打开 [BUG_TRACKER.md](./BUG_TRACKER.md)
2. 从 **P0** 开始，按顺序修复
3. 在 Bug 标题旁标注你的名字（如 `[WIP: 张三]`）

### 4.2 修复 & 验证

每个 Bug 都有**验收标准**（checklist），修复后逐一对照检查：

```bash
# 运行自动化测试
cd bot
python -m pytest tests/ -v

# 手动测试（管理员命令）
# 在 Telegram 中发送 /test 触发一次简报生成
```

### 4.3 提交代码

```bash
# 确保不提交 .env
git status   # 检查 .env 不在变更列表中

# 提交
git add -A
git commit -m "fix(BUG-001): 修复信息源添加失败的问题"
git push origin sprint2-dev
```

**提交消息格式**: `fix(BUG-XXX): 简短描述`

### 4.4 更新 Bug Tracker

在 `BUG_TRACKER.md` 底部的「修复日志」表格中添加记录：

```
| 2026-02-12 | BUG-001 | 张三 | 修复了 sources handler 中 RSS 验证逻辑的异常处理 |
```

并在对应 Bug 的验收标准中勾选已通过的项目。

---

## 5. 测试数据说明

项目附带脱敏测试数据，位于 `test_data/` 目录：

| 文件/目录 | 内容 | 说明 |
|-----------|------|------|
| `users.json` | 模拟用户数据 | Telegram ID 和姓名已替换为虚构数据 |
| `profiles/` | 用户画像 | 偏好内容保留，身份信息已脱敏 |
| `raw_content/` | RSS 抓取样本 | 真实新闻数据，可直接用于测试筛选和去重 |
| `prefetch_cache/` | 预抓取缓存 | 真实新闻数据缓存 |

**使用测试数据**:
```bash
# 将测试数据复制到运行目录
cp -r test_data/ bot/data/

# 或者直接修改 .env 中的数据目录
# DATA_DIR=../test_data
```

---

## 6. 常用调试命令

| 操作 | 命令/方法 |
|------|-----------|
| 查看实时日志 | `tail -f data/logs/bot.log` |
| 手动触发简报 | Telegram 发送 `/test`（需管理员权限） |
| 手动触发画像更新 | Telegram 发送 `/testprofile`（需管理员权限） |
| 开启调试日志 | 在 `main.py` 中设置 `logger.setLevel(logging.DEBUG)` |
| 运行全部测试 | `cd bot && python -m pytest tests/ -v` |
| 运行单个测试 | `python -m pytest tests/test_sprint1.py::TestDeduplication -v` |
| 暂停定时推送 | `.env` 中设置 `PAUSE_PUSH=true` |

---

## 7. 重要提醒

1. **不要提交 `.env` 文件** — 包含你的私人密钥
2. **不要修改 `.env.example`** — 除非你在添加新的配置项
3. **修改 `ui_strings.py` 时** — 确保 zh/en/ja/ko 四种语言都有对应翻译
4. **修改 prompt 模板时** — 保持 `{variable}` 占位符格式不变
5. **每次修复后** — 运行 `pytest` 确保没有破坏现有功能
6. **有疑问时** — 在 Bug Tracker 对应 bug 下添加评论，或联系项目负责人
