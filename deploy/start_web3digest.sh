#!/bin/bash
# Web3 Daily Digest 启动脚本 (Linux/macOS)
# 使用方法: ./deploy/start_web3digest.sh [--test] [--background]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend/wiseflow"
WEB3DIGEST_DIR="$BACKEND_DIR/core/custom_processes/web3digest"

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Web3 Daily Digest - 启动脚本${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# 解析参数
TEST_MODE=false
BACKGROUND=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --test|-t)
            TEST_MODE=true
            shift
            ;;
        --background|-b)
            BACKGROUND=true
            shift
            ;;
        *)
            echo -e "${RED}[ERROR] 未知参数: $1${NC}"
            echo "使用方法: $0 [--test] [--background]"
            exit 1
            ;;
    esac
done

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python3 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] Python: $(which python3)${NC}"

# 检查 .env 文件
ENV_FILE="$WEB3DIGEST_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}[ERROR] .env 文件不存在: $ENV_FILE${NC}"
    echo -e "${YELLOW}请复制 env_sample 并配置必要的环境变量${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] 配置文件: $ENV_FILE${NC}"

# 加载环境变量
set -a
source "$ENV_FILE"
set +a

# 检查关键环境变量
REQUIRED_VARS=("TELEGRAM_BOT_TOKEN" "LLM_API_KEY")
for var in "${REQUIRED_VARS[@]}"; do
    value="${!var}"
    if [ -z "$value" ]; then
        echo -e "${RED}[ERROR] 缺少必要的环境变量: $var${NC}"
        exit 1
    fi
    masked="${value:0:10}..."
    echo -e "${GREEN}[OK] $var = $masked${NC}"
done

echo ""

# 切换到工作目录
cd "$BACKEND_DIR"
echo -e "${CYAN}[INFO] 工作目录: $BACKEND_DIR${NC}"

if [ "$TEST_MODE" = true ]; then
    # 测试模式
    echo ""
    echo -e "${YELLOW}========== 运行测试 ==========${NC}"
    python3 core/custom_processes/web3digest/quick_test_flow.py
else
    # 正常启动
    echo ""
    echo -e "${YELLOW}========== 启动服务 ==========${NC}"
    
    if [ "$BACKGROUND" = true ]; then
        # 后台运行
        LOG_DIR="$WEB3DIGEST_DIR/data/web3digest/logs"
        LOG_FILE="$LOG_DIR/service.log"
        PID_FILE="$LOG_DIR/service.pid"
        
        mkdir -p "$LOG_DIR"
        
        echo -e "${CYAN}[INFO] 后台启动，日志文件: $LOG_FILE${NC}"
        
        nohup python3 core/custom_processes/web3digest/main.py > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        
        sleep 3
        if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
            echo -e "${GREEN}[OK] 服务已在后台启动 (PID: $(cat $PID_FILE))${NC}"
            echo -e "${CYAN}[TIP] 查看日志: tail -f $LOG_FILE${NC}"
            echo -e "${CYAN}[TIP] 停止服务: kill \$(cat $PID_FILE)${NC}"
        else
            echo -e "${RED}[ERROR] 服务启动失败，请查看日志${NC}"
            exit 1
        fi
    else
        # 前台运行
        echo -e "${CYAN}[INFO] 按 Ctrl+C 停止服务${NC}"
        echo ""
        python3 core/custom_processes/web3digest/main.py
    fi
fi
