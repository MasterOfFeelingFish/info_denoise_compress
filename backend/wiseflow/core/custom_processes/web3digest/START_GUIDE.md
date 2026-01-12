# 🚀 启动指南

## 📋 启动前检查清单

在启动服务前，请确认以下配置已完成：

- [ ] **Telegram Bot Token** 已配置在 `.env` 文件中
- [ ] **Kimi API Key** 已配置在 `.env` 文件中
- [ ] **Python 3.11+** 已安装
- [ ] **依赖包** 已安装
- [ ] **WiseFlow 框架** 已正确安装

---

## 🔧 步骤 1: 检查配置

### 1.1 确认 `.env` 文件存在

在 WiseFlow 项目根目录（`backend/wiseflow/`）检查 `.env` 文件：

```bash
cd backend/wiseflow
ls -la .env  # Linux/Mac
dir .env    # Windows
```

### 1.2 验证配置内容

`.env` 文件应包含以下必需配置：

```bash
# 必需配置
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
LLM_API_BASE=https://api.moonshot.cn/v1
LLM_API_KEY=sk-Nu4nsNqZtsD1cmm1hJG2wrgc0eG1cQXe77bxZ226uolR2Idu
PRIMARY_MODEL=kimi-k2-thinking-preview

# 鉴权配置（可选）
ADMIN_TELEGRAM_IDS=your_telegram_id  # 管理员 Telegram ID（逗号分隔）
ENABLE_WHITELIST=false  # 是否启用白名单模式
```

**注意**: 请将 `your_telegram_bot_token` 替换为实际的 Telegram Bot Token。

---

## 📦 步骤 2: 安装依赖

### 2.1 安装项目依赖

```bash
# 进入 WiseFlow 项目根目录
cd backend/wiseflow

# 安装 web3digest 依赖
pip install -r core/custom_processes/web3digest/requirements.txt
```

### 2.2 安装 WiseFlow 依赖（如果尚未安装）

```bash
# 安装 WiseFlow 核心依赖
pip install -r requirements.txt
```

### 2.3 验证依赖安装

```bash
# 检查关键包是否已安装
python -c "import telegram; import openai; import apscheduler; print('✅ 依赖安装成功')"
```

---

## ✅ 步骤 3: 测试配置（可选但推荐）

### 3.1 测试抓取功能

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/test_crawler.py
```

如果测试通过，会看到：
- ✅ RSS.app 客户端测试成功
- ✅ WiseFlow 客户端测试成功
- ✅ 信息抓取测试成功

### 3.2 测试反馈功能（可选）

```bash
python core/custom_processes/web3digest/test_feedback_loop.py
```

---

## 🚀 步骤 4: 启动服务

### 4.1 启动主服务

```bash
# 确保在 WiseFlow 项目根目录
cd backend/wiseflow

# 启动服务
python core/custom_processes/web3digest/main.py
```

### 4.2 预期输出

服务启动成功后，您应该看到类似以下输出：

```
2025-01-XX XX:XX:XX | INFO     | __main__ | 确保目录存在: ./data/web3digest/users
2025-01-XX XX:XX:XX | INFO     | __main__ | 确保目录存在: ./data/web3digest/profiles
...
2025-01-XX XX:XX:XX | INFO     | scheduler | 调度器已启动
2025-01-XX XX:XX:XX | INFO     | scheduler | 抓取调度器已启动，每小时执行一次抓取任务
2025-01-XX XX:XX:XX | INFO     | telegram_bot | Telegram Bot 启动中...
2025-01-XX XX:XX:XX | INFO     | telegram_bot | ✅ Telegram Bot 已启动
2025-01-XX XX:XX:XX | INFO     | __main__ | 🚀 Web3 Daily Digest 服务启动中...
```

### 4.3 后台运行（可选）

**Linux/Mac**:
```bash
# 使用 nohup 后台运行
nohup python core/custom_processes/web3digest/main.py > web3digest.log 2>&1 &

# 或使用 screen
screen -S web3digest
python core/custom_processes/web3digest/main.py
# 按 Ctrl+A 然后 D 退出 screen
```

**Windows**:
```powershell
# 使用 PowerShell 后台运行
Start-Process python -ArgumentList "core/custom_processes/web3digest/main.py" -WindowStyle Hidden
```

---

## 📱 步骤 5: 验证服务运行

### 5.1 测试 Telegram Bot

1. 在 Telegram 中搜索您的 Bot（使用 Bot 用户名）
2. 点击 "Start" 或发送 `/start` 命令
3. Bot 应该回复欢迎消息并开始偏好收集对话

### 5.2 测试完整流程

在 Telegram Bot 中发送：
```
/test
```

这会触发完整的测试流程：
1. 抓取信息
2. AI 筛选
3. 生成简报
4. 推送简报

### 5.3 检查日志

查看日志文件确认服务运行状态：

```bash
# 日志文件位置
cat ./data/web3digest/logs/web3digest.log  # Linux/Mac
type .\data\web3digest\logs\web3digest.log  # Windows
```

---

## 🔍 常见问题排查

### 问题 1: 启动失败 - 找不到模块

**错误**: `ModuleNotFoundError: No module named 'core'`

**解决**:
```bash
# 确保在 WiseFlow 项目根目录运行
cd backend/wiseflow
python core/custom_processes/web3digest/main.py
```

### 问题 2: Telegram Bot Token 无效

**错误**: `Unauthorized` 或 `Invalid token`

**解决**:
1. 检查 `.env` 文件中的 `TELEGRAM_BOT_TOKEN` 是否正确
2. 在 @BotFather 中重新生成 Token
3. 确保 Token 格式正确（`数字:字母数字组合`）

### 问题 3: Kimi API Key 无效

**错误**: `401 Unauthorized` 或 LLM 调用失败

**解决**:
1. 检查 `.env` 文件中的 `LLM_API_KEY` 是否正确
2. 访问 https://platform.moonshot.cn/ 验证账户状态
3. 确认账户余额充足

### 问题 4: 端口被占用

**错误**: `Address already in use`

**解决**:
- Telegram Bot 使用长轮询，不占用本地端口
- 如果仍有问题，检查是否有其他 Python 进程在运行

### 问题 5: 依赖包版本冲突

**错误**: `ImportError` 或版本不兼容

**解决**:
```bash
# 使用虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 重新安装依赖
pip install -r core/custom_processes/web3digest/requirements.txt
```

---

## 📊 服务运行状态检查

### 检查服务是否运行

**Linux/Mac**:
```bash
ps aux | grep "main.py"
```

**Windows**:
```powershell
Get-Process python | Where-Object {$_.Path -like "*web3digest*"}
```

### 查看实时日志

```bash
# Linux/Mac
tail -f ./data/web3digest/logs/web3digest.log

# Windows PowerShell
Get-Content .\data\web3digest\logs\web3digest.log -Wait -Tail 50
```

---

## 🛑 停止服务

### 正常停止

在运行服务的终端中按 `Ctrl+C`

### 强制停止

**Linux/Mac**:
```bash
# 查找进程
ps aux | grep "main.py"

# 停止进程（替换 PID）
kill <PID>
```

**Windows**:
```powershell
# 查找进程
Get-Process python | Where-Object {$_.Path -like "*web3digest*"}

# 停止进程（替换 Id）
Stop-Process -Id <Id>
```

---

## 🔄 重启服务

```bash
# 停止服务（Ctrl+C）
# 然后重新启动
python core/custom_processes/web3digest/main.py
```

---

## 📝 下一步

服务启动成功后：

1. **测试 Bot**: 在 Telegram 中与 Bot 交互，完成偏好设置
2. **等待抓取**: 系统每小时自动抓取信息
3. **接收简报**: 每日固定时间（默认 09:00）接收个性化简报
4. **提供反馈**: 使用 👍/👎 按钮提供反馈，帮助系统学习

---

## 📚 相关文档

- [快速开始指南](./QUICK_START.md)
- [第三方服务配置](./THIRD_PARTY_CONFIG.md)
- [Kimi API 配置](./KIMI_API_CONFIG.md)
- [集成指南](./INTEGRATION_GUIDE.md)

---

## 💡 提示

- **首次启动**: 建议先运行测试脚本验证配置
- **生产环境**: 建议使用进程管理工具（如 systemd、supervisor）
- **监控**: 定期查看日志文件，确保服务正常运行
- **备份**: 定期备份 `data/web3digest` 目录中的数据
