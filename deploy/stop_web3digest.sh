#!/bin/bash
# Web3 Daily Digest 停止脚本 (Linux/macOS)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WEB3DIGEST_DIR="$PROJECT_ROOT/backend/wiseflow/core/custom_processes/web3digest"
PID_FILE="$WEB3DIGEST_DIR/data/web3digest/logs/service.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping Web3 Daily Digest (PID: $PID)..."
        kill $PID
        rm -f "$PID_FILE"
        echo "Service stopped."
    else
        echo "Service not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
else
    echo "No PID file found. Service may not be running."
    # 尝试通过进程名停止
    pkill -f "web3digest/main.py" 2>/dev/null && echo "Killed by process name" || echo "No process found"
fi
