"""
Web3 Daily Digest - Telegram Bot Entry Point

Main application file that initializes the bot, sets up handlers,
and configures scheduled tasks for daily digest delivery.

Reference: python-telegram-bot v22.x with built-in JobQueue
"""
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import signal
import atexit
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

from config import TELEGRAM_BOT_TOKEN, PUSH_HOUR, PUSH_MINUTE, DATA_DIR, LOG_ROTATE_DAYS, LOG_BACKUP_COUNT, MAX_DIGEST_ITEMS
from utils.telegram_utils import safe_answer_callback_query
from handlers.start import get_start_handler, get_start_callbacks
from handlers.feedback import get_feedback_handlers
from handlers.settings import get_settings_handler, get_settings_callbacks
from handlers.sources import get_sources_handler, get_sources_callbacks
from handlers.chat import get_chat_handler, get_clear_command_handler, get_clear_callback_handler, get_chat_to_start_handler, get_retry_chat_handler, get_context_settings_handler, get_set_context_days_handler


# ============ Logging Configuration ============

# Create logs directory
LOGS_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


class HeartbeatFilter(logging.Filter):
    """Filter out noisy heartbeat/polling log messages."""

    # Patterns to filter out
    NOISE_PATTERNS = [
        "HTTP Request: POST https://api.telegram.org/bot",
        "getUpdates",
        "Got response",
        "Entering:",
        "Exiting:",
        "No updates to fetch",
        "Network loop",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.NOISE_PATTERNS:
            if pattern in msg:
                return False
        return True


log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Console handler (with heartbeat filter)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.addFilter(HeartbeatFilter())

# Timed rotating file handler: rotate every N days, keep 30 backups
# 按天轮转日志，LOG_ROTATE_DAYS 控制几天轮转一次，LOG_BACKUP_COUNT 控制保留数量
file_handler = TimedRotatingFileHandler(
    os.path.join(LOGS_DIR, "bot.log"),
    when="D",                        # 按天
    interval=LOG_ROTATE_DAYS,        # 每 N 天轮转
    backupCount=LOG_BACKUP_COUNT,    # 保留 N 个备份（默认30天）
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)
file_handler.addFilter(HeartbeatFilter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)

# Reduce noise from third-party libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to generate and send daily digest to all users.
    Runs at configured time (default: 9:00 AM Beijing Time).
    Each user has their own sources, so we fetch per-user.
    """
    from services.rss_fetcher import fetch_user_sources, get_user_source_list
    from services.content_filter import filter_content_for_user, get_ai_summary
    from services.report_generator import (
        generate_empty_report,
        detect_user_language,
        prepare_digest_messages,
    )
    from utils.json_storage import (
        get_users,
        get_user_profile,
        save_user_raw_content,
        save_user_daily_stats,
    )
    from handlers.feedback import create_feedback_keyboard, create_item_feedback_keyboard

    logger.info("Starting daily digest generation...")

    today = datetime.now().strftime("%Y-%m-%d")

    try:
        # Get all users
        users = get_users()
        if not users:
            logger.warning("No users registered, skipping digest")
            return

        # Process each user with their own sources
        for user in users:
            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue

            try:
                # 1. Fetch content from this user's sources
                user_sources = get_user_source_list(telegram_id)
                sources_count = sum(len(s) for s in user_sources.values())

                raw_content = await fetch_user_sources(telegram_id, hours_back=24)

                logger.info(f"User {telegram_id}: Fetched {len(raw_content)} items from {sources_count} sources")

                # Save raw content for this user
                save_user_raw_content(telegram_id, today, raw_content)

                # Get user profile for language detection
                profile = get_user_profile(telegram_id) or ""
                user_lang = detect_user_language(profile)

                # 2. Filter content for user
                filtered_items = await filter_content_for_user(
                    telegram_id=telegram_id,
                    raw_content=raw_content,
                    max_items=MAX_DIGEST_ITEMS
                )

                chat_id = int(telegram_id)
                report_id = f"{today}_{telegram_id}"

                if filtered_items:
                    # Generate AI summary
                    ai_summary = await get_ai_summary(filtered_items, profile)

                    # Prepare messages: header + individual items
                    header, item_messages = prepare_digest_messages(
                        filtered_items=filtered_items,
                        ai_summary=ai_summary,
                        sources_count=sources_count,
                        raw_count=len(raw_content),
                        lang=user_lang
                    )

                    # Send header message
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=header,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )

                    # Send each item with feedback buttons
                    for item_msg, item_id in item_messages:
                        # Section headers don't get feedback buttons
                        if item_id.startswith("section_"):
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=item_msg,
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                        else:
                            item_keyboard = create_item_feedback_keyboard(item_id)
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=item_msg,
                                reply_markup=item_keyboard,
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )

                    # Send final feedback message
                    final_keyboard = create_feedback_keyboard(report_id)
                    locale_prompt = "这份简报有帮助吗？" if user_lang == "zh" else "Was this helpful?"
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"{'─' * 28}\n{locale_prompt}",
                        reply_markup=final_keyboard
                    )

                else:
                    # No content - send empty report
                    report = generate_empty_report(lang=user_lang)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=report,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )

                # 3. Save per-user daily stats
                save_user_daily_stats(
                    telegram_id=telegram_id,
                    date=today,
                    sources_monitored=sources_count,
                    raw_items_scanned=len(raw_content),
                    items_sent=len(filtered_items),
                    status="success",
                    filtered_items=filtered_items
                )

                logger.info(f"Sent digest to {telegram_id}: {len(filtered_items)} items")

            except Exception as e:
                logger.error(f"Failed to send digest to {telegram_id}: {e}")
                # Save error status
                save_user_daily_stats(
                    telegram_id=telegram_id,
                    date=today,
                    sources_monitored=0,
                    raw_items_scanned=0,
                    items_sent=0,
                    status=f"error: {str(e)[:50]}"
                )

        logger.info(f"Daily digest complete: {len(users)} users processed")

    except Exception as e:
        logger.error(f"Daily digest job failed: {e}", exc_info=True)


async def test_fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden /test command - manually trigger data fetch and digest."""
    user = update.effective_user
    telegram_id = str(user.id)

    await update.message.reply_text("正在抓取数据...")

    try:
        # Run the daily digest job manually
        await daily_digest_job(context)
        await update.message.reply_text("抓取完成。")
    except Exception as e:
        logger.error(f"Test fetch failed: {e}")
        await update.message.reply_text(f"抓取失败: {str(e)[:100]}")


async def test_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden /testprofile command - manually trigger profile update from feedback."""
    from services.profile_updater import update_all_user_profiles

    await update.message.reply_text("正在更新用户画像...")

    try:
        await update_all_user_profiles()
        await update.message.reply_text("画像更新完成。")
    except Exception as e:
        logger.error(f"Test profile update failed: {e}")
        await update.message.reply_text(f"更新失败: {str(e)[:100]}")


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
  /clear     清空今日对话
  /help      帮助信息

{'─' * 24}

功能说明：

AI 对话
  直接发送任何消息即可与 AI 对话。
  AI 能够联网搜索获取实时信息，
  并读取你最近 3 天的推送内容。

每日简报
  每天 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}（北京时间）自动推送。
  内容分为「今日必看」「推荐」「其他」三个板块。
  AI 根据你的偏好智能筛选 15-30 条精选内容。

偏好设置 (/settings)
  查看或更新你的 Web3 兴趣偏好。
  AI 会根据偏好个性化筛选每日简报。

信息源管理 (/sources)
  添加/删除你关注的 Twitter 账号或网站 RSS。
  支持自定义个人信息源。

统计 (/stats)
  查看你的注册时间、反馈历史、满意度趋势。

对话设置（主菜单按钮）
  设置 AI 对话的上下文天数：
  • 只用当天 - 每天从头开始
  • 包含昨天 - AI 能记住昨天的对话
  • 包含前天 - AI 能记住近 3 天对话

反馈
  每条推送消息都有反馈按钮，
  你的反馈会帮助 AI 更好地理解你的偏好。

{'─' * 24}

有问题？直接发消息问我！"""

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

    # Run data cleanup at 00:30 daily
    # 每日 00:30 清理过期数据文件
    cleanup_time = time(hour=0, minute=30, tzinfo=beijing_tz)
    application.job_queue.run_daily(
        callback=data_cleanup_job,
        time=cleanup_time,
        name="data_cleanup"
    )

    logger.info("Scheduled data cleanup at 00:30 Beijing Time")


async def profile_update_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job to update user profiles based on feedback."""
    from services.profile_updater import update_all_user_profiles

    logger.info("Running scheduled profile update...")
    try:
        await update_all_user_profiles()
        logger.info("Profile update complete")
    except Exception as e:
        logger.error(f"Profile update failed: {e}")


async def data_cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to clean up old data files.

    每日定时清理过期数据：
    - raw_content: 保留 RAW_CONTENT_RETENTION_DAYS 天
    - daily_stats: 保留 DAILY_STATS_RETENTION_DAYS 天
    - feedback: 保留 FEEDBACK_RETENTION_DAYS 天
    """
    from utils.json_storage import cleanup_old_data

    logger.info("Running scheduled data cleanup...")
    try:
        results = cleanup_old_data()
        total = sum(results.values())
        if total > 0:
            logger.info(
                f"Data cleanup complete: deleted {results['raw_content']} raw_content, "
                f"{results['daily_stats']} daily_stats, {results['feedback']} feedback files"
            )
        else:
            logger.info("Data cleanup complete: no expired files to delete")
    except Exception as e:
        logger.error(f"Data cleanup failed: {e}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle noop callback for already-feedback items."""
    query = update.callback_query
    await safe_answer_callback_query(query, "已经反馈过了", show_alert=False)


async def show_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle show_help callback from unknown message handler."""
    query = update.callback_query
    await safe_answer_callback_query(query)

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
  /clear     清空今日对话
  /help      帮助信息

{'─' * 24}

功能说明：

AI 对话
  直接发送任何消息即可与 AI 对话。
  AI 能够联网搜索获取实时信息，
  并读取你最近 3 天的推送内容。

每日简报
  每天 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}（北京时间）自动推送。
  内容分为「今日必看」「推荐」「其他」三个板块。
  AI 根据你的偏好智能筛选 15-30 条精选内容。

偏好设置 (/settings)
  查看或更新你的 Web3 兴趣偏好。
  AI 会根据偏好个性化筛选每日简报。

信息源管理 (/sources)
  添加/删除你关注的 Twitter 账号或网站 RSS。
  支持自定义个人信息源。

统计 (/stats)
  查看你的注册时间、反馈历史、满意度趋势。

对话设置（主菜单按钮）
  设置 AI 对话的上下文天数：
  • 只用当天 - 每天从头开始
  • 包含昨天 - AI 能记住昨天的对话
  • 包含前天 - AI 能记住近 3 天对话

反馈
  每条推送消息都有反馈按钮，
  你的反馈会帮助 AI 更好地理解你的偏好。

{'─' * 24}

有问题？直接发消息问我！"""

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
    application.add_handler(CommandHandler("test", test_fetch_command))
    application.add_handler(CommandHandler("testprofile", test_profile_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(get_clear_command_handler())

    # Callback for help from unknown message
    application.add_handler(CallbackQueryHandler(show_help_callback, pattern="^show_help$"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
    application.add_handler(get_clear_callback_handler())
    application.add_handler(get_chat_to_start_handler())
    application.add_handler(get_retry_chat_handler())
    application.add_handler(get_context_settings_handler())
    application.add_handler(get_set_context_days_handler())

    # AI Chat handler - handles all text messages (must be last)
    application.add_handler(get_chat_handler())

    # Error handler
    application.add_error_handler(error_handler)

    # Register shutdown handler to save shutdown log
    # 服务关闭时保存 shutdown 日志
    def on_shutdown():
        shutdown_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        shutdown_log_path = os.path.join(LOGS_DIR, f"bot.log.shutdown.{shutdown_time}")
        try:
            # Copy current log to shutdown file
            current_log_path = os.path.join(LOGS_DIR, "bot.log")
            if os.path.exists(current_log_path):
                import shutil
                shutil.copy2(current_log_path, shutdown_log_path)
                logger.info(f"Shutdown log saved to {shutdown_log_path}")
        except Exception as e:
            logger.error(f"Failed to save shutdown log: {e}")
        logger.info("Bot shutting down...")

    atexit.register(on_shutdown)

    # Start the bot
    logger.info("Starting Web3 Daily Digest Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
