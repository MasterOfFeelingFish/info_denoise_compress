#!/bin/bash
#
# 安装 Git Hooks
# 在项目根目录执行: bash bot/scripts/git-hooks/install.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOKS_DIR="$PROJECT_DIR/.git/hooks"

echo "安装 Git Hooks..."
echo "  源目录: $SCRIPT_DIR"
echo "  目标目录: $HOOKS_DIR"
echo ""

# 安装 post-merge hook
if [ -f "$SCRIPT_DIR/post-merge" ]; then
    cp "$SCRIPT_DIR/post-merge" "$HOOKS_DIR/post-merge"
    chmod +x "$HOOKS_DIR/post-merge"
    echo "✅ post-merge hook 已安装"
else
    echo "❌ post-merge 文件不存在"
    exit 1
fi

echo ""
echo "安装完成！"
echo "现在每次 git pull 时，如果 CHANGELOG.md 有变更，会自动发送通知。"
