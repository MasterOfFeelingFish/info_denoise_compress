#!/usr/bin/env python3
"""
Web3 Daily Digest - Simplified Bot Runner
简化版 Bot 启动器，跳过 WiseFlow 依赖
"""

import asyncio
import sys
from pathlib import Path

# 设置路径
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 加载环境变量
from dotenv import load_dotenv
_env_file = Path(__file__).parent / ".env"
load_dotenv(_env_file)

import os
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("web3digest")

# Telegram Bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode


class SimplifiedBot:
    """简化版 Bot"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = None
        self.users = {}  # 简单的用户存储
    
    async def start(self):
        """启动 Bot"""
        self.application = Application.builder().token(self.token).build()
        
        # 注册命令
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("test", self.cmd_test))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        logger.info("🚀 Telegram Bot 启动中...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        
        logger.info("✅ Bot 已启动! 请在 Telegram 中发送 /start")
        
        # 保持运行
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """停止 Bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"用户 {user.full_name} ({user_id}) 发送 /start")
        
        # 记录用户
        self.users[user_id] = {
            "name": user.full_name,
            "joined": datetime.now().isoformat()
        }
        
        welcome_text = f"""
🎉 **欢迎使用 Web3 Daily Digest!**

你好 {user.full_name}！

我是你的 Web3 信息助手，可以帮你：
• 📰 聚合 Web3 领域重要信息
• 🎯 根据你的偏好个性化筛选
• ⏰ 每日定时推送简报

**开始使用：**
1. 告诉我你关注的领域（DeFi、NFT、Layer2 等）
2. 设置你的偏好
3. 开始接收每日简报！

使用 /help 查看更多命令
        """
        
        keyboard = [
            [InlineKeyboardButton("🎯 设置我的偏好", callback_data="setup_preferences")],
            [InlineKeyboardButton("📡 查看信息源", callback_data="view_sources")],
            [InlineKeyboardButton("🧪 测试简报", callback_data="test_digest")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        help_text = """
🤖 **Web3 Daily Digest 使用指南**

**命令列表：**
/start - 开始使用
/help - 查看帮助
/test - 测试简报功能

**功能特点：**
• AI 个性化筛选
• 多源信息聚合
• 每日定时推送
• 反馈学习优化

**状态：** ✅ Bot 运行正常
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /test 命令"""
        await update.message.reply_text("🔄 正在测试...")
        
        # 模拟简报
        test_digest = """
📰 **Web3 每日简报** (测试版)
📅 {date}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 **今日必看 (Top 3)**

1️⃣ **以太坊 Pectra 升级测试网进展**
   > 以太坊核心开发者确认 Pectra 升级将于 Q1 上线
   📍 来源: @ethereum

2️⃣ **Arbitrum 生态 TVL 突破 200 亿美元**
   > Layer2 赛道持续增长，Arbitrum 领跑
   📍 来源: @l2beat

3️⃣ **某巨鲸地址转出 5000 ETH**
   > 链上监控显示大额异动
   📍 来源: @lookonchain

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **今日为您做了什么**

• 监控信息源: 3 个
• 扫描原始信息: 50 条
• 为您精选: 3 条
• 今日为您节省: 约 0.5 小时

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 这份简报对您有帮助吗？
        """.format(date=datetime.now().strftime("%Y年%m月%d日"))
        
        keyboard = [
            [
                InlineKeyboardButton("👍 有用", callback_data="feedback_positive"),
                InlineKeyboardButton("👎 不太行", callback_data="feedback_negative")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            test_digest,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮回调"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "setup_preferences":
            await query.edit_message_text(
                "🎯 **设置偏好**\n\n"
                "请告诉我你关注的领域：\n"
                "例如：DeFi、NFT、Layer2、以太坊、Solana\n\n"
                "（此功能完整版开发中...）",
                parse_mode=ParseMode.MARKDOWN
            )
        elif data == "view_sources":
            await query.edit_message_text(
                "📡 **当前信息源**\n\n"
                "✅ The Block (RSS)\n"
                "✅ CoinDesk (RSS)\n"
                "✅ Foresight News (RSS)\n\n"
                "（更多信息源配置中...）",
                parse_mode=ParseMode.MARKDOWN
            )
        elif data == "test_digest":
            await self.cmd_test(update, context)
        elif data.startswith("feedback_"):
            rating = "positive" if "positive" in data else "negative"
            await query.edit_message_text(
                f"✅ 感谢您的反馈！\n\n"
                f"您的评价: {'👍 有用' if rating == 'positive' else '👎 需要改进'}\n\n"
                f"我们会根据您的反馈持续优化简报质量。"
            )


async def main():
    """主函数"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN 未配置")
        return
    
    logger.info("=" * 50)
    logger.info("Web3 Daily Digest - 简化版启动")
    logger.info("=" * 50)
    
    bot = SimplifiedBot(token=token)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("收到停止信号...")
    finally:
        await bot.stop()
        logger.info("Bot 已停止")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
