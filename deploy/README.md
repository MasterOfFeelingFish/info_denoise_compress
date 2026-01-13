# Web3 Daily Digest - 部署指南

## 📁 部署脚本

| 脚本 | 平台 | 说明 |
|------|------|------|
| `start_web3digest.ps1` | Windows | 启动脚本 |
| `stop_web3digest.ps1` | Windows | 停止脚本 |
| `start_web3digest.sh` | Linux/macOS | 启动脚本 |
| `stop_web3digest.sh` | Linux/macOS | 停止脚本 |

## 🚀 快速启动

### Windows

```powershell
# 前台运行（可看到日志）
.\deploy\start_web3digest.ps1

# 后台运行
.\deploy\start_web3digest.ps1 -Background

# 运行测试
.\deploy\start_web3digest.ps1 -Test

# 停止服务
.\deploy\stop_web3digest.ps1
```

### Linux/macOS

```bash
# 添加执行权限（首次）
chmod +x deploy/*.sh

# 前台运行
./deploy/start_web3digest.sh

# 后台运行
./deploy/start_web3digest.sh --background

# 运行测试
./deploy/start_web3digest.sh --test

# 停止服务
./deploy/stop_web3digest.sh
```

## ⚙️ 配置要求

### 1. 环境变量

在 `backend/wiseflow/core/custom_processes/web3digest/.env` 中配置：

```env
# 必需
TELEGRAM_BOT_TOKEN=your_bot_token
LLM_API_KEY=your_kimi_api_key

# 可选
LLM_API_BASE=https://api.moonshot.cn/v1
PRIMARY_MODEL=moonshot-v1-32k
DAILY_PUSH_TIME=09:00
```

### 2. 依赖安装

```bash
cd backend/wiseflow
pip install -r requirements.txt
```

### 3. 目录结构

```
backend/wiseflow/
├── core/custom_processes/web3digest/
│   ├── .env              # 配置文件
│   ├── main.py           # 主程序入口
│   ├── data/web3digest/  # 数据存储目录
│   │   ├── logs/         # 日志
│   │   ├── users/        # 用户数据
│   │   ├── profiles/     # 用户画像
│   │   ├── feedback/     # 反馈数据
│   │   └── raw_info/     # 抓取的原始信息
│   └── ...
└── ...
```

## 📊 服务验证

### 测试 LLM 连接
```powershell
.\deploy\start_web3digest.ps1 -Test
```

### 测试 Telegram Bot
1. 启动服务
2. 在 Telegram 中搜索并打开 Bot
3. 发送 `/start` 命令
4. 应收到欢迎消息

### 测试完整流程
1. 发送 `/test` 命令
2. Bot 将触发抓取 → 筛选 → 生成简报
3. 检查收到的简报内容

## 🔍 日志查看

### Windows
```powershell
# 实时查看日志
Get-Content "backend\wiseflow\core\custom_processes\web3digest\data\web3digest\logs\service.log" -Tail 50 -Wait
```

### Linux/macOS
```bash
# 实时查看日志
tail -f backend/wiseflow/core/custom_processes/web3digest/data/web3digest/logs/service.log
```

## ❓ 常见问题

### 1. 启动失败：缺少环境变量
确保 `.env` 文件存在且包含必要配置。

### 2. LLM 调用失败
- 检查 `LLM_API_KEY` 是否正确
- 检查 `PRIMARY_MODEL` 是否为有效模型名（如 `moonshot-v1-32k`）

### 3. Telegram Bot 无响应
- 确保 `TELEGRAM_BOT_TOKEN` 正确
- 检查是否有其他实例在运行

### 4. RSS 抓取失败
- 检查网络连接
- 验证 RSS URL 是否可访问
