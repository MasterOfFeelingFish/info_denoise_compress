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
from utils.telegram_utils import safe_answer_callback_query, send_message_safe
from utils.json_storage import (
    get_user,
    create_user,
    save_user_profile,
    get_user_profile,
    track_event,
)
from utils.auth import whitelist_required

logger = logging.getLogger(__name__)

# Conversation states
ONBOARDING_ROUND_1, ONBOARDING_ROUND_2, ONBOARDING_ROUND_3, CONFIRM_PROFILE, SOURCE_CHOICE, ADDING_SOURCES = range(6)


@whitelist_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /start command.
    Check if user exists, show appropriate welcome message.
    """
    user = update.effective_user
    telegram_id = str(user.id)

    # 埋点：会话开始
    track_event(telegram_id, "session_start", {"command": "start"})

    # Check if user already registered
    existing_user = get_user(telegram_id)

    if existing_user:
        # Existing user - show main menu with clear visual hierarchy
        from handlers.admin import is_admin
        
        keyboard = [
            [InlineKeyboardButton("查看今日简报", callback_data="view_digest")],
            [
                InlineKeyboardButton("偏好设置", callback_data="update_preferences"),
                InlineKeyboardButton("信息源", callback_data="manage_sources"),
            ],
            [
                InlineKeyboardButton("查看统计", callback_data="view_stats"),
            ],
        ]
        
        # Add admin panel button for admins only
        if is_admin(user.id):
            keyboard.append([InlineKeyboardButton("🛡️ 管理员控制台", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"欢迎回来，{user.first_name}\n"
            f"{'─' * 24}\n\n"
            "你的个性化 Web3 情报简报。\n"
            "每日精选，智能推送。\n\n"
            "请选择操作：",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    else:
        # New user - directly start onboarding (no button click required)
        # Clear only onboarding-related state from previous incomplete registration
        # (Don't use .clear() to avoid affecting other potential features)
        context.user_data["conversation_history"] = []
        context.user_data["current_round"] = 1

        # Show welcome message + typing indicator
        await update.message.reply_text(
            "Web3 每日简报\n"
            f"{'─' * 24}\n\n"
            "你的个性化情报助手。\n\n"
            "我们做什么：\n"
            "  • 每日扫描 50+ 信息源\n"
            "  • 过滤噪音，精选内容\n"
            "  • 推送真正重要的信息\n\n"
            "让我们先了解你的偏好，开始 3 步设置...\n\n"
            "⏳ <i>正在生成问题，请稍候...</i>",
            parse_mode="HTML"
        )

        await update.message.chat.send_action(ChatAction.TYPING)

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
            ]
            await update.message.reply_text(
                "AI 服务暂时不可用，请稍后重试。",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "[第 1 步 / 共 3 步] 设置你的偏好\n\n" + ai_response
        )

        return ONBOARDING_ROUND_1


@whitelist_required
async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin the AI-driven preference collection (3 rounds)."""
    query = update.callback_query

    # Anti-debounce: Prevent duplicate clicks
    if context.user_data.get("processing"):
        await safe_answer_callback_query(query, "正在生成问题，请稍候...", show_alert=True)
        return ONBOARDING_ROUND_1

    context.user_data["processing"] = True
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
        context.user_data.pop("processing", None)  # Release lock on error
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="start_onboarding")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await query.edit_message_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    context.user_data.pop("processing", None)  # Release lock on success
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

    # Show progress message
    progress_msg = await update.message.reply_text(
        "⏳ <i>正在生成你的个性化画像，请稍候...</i>",
        parse_mode="HTML"
    )

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

    # Anti-debounce: Prevent duplicate clicks
    if context.user_data.get("processing"):
        await safe_answer_callback_query(query, "正在处理中，请稍候...", show_alert=True)
        return CONFIRM_PROFILE

    context.user_data["processing"] = True
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)

    # Show progress message
    await query.edit_message_text(
        "⏳ <i>正在保存你的偏好设置，请稍候...</i>",
        parse_mode="HTML"
    )

    # Create user record (save user_id to avoid file lock race condition)
    created_user = create_user(
        telegram_id=telegram_id,
        username=user.username,
        first_name=user.first_name
    )
    user_id = created_user['id']

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
        context.user_data.pop("processing", None)  # Release lock on error
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="confirm_profile")],
            [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
        ]
        await query.edit_message_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    # Pass user_id to avoid re-querying users.json (Windows file lock race condition)
    save_user_profile(telegram_id, full_profile, user_id=user_id)

    # Clear conversation data
    context.user_data.clear()

    # Show source choice: custom sources / default sources / skip
    from config import DEFAULT_USER_SOURCES

    default_sources_preview = ", ".join(list(DEFAULT_USER_SOURCES.get("websites", {}).keys())[:2])

    keyboard = [
        [InlineKeyboardButton("🎯 配置我自己的信息源", callback_data="source_custom")],
        [InlineKeyboardButton("📡 使用默认推荐源", callback_data="source_default")],
        [InlineKeyboardButton("⏰ 稍后，明天 09:00 再看", callback_data="source_skip")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "✅ 偏好保存成功！\n\n"
        "你的个性化 Web3 简报已配置完成。\n\n"
        f"📰 接下来，选择你的信息源：\n\n"
        f"🔹 默认源：{default_sources_preview}...\n\n"
        "你希望：",
        reply_markup=reply_markup
    )

    return SOURCE_CHOICE


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
        from handlers.admin import is_admin
        
        keyboard = [
            [InlineKeyboardButton("查看今日简报", callback_data="view_digest")],
            [
                InlineKeyboardButton("偏好设置", callback_data="update_preferences"),
                InlineKeyboardButton("信息源", callback_data="manage_sources"),
            ],
            [InlineKeyboardButton("查看统计", callback_data="view_stats")],
        ]
        
        # Add admin panel button for admins only
        if is_admin(user.id):
            keyboard.append([InlineKeyboardButton("🛡️ 管理员控制台", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"欢迎回来，{user.first_name}\n"
            f"{'─' * 24}\n\n"
            "你的个性化 Web3 情报简报。\n"
            "每日精选，智能推送。\n\n"
            "请选择操作：",
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
    
    # === Final output translation (all at once) ===
    from services.content_filter import translate_text, translate_content, _extract_user_language
    target_language = _extract_user_language(profile)
    if target_language != "English":
        # Translate both items and summary before output
        filtered_items = await translate_content(filtered_items, target_language)
        ai_summary = await translate_text(ai_summary, target_language)

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
            await send_message_safe(
                context,
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

            await send_message_safe(
                context,
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


async def trigger_first_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger first digest immediately for new users."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)

    # Show progress message
    await query.edit_message_text(
        "正在生成你的首份简报...\n\n"
        "🔍 抓取最新内容\n"
        "🤖 AI 智能筛选\n"
        "📊 生成个性化简报\n\n"
        "预计需要 10-20 秒，请稍候..."
    )

    try:
        from datetime import datetime
        from services.digest_processor import process_single_user

        today = datetime.now().strftime("%Y-%m-%d")
        user = get_user(telegram_id)

        if not user:
            await query.edit_message_text(
                "用户信息未找到，请使用 /start 重新开始。"
            )
            return

        # Trigger digest generation
        result = await process_single_user(context, user, today)

        if result.get("status") == "success":
            items_count = result.get("items_sent", 0)
            # Success - digest messages already sent by process_single_user
            # Just send a final summary message
            keyboard = [[InlineKeyboardButton("返回主菜单", callback_data="back_to_start")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await send_message_safe(
                context,
                chat_id=int(telegram_id),
                text=f"✅ 首份简报推送完成！\n\n"
                     f"已为你精选 {items_count} 条内容。\n\n"
                     f"💡 提示：\n"
                     f"  • 每条内容都有反馈按钮（👍/👎）\n"
                     f"  • 你的反馈会让简报更懂你\n"
                     f"  • 下次自动推送：明天 09:00\n\n"
                     f"使用 /help 查看更多功能。",
                reply_markup=reply_markup
            )
        else:
            # Error occurred
            error_msg = result.get("error", "未知错误")
            keyboard = [
                [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
                [InlineKeyboardButton("查看帮助", callback_data="show_help")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"推送失败\n\n"
                f"原因：{error_msg[:100]}\n\n"
                f"你可以稍后使用 /test 命令重试，\n"
                f"或等待明天 09:00 的自动推送。",
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"First digest trigger failed for {telegram_id}: {e}")
        keyboard = [[InlineKeyboardButton("返回主菜单", callback_data="back_to_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "推送失败，请稍后重试。\n\n"
            "你可以使用 /test 命令手动触发推送。",
            reply_markup=reply_markup
        )


async def skip_first_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip first digest and show main menu."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user

    keyboard = [
        [
            InlineKeyboardButton("偏好设置", callback_data="update_preferences"),
            InlineKeyboardButton("信息源", callback_data="manage_sources"),
        ],
        [InlineKeyboardButton("查看统计", callback_data="view_stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"好的，{user.first_name}！\n\n"
        f"你的首份简报将在明天 09:00 推送。\n\n"
        f"在此之前，你可以：\n"
        f"  • 调整偏好设置\n"
        f"  • 添加更多信息源\n\n"
        f"使用 /help 查看所有功能。",
        reply_markup=reply_markup
    )

    return ConversationHandler.END


async def add_custom_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enter quick add sources mode."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    # Initialize adding counters
    context.user_data["added_sources_count"] = 0
    context.user_data["added_sources_list"] = []

    keyboard = [
        [InlineKeyboardButton("✅ 完成添加，开始推送", callback_data="finish_sources")],
        [InlineKeyboardButton("📡 使用默认源", callback_data="finish_sources_default")],
        [InlineKeyboardButton("⏰ 稍后再说", callback_data="source_skip")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🎯 添加你关注的信息源\n\n"
        "请发送以下任一格式：\n\n"
        "📱 Twitter: @VitalikButerin\n"
        "📰 网站: https://example.com/rss\n\n"
        "💡 可以连续发送多个，完成后点击按钮：",
        reply_markup=reply_markup
    )

    return ADDING_SOURCES


async def handle_add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user adding a source."""
    from services.rss_fetcher import validate_twitter_handle, validate_url
    from utils.json_storage import get_user_sources, save_user_sources
    from urllib.parse import urlparse

    text = update.message.text.strip()
    telegram_id = str(update.effective_user.id)

    # Get current sources
    user_sources = get_user_sources(telegram_id)

    success = False
    added_name = ""

    # Try Twitter
    if text.startswith("@") or not text.startswith("http"):
        validation = await validate_twitter_handle(text)
        if validation["valid"]:
            handle = validation["handle"]
            if handle not in user_sources.get("twitter", {}):
                user_sources.setdefault("twitter", {})[handle] = ""
                added_name = handle
                success = True

    # Try website RSS
    else:
        validation = await validate_url(text)
        if validation["valid"]:
            url = validation["url"]
            # Extract domain name as source name
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            name = domain.split(".")[0].title()  # e.g., "theblock.co" -> "Theblock"

            if name not in user_sources.get("websites", {}):
                user_sources.setdefault("websites", {})[name] = url
                added_name = f"{name} ({domain})"
                success = True

    if success:
        # Save
        save_user_sources(telegram_id, user_sources)

        # Update counter
        context.user_data["added_sources_count"] = context.user_data.get("added_sources_count", 0) + 1
        context.user_data.setdefault("added_sources_list", []).append(added_name)

        count = context.user_data["added_sources_count"]
        sources_list = context.user_data["added_sources_list"]

        keyboard = [
            [InlineKeyboardButton("✅ 完成添加，开始推送", callback_data="finish_sources")],
            [InlineKeyboardButton("📡 补充默认源一起推送", callback_data="finish_sources_default")],
            [InlineKeyboardButton("⏰ 稍后再说", callback_data="source_skip")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        sources_text = "\n".join([f"  • {s}" for s in sources_list])

        await update.message.reply_text(
            f"✅ 已添加：{added_name}\n\n"
            f"📊 当前已添加 {count} 个信息源：\n{sources_text}\n\n"
            f"继续发送更多，或选择：",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"❌ 格式错误：{text[:20]}\n\n"
            f"请使用以下格式：\n"
            f"• Twitter: @用户名\n"
            f"• 网站: https://...\n\n"
            f"📊 当前已添加 {context.user_data.get('added_sources_count', 0)} 个信息源"
        )

    return ADDING_SOURCES


async def finish_adding_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish adding sources and trigger digest."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    count = context.user_data.get("added_sources_count", 0)

    # Boundary: 0 sources
    if count == 0:
        keyboard = [
            [InlineKeyboardButton("确认使用默认源", callback_data="finish_sources_default")],
            [InlineKeyboardButton("返回继续添加", callback_data="source_custom")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "你还没有添加任何信息源。\n\n"
            "📡 将使用默认推荐源为你推送。",
            reply_markup=reply_markup
        )
        return SOURCE_CHOICE

    # Clear temp data
    context.user_data.pop("added_sources_count", None)
    context.user_data.pop("added_sources_list", None)

    # Trigger digest (using user's custom sources)
    await trigger_first_digest_internal(update, context, use_default=False)

    return ConversationHandler.END


async def finish_with_default(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish with user sources + default sources."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    from utils.json_storage import get_user_sources, save_user_sources
    from config import DEFAULT_USER_SOURCES
    import asyncio

    # Merge user sources + default sources
    user_sources = get_user_sources(telegram_id)
    for category, sources in DEFAULT_USER_SOURCES.items():
        user_sources.setdefault(category, {}).update(sources)

    save_user_sources(telegram_id, user_sources)

    # Windows file lock mitigation: Brief delay to ensure file lock is released
    await asyncio.sleep(0.1)

    # Clear temp data
    context.user_data.pop("added_sources_count", None)
    context.user_data.pop("added_sources_list", None)

    # Trigger digest
    await trigger_first_digest_internal(update, context, use_default=False)

    return ConversationHandler.END


async def use_default_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Use default sources and trigger digest."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    # Trigger digest (using default sources)
    await trigger_first_digest_internal(update, context, use_default=True)

    return ConversationHandler.END


async def trigger_first_digest_internal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    use_default: bool = True
) -> None:
    """Internal function to trigger first digest."""
    query = update.callback_query
    telegram_id = str(query.from_user.id)

    await query.edit_message_text(
        "正在为你准备首份简报...\n\n"
        f"{'📡 使用默认信息源' if use_default else '🎯 使用你配置的信息源'}\n"
        "🤖 AI 智能筛选中\n\n"
        "预计 10-20 秒，请稍候..."
    )

    try:
        from datetime import datetime
        from services.digest_processor import process_single_user

        today = datetime.now().strftime("%Y-%m-%d")
        user = get_user(telegram_id)

        if not user:
            await query.edit_message_text(
                "用户信息未找到，请使用 /start 重新开始。"
            )
            return

        # Trigger digest generation (no global_raw_content, will fetch individually)
        result = await process_single_user(context, user, today)

        if result.get("status") == "success":
            items_count = result.get("items_sent", 0)

            if items_count == 0:
                # No content - guide user to add sources
                keyboard = [[InlineKeyboardButton("添加信息源", callback_data="manage_sources")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await send_message_safe(
                    context,
                    chat_id=int(telegram_id),
                    text="暂时没有新内容。\n\n"
                         "💡 建议：\n"
                         "  • 添加更多信息源（/sources）\n"
                         "  • 下次推送：明天 09:00",
                    reply_markup=reply_markup
                )
            else:
                # Success - digest messages already sent
                keyboard = [[InlineKeyboardButton("返回主菜单", callback_data="back_to_start")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await send_message_safe(
                    context,
                    chat_id=int(telegram_id),
                    text=f"✅ 首份简报推送完成！\n\n"
                         f"已为你精选 {items_count} 条内容。\n\n"
                         f"💡 提示：\n"
                         f"  • 每条内容都有反馈按钮（👍/👎）\n"
                         f"  • 你的反馈会让简报更懂你\n"
                         f"  • 下次自动推送：明天 09:00\n\n"
                         f"使用 /help 查看更多功能。",
                    reply_markup=reply_markup
                )
        else:
            # Error occurred
            error_msg = result.get("error", "未知错误")
            keyboard = [
                [InlineKeyboardButton("返回主菜单", callback_data="back_to_start")],
                [InlineKeyboardButton("查看帮助", callback_data="show_help")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"推送失败\n\n"
                f"原因：{error_msg[:100]}\n\n"
                f"你可以稍后使用 /test 命令重试，\n"
                f"或等待明天 09:00 的自动推送。",
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"First digest trigger failed for {telegram_id}: {e}")
        keyboard = [[InlineKeyboardButton("返回主菜单", callback_data="back_to_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "推送失败，请稍后重试。\n\n"
            "你可以使用 /test 命令手动触发推送。",
            reply_markup=reply_markup
        )


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
            SOURCE_CHOICE: [
                CallbackQueryHandler(add_custom_sources, pattern="^source_custom$"),
                CallbackQueryHandler(use_default_sources, pattern="^source_default$"),
                CallbackQueryHandler(skip_first_digest, pattern="^source_skip$"),
            ],
            ADDING_SOURCES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_source),
                CallbackQueryHandler(finish_adding_sources, pattern="^finish_sources$"),
                CallbackQueryHandler(finish_with_default, pattern="^finish_sources_default$"),
                CallbackQueryHandler(skip_first_digest, pattern="^source_skip$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(start_onboarding, pattern="^start_onboarding$"),
            CallbackQueryHandler(learn_more, pattern="^learn_more$"),
        ],
    )
