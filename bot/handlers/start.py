"""
Telegram Bot Start Handler

Handles /start command and user registration flow.
Uses ConversationHandler for AI-driven preference collection.

Reference: python-telegram-bot v22.x official examples (Exa verified 2025-01-12)
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from services.gemini import call_gemini
from utils.prompt_loader import get_prompt
from utils.telegram_utils import safe_answer_callback_query
from utils.json_storage import (
    get_user,
    create_user,
    save_user_profile,
    get_user_profile,
)

logger = logging.getLogger(__name__)

# Conversation states
ONBOARDING_ROUND_1, ONBOARDING_ROUND_2, ONBOARDING_ROUND_3, CONFIRM_PROFILE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /start command.
    Check if user exists, show appropriate welcome message.
    """
    user = update.effective_user
    telegram_id = str(user.id)

    # Check if user already registered
    existing_user = get_user(telegram_id)

    if existing_user:
        # Existing user - show main menu with clear visual hierarchy
        keyboard = [
            [InlineKeyboardButton("查看今日简报", callback_data="view_digest")],
            [
                InlineKeyboardButton("偏好设置", callback_data="update_preferences"),
                InlineKeyboardButton("信息源", callback_data="manage_sources"),
            ],
            [
                InlineKeyboardButton("查看统计", callback_data="view_stats"),
                InlineKeyboardButton("对话设置", callback_data="chat_context_settings"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"欢迎回来，{user.first_name}\n"
            f"{'─' * 24}\n\n"
            "你的个性化 Web3 情报简报。\n"
            "每日精选，智能推送。\n\n"
            "请选择操作，或直接发消息与 AI 对话：",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    else:
        # New user - start onboarding with welcoming layout
        keyboard = [
            [InlineKeyboardButton("开始使用", callback_data="start_onboarding")],
            [InlineKeyboardButton("了解更多", callback_data="learn_more")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Web3 每日简报\n"
            f"{'─' * 24}\n\n"
            "你的个性化情报助手。\n\n"
            "我们做什么：\n"
            "  • 每日扫描 50+ 信息源\n"
            "  • 过滤噪音，精选内容\n"
            "  • 推送真正重要的信息\n\n"
            "每天节省约 2 小时阅读时间",
            reply_markup=reply_markup
        )
        return ConversationHandler.END


async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin the AI-driven preference collection (3 rounds)."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    # Initialize conversation history
    context.user_data["conversation_history"] = []
    context.user_data["current_round"] = 1

    # Show typing indicator while AI generates response
    await query.message.chat.send_action(ChatAction.TYPING)

    # Load prompt from file
    system_instruction = get_prompt("onboarding_round1.txt")

    try:
        ai_response = await call_gemini(
            prompt="Start the conversation by asking the user about their Web3 interests.",
            system_instruction=system_instruction,
            temperature=0.9
        )
    except Exception as e:
        logger.error(f"Onboarding round 1 failed: {e}")
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="start_onboarding")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await query.edit_message_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "[第 1 步 / 共 3 步] 设置你的偏好\n\n" + ai_response
    )

    return ONBOARDING_ROUND_1


async def handle_round_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user response in round 1, proceed to round 2."""
    user_message = update.message.text
    context.user_data["conversation_history"].append({
        "round": 1,
        "user_input": user_message
    })
    context.user_data["current_round"] = 2

    # Show typing indicator while AI generates response
    await update.message.chat.send_action(ChatAction.TYPING)

    # Load prompt from file with user input
    system_instruction = get_prompt("onboarding_round2.txt", user_input=user_message)

    try:
        ai_response = await call_gemini(
            prompt=f"The user said: '{user_message}'. Ask follow-up questions about content preferences.",
            system_instruction=system_instruction,
            temperature=0.9
        )
    except Exception as e:
        logger.error(f"Onboarding round 2 failed: {e}")
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="start_onboarding")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await update.message.reply_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "[第 2 步 / 共 3 步] 内容偏好\n\n" + ai_response
    )

    return ONBOARDING_ROUND_2


async def handle_round_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user response in round 2, proceed to round 3 (confirmation)."""
    user_message = update.message.text
    context.user_data["conversation_history"].append({
        "round": 2,
        "user_input": user_message
    })
    context.user_data["current_round"] = 3

    # Show typing indicator while AI generates response
    await update.message.chat.send_action(ChatAction.TYPING)

    # Build conversation context
    history = context.user_data["conversation_history"]
    round_1 = history[0]["user_input"]
    round_2 = user_message

    # Load prompt from file
    system_instruction = get_prompt("onboarding_round3.txt", round_1=round_1, round_2=round_2)

    try:
        ai_response = await call_gemini(
            prompt=f"Summarize preferences: Round 1: '{round_1}', Round 2: '{round_2}'",
            system_instruction=system_instruction,
            temperature=0.7
        )
    except Exception as e:
        logger.error(f"Onboarding round 3 failed: {e}")
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="retry_round_2")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await update.message.reply_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    # Store the generated profile summary
    context.user_data["profile_summary"] = ai_response

    # Add confirmation buttons
    keyboard = [
        [InlineKeyboardButton("确认", callback_data="confirm_profile")],
        [InlineKeyboardButton("重新开始", callback_data="start_onboarding")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "[第 3 步 / 共 3 步] 请确认你的偏好\n\n" + ai_response,
        reply_markup=reply_markup
    )

    return CONFIRM_PROFILE


async def retry_round_2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Retry round 2 with the same round 1 data."""
    query = update.callback_query
    await query.answer("正在重试...")

    # Get round 1 data
    round_1 = context.user_data.get("onboarding_round_1")
    if not round_1:
        await query.edit_message_text(
            "无法重试，请重新开始注册。",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("重新开始", callback_data="start_onboarding")
            ]])
        )
        return ConversationHandler.END

    # Load prompt from file
    system_instruction = get_prompt("onboarding_round2.txt", user_input=round_1)

    try:
        ai_response = await call_gemini(
            prompt=f"The user said: '{round_1}'. Ask follow-up questions about content preferences.",
            system_instruction=system_instruction,
            temperature=0.9
        )

        await query.edit_message_text(
            "[第 2 步 / 共 3 步] 内容偏好\n\n" + ai_response
        )

        return ONBOARDING_ROUND_2

    except Exception as e:
        logger.error(f"Retry round 2 failed: {e}")
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="retry_round_2")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await query.edit_message_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END


async def confirm_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save confirmed user profile and complete registration."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)

    # Create user record
    create_user(
        telegram_id=telegram_id,
        username=user.username,
        first_name=user.first_name
    )

    # Save profile (natural language description)
    profile_summary = context.user_data.get("profile_summary", "")
    history = context.user_data.get("conversation_history", [])

    # Load prompt from file
    system_instruction = get_prompt("onboarding_confirm.txt")

    try:
        full_profile = await call_gemini(
            prompt=f"Create profile from: {history}. Summary: {profile_summary}",
            system_instruction=system_instruction,
            temperature=0.5
        )
    except Exception as e:
        logger.error(f"Failed to generate profile: {e}")
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="confirm_profile")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await query.edit_message_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    save_user_profile(telegram_id, full_profile)

    # Clear conversation data
    context.user_data.clear()

    # Show success message
    keyboard = [
        [InlineKeyboardButton("查看示例简报", callback_data="view_sample")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "偏好保存成功！\n\n"
        "你将每日收到个性化 Web3 简报。\n"
        "我们会根据你的反馈不断优化推送内容。\n\n"
        "使用 /settings 随时更新偏好设置。",
        reply_markup=reply_markup
    )

    return ConversationHandler.END


async def learn_more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show more information about the service."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [InlineKeyboardButton("开始使用", callback_data="start_onboarding")],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "工作原理\n"
        f"{'─' * 24}\n\n"
        "第 1 步  告诉我们你的兴趣\n"
        "        3 轮 AI 对话快速完成\n\n"
        "第 2 步  我们 24/7 监控信息源\n"
        "        50+ Twitter 账号和网站\n\n"
        "第 3 步  AI 智能过滤噪音\n"
        "        根据你的画像个性化筛选\n\n"
        "第 4 步  每日推送简报\n"
        "        北京时间 9:00\n\n"
        "第 5 步  持续优化\n"
        "        根据你的反馈不断学习",
        reply_markup=reply_markup
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("开始设置", callback_data="start_onboarding")],
        [InlineKeyboardButton("了解更多", callback_data="learn_more")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "设置已取消。\n\n"
        "随时可以重新开始。",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main start menu."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)
    existing_user = get_user(telegram_id)

    if existing_user:
        keyboard = [
            [InlineKeyboardButton("查看今日简报", callback_data="view_digest")],
            [
                InlineKeyboardButton("偏好设置", callback_data="update_preferences"),
                InlineKeyboardButton("信息源", callback_data="manage_sources"),
            ],
            [InlineKeyboardButton("查看统计", callback_data="view_stats")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"欢迎回来，{user.first_name}\n"
            f"{'─' * 24}\n\n"
            "你的个性化 Web3 情报简报。\n"
            "每日精选，智能推送。\n\n"
            "请选择操作，或直接发消息与 AI 对话：",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("开始使用", callback_data="start_onboarding")],
            [InlineKeyboardButton("了解更多", callback_data="learn_more")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Web3 每日简报\n"
            f"{'─' * 24}\n\n"
            "你的个性化情报助手。\n\n"
            "我们做什么：\n"
            "  • 每日扫描 50+ 信息源\n"
            "  • 过滤噪音，精选内容\n"
            "  • 推送真正重要的信息\n\n"
            "每天节省约 2 小时阅读时间",
            reply_markup=reply_markup
        )


async def view_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's digest or a message if not available."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    from utils.json_storage import get_user_daily_stats, get_user_profile
    from services.report_generator import prepare_digest_messages, detect_user_language, get_ai_summary
    from handlers.feedback import create_item_feedback_keyboard, get_item_feedback_status
    from config import PUSH_HOUR, PUSH_MINUTE
    from datetime import datetime

    telegram_id = str(query.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")

    # Get today's stats
    stats = get_user_daily_stats(telegram_id, today)

    if not stats or not stats.get("filtered_items"):
        # No digest available yet
        keyboard = [
            [InlineKeyboardButton("返回", callback_data="back_to_start")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "今日简报\n"
            f"{'─' * 24}\n\n"
            f"推送时间：北京时间 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}\n\n"
            "你的简报将自动推送。\n"
            "请在推送时间后查看。\n\n"
            "提示：使用 /settings 自定义偏好设置。",
            reply_markup=reply_markup
        )
        return

    # Get filtered items and generate messages
    filtered_items = stats["filtered_items"]
    profile = get_user_profile(telegram_id) or ""
    user_lang = detect_user_language(profile)

    # Generate AI summary if not already in stats
    ai_summary = stats.get("ai_summary", "")
    if not ai_summary and filtered_items:
        from services.content_filter import get_ai_summary
        ai_summary = await get_ai_summary(filtered_items, profile)

    # Prepare messages
    header, item_messages = prepare_digest_messages(
        filtered_items=filtered_items,
        ai_summary=ai_summary,
        sources_count=stats.get("sources_monitored", 0),
        raw_count=stats.get("raw_items_scanned", 0),
        lang=user_lang
    )

    # Send header
    await query.edit_message_text(
        f"[回顾] {header}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    # Send each item with feedback buttons
    for item_msg, item_id in item_messages:
        # Check feedback status
        feedback_status = get_item_feedback_status(item_id)

        # Section headers don't get feedback buttons
        if item_id.startswith("section_"):
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=item_msg,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            # Create feedback keyboard based on status
            if feedback_status:
                # Already has feedback, show status
                status_text = "👍 已点赞" if feedback_status == "like" else "👎 已标记"
                item_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(status_text, callback_data=f"noop")]
                ])
            else:
                # No feedback yet, show buttons
                item_keyboard = create_item_feedback_keyboard(item_id)

            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=item_msg,
                reply_markup=item_keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )


async def update_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Redirect to settings for preference update."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [
            InlineKeyboardButton("查看", callback_data="settings_view"),
            InlineKeyboardButton("更新", callback_data="settings_update"),
        ],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "偏好设置\n"
        f"{'─' * 24}\n\n"
        "管理你的 Web3 每日简报偏好。",
        reply_markup=reply_markup
    )


async def manage_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Redirect to sources management."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [
            InlineKeyboardButton("Twitter", callback_data="sources_twitter"),
            InlineKeyboardButton("网站", callback_data="sources_websites"),
        ],
        [InlineKeyboardButton("推荐信息源", callback_data="sources_suggest")],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "信息源管理\n"
        f"{'─' * 24}\n\n"
        "我们监控多个信息源为你生成简报。\n"
        "查看当前信息源或推荐新的。",
        reply_markup=reply_markup
    )


async def view_sample(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a sample digest preview."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")

    sample_text = f"""示例预览
{date_str}
{'━' * 28}

以下是你每日简报的样式预览。

今日必看

1. 重大协议升级公告
   关键进展的简要摘要...
   [The Block]

2. 链上巨鲸活动监测
   DeFi 领域的重大资金流动...
   [lookonchain]

{'─' * 28}

DeFi (3)
  • DeFi 相关新闻 [来源]
  • 另一条相关更新 [来源]

{'─' * 28}

统计
  信息源       50+
  扫描条数     200+
  精选条数     15
  节省时间     约 2 小时

{'━' * 28}

你的真实简报将于明天 9:00 推送。"""

    await query.edit_message_text(
        sample_text,
        reply_markup=reply_markup
    )


async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics via callback."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    from services.profile_updater import analyze_feedback_trends

    def _translate_trend(trend: str) -> str:
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
        keyboard = [[InlineKeyboardButton("返回", callback_data="back_to_start")]]
        await query.edit_message_text(
            "你还没有注册。请使用 /start 开始。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

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
            InlineKeyboardButton("返回", callback_data="back_to_start"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(stats_text, reply_markup=reply_markup)


def get_start_callbacks():
    """Get standalone callback handlers for start menu."""
    return [
        CallbackQueryHandler(back_to_start, pattern="^back_to_start$"),
        CallbackQueryHandler(view_digest, pattern="^view_digest$"),
        CallbackQueryHandler(update_preferences, pattern="^update_preferences$"),
        CallbackQueryHandler(manage_sources, pattern="^manage_sources$"),
        CallbackQueryHandler(view_sample, pattern="^view_sample$"),
        CallbackQueryHandler(view_stats, pattern="^view_stats$"),
        CallbackQueryHandler(learn_more, pattern="^learn_more$"),
    ]


def get_start_handler() -> ConversationHandler:
    """Create and return the conversation handler for start/onboarding."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start_onboarding, pattern="^start_onboarding$"),
            CallbackQueryHandler(retry_round_2_callback, pattern="^retry_round_2$"),
        ],
        states={
            ONBOARDING_ROUND_1: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_round_1),
            ],
            ONBOARDING_ROUND_2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_round_2),
            ],
            CONFIRM_PROFILE: [
                CallbackQueryHandler(confirm_profile, pattern="^confirm_profile$"),
                CallbackQueryHandler(start_onboarding, pattern="^start_onboarding$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(start_onboarding, pattern="^start_onboarding$"),
            CallbackQueryHandler(learn_more, pattern="^learn_more$"),
        ],
    )
