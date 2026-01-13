"""
Web3 Daily Digest - Telegram Bot Entry Point

Main application file that initializes the bot, sets up handlers,
and configures scheduled tasks for daily digest delivery.

Reference: python-telegram-bot v22.x with built-in JobQueue
"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import sys
from datetime import time, datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, PUSH_HOUR, PUSH_MINUTE
from handlers.start import get_start_handler, get_start_callbacks
from handlers.feedback import get_feedback_handlers
from handlers.settings import get_settings_handler, get_settings_callbacks
from handlers.sources import get_sources_handler, get_sources_callbacks

# Configure logging with rotation
log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

# Rotating file handler: 5MB max size, keep 5 backup files
file_handler = RotatingFileHandler(
    "bot.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to generate and send daily digest to all users.
    Runs at configured time (default: 9:00 AM Beijing Time).
    """
    from services.rss_fetcher import fetch_all_sources, get_source_list
    from services.content_filter import filter_content_for_user
    from services.report_generator import (
        generate_daily_report,
        generate_empty_report,
        split_report_for_telegram,
    )
    from services.profile_updater import update_all_user_profiles
    from utils.json_storage import get_users, save_raw_content, save_daily_stats
    from handlers.feedback import create_feedback_keyboard

    logger.info("Starting daily digest generation...")

    try:
        # 1. Fetch all RSS content
        raw_content = await fetch_all_sources(hours_back=24)
        sources = get_source_list()
        sources_count = sum(len(s) for s in sources.values())

        logger.info(f"Fetched {len(raw_content)} items from {sources_count} sources")

        # Save raw content for debugging
        today = datetime.now().strftime("%Y-%m-%d")
        save_raw_content(today, raw_content)

        # 2. Get all users
        users = get_users()
        if not users:
            logger.warning("No users registered, skipping digest")
            return

        user_stats = {}

        # 3. Process each user
        for user in users:
            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue

            try:
                # Filter content for user
                filtered_items = await filter_content_for_user(
                    telegram_id=telegram_id,
                    raw_content=raw_content,
                    max_items=20
                )

                # Generate report
                if filtered_items:
                    report = await generate_daily_report(
                        telegram_id=telegram_id,
                        filtered_items=filtered_items,
                        raw_count=len(raw_content),
                        sources_count=sources_count
                    )
                else:
                    report = generate_empty_report()

                # Split report if too long
                messages = split_report_for_telegram(report)

                # Send to user
                chat_id = int(telegram_id)
                for i, msg in enumerate(messages):
                    # Add feedback buttons to last message
                    if i == len(messages) - 1:
                        report_id = f"{today}_{telegram_id}"
                        reply_markup = create_feedback_keyboard(report_id)
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            disable_web_page_preview=True
                        )

                user_stats[telegram_id] = {
                    "items_sent": len(filtered_items),
                    "status": "success"
                }
                logger.info(f"Sent digest to {telegram_id}: {len(filtered_items)} items")

            except Exception as e:
                logger.error(f"Failed to send digest to {telegram_id}: {e}")
                user_stats[telegram_id] = {
                    "items_sent": 0,
                    "status": f"error: {str(e)}"
                }

        # 4. Save daily stats
        save_daily_stats(
            date=today,
            sources_monitored=sources_count,
            raw_items_scanned=len(raw_content),
            user_stats=user_stats
        )

        # 5. Update user profiles based on feedback (run after digests)
        await update_all_user_profiles()

        logger.info(f"Daily digest complete: {len(users)} users processed")

    except Exception as e:
        logger.error(f"Daily digest job failed: {e}", exc_info=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    keyboard = [
        [
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
            InlineKeyboardButton("设置", callback_data="update_preferences"),
        ],
        [InlineKeyboardButton("信息源", callback_data="manage_sources")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_text = f"""帮助
{'─' * 24}

命令：
  /start     主菜单
  /settings  偏好设置
  /sources   信息源管理
  /stats     查看统计
  /help      帮助信息

{'─' * 24}

推送时间：北京时间 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}"""

    await update.message.reply_text(help_text, reply_markup=reply_markup)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - show user statistics."""
    from services.profile_updater import analyze_feedback_trends
    from utils.json_storage import get_user

    def _translate_trend(trend: str) -> str:
        """Translate trend text to Chinese."""
        translations = {
            "improving": "改善中",
            "declining": "下降中",
            "stable": "稳定",
            "no_data": "暂无数据",
        }
        return translations.get(trend, trend.replace('_', ' '))

    user = update.effective_user
    telegram_id = str(user.id)

    db_user = get_user(telegram_id)
    if not db_user:
        await update.message.reply_text(
            "你还没有注册。请使用 /start 开始。"
        )
        return

    # Get feedback trends
    trends = await analyze_feedback_trends(telegram_id, days=30)

    stats_text = f"""你的统计
{'─' * 24}

注册时间：{db_user.get('created', '未知')[:10]}

最近 30 天
  反馈次数         {trends['total_feedbacks']}
  正面评价         {trends['positive_count']}
  负面评价         {trends['negative_count']}
  满意度           {trends['positive_rate']:.0%}
  趋势             {_translate_trend(trends['trend'])}
{f"  主要问题         {', '.join(trends['common_issues'][:2])}" if trends['common_issues'] else ""}

{'─' * 24}

使用 /settings 调整偏好设置。"""

    keyboard = [
        [
            InlineKeyboardButton("更新偏好", callback_data="settings_update"),
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(stats_text, reply_markup=reply_markup)


async def post_init(application: Application) -> None:
    """Post-initialization callback to set up scheduled jobs."""
    # Get timezone for Beijing
    beijing_tz = ZoneInfo("Asia/Shanghai")

    # Schedule daily digest
    push_time = time(hour=PUSH_HOUR, minute=PUSH_MINUTE, tzinfo=beijing_tz)

    application.job_queue.run_daily(
        callback=daily_digest_job,
        time=push_time,
        name="daily_digest"
    )

    logger.info(f"Scheduled daily digest at {PUSH_HOUR:02d}:{PUSH_MINUTE:02d} Beijing Time")

    # Optional: Run profile updates at midnight
    midnight = time(hour=0, minute=0, tzinfo=beijing_tz)
    application.job_queue.run_daily(
        callback=profile_update_job,
        time=midnight,
        name="profile_update"
    )


async def profile_update_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job to update user profiles based on feedback."""
    from services.profile_updater import update_all_user_profiles

    logger.info("Running scheduled profile update...")
    try:
        await update_all_user_profiles()
        logger.info("Profile update complete")
    except Exception as e:
        logger.error(f"Profile update failed: {e}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)


async def unknown_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages that don't match any other handler."""
    keyboard = [
        [
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
            InlineKeyboardButton("帮助", callback_data="show_help"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "我没有理解你的意思。\n\n"
        "请使用 /start、/help 或 /settings。",
        reply_markup=reply_markup
    )


async def show_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle show_help callback from unknown message handler."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
            InlineKeyboardButton("设置", callback_data="update_preferences"),
        ],
        [InlineKeyboardButton("信息源", callback_data="manage_sources")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_text = f"""帮助
{'─' * 24}

命令：
  /start     主菜单
  /settings  偏好设置
  /sources   信息源管理
  /stats     查看统计
  /help      帮助信息

{'─' * 24}

推送时间：北京时间 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}"""

    await query.edit_message_text(help_text, reply_markup=reply_markup)


def main() -> None:
    """Main function to run the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Please check your .env file.")
        sys.exit(1)

    # Build application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Add handlers
    # Start/onboarding conversation handler
    application.add_handler(get_start_handler())

    # Start menu callbacks
    for callback in get_start_callbacks():
        application.add_handler(callback)

    # Settings handler
    application.add_handler(get_settings_handler())
    for callback in get_settings_callbacks():
        application.add_handler(callback)

    # Sources handler
    application.add_handler(get_sources_handler())
    for callback in get_sources_callbacks():
        application.add_handler(callback)

    # Feedback handlers
    feedback_conv, item_handler = get_feedback_handlers()
    application.add_handler(feedback_conv)
    application.add_handler(item_handler)

    # Command handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))

    # Callback for help from unknown message
    application.add_handler(CallbackQueryHandler(show_help_callback, pattern="^show_help$"))

    # Fallback handler for unrecognized messages (must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message_handler))

    # Error handler
    application.add_error_handler(error_handler)

    # Start the bot
    logger.info("Starting Web3 Daily Digest Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
