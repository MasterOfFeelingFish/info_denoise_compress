"""
Telegram Bot Sources Handler

Handles /sources command for users to view and manage information sources.
Allows viewing current sources and suggesting new ones.

Reference: python-telegram-bot v22.x (Exa verified 2025-01-12)
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from services.rss_fetcher import get_source_list
from utils.json_storage import get_user

logger = logging.getLogger(__name__)

# Conversation states
AWAITING_SOURCE_SUGGESTION, AWAITING_TWITTER_ADD, AWAITING_WEBSITE_ADD = range(3)


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sources command - show sources menu."""
    user = update.effective_user
    telegram_id = str(user.id)

    db_user = get_user(telegram_id)
    if not db_user:
        await update.message.reply_text(
            "你还没有注册。请使用 /start 开始。"
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("Twitter", callback_data="sources_twitter"),
            InlineKeyboardButton("网站", callback_data="sources_websites"),
        ],
        [InlineKeyboardButton("推荐信息源", callback_data="sources_suggest")],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Get source counts
    sources = get_source_list()
    twitter_count = len(sources.get("twitter", []))
    website_count = len(sources.get("websites", []))

    await update.message.reply_text(
        f"信息源管理\n"
        f"{'─' * 24}\n\n"
        f"当前监控：\n"
        f"  • Twitter 账号: {twitter_count}\n"
        f"  • 网站 RSS: {website_count}\n\n"
        "选择分类查看详情。",
        reply_markup=reply_markup
    )


async def view_twitter_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of monitored Twitter accounts."""
    query = update.callback_query
    await query.answer()

    sources = get_source_list()
    twitter_sources = sources.get("twitter", [])

    if twitter_sources:
        lines = [
            f"Twitter 信息源\n"
            f"{'─' * 24}\n"
        ]
        for i, source in enumerate(twitter_sources, 1):
            lines.append(f"  {i}. {source}")
        lines.append(f"\n共 {len(twitter_sources)} 个账号")
        text = "\n".join(lines)
    else:
        text = (
            f"Twitter 信息源\n"
            f"{'─' * 24}\n\n"
            "还没有配置 Twitter 信息源。\n\n"
            "点击「添加 Twitter」添加账号。"
        )

    keyboard = [
        [InlineKeyboardButton("添加 Twitter", callback_data="sources_add_twitter")],
        [InlineKeyboardButton("返回", callback_data="sources_back")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def view_website_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of monitored website RSS feeds."""
    query = update.callback_query
    await query.answer()

    sources = get_source_list()
    website_sources = sources.get("websites", [])

    if website_sources:
        lines = [
            f"网站信息源\n"
            f"{'─' * 24}\n"
        ]
        for i, source in enumerate(website_sources, 1):
            lines.append(f"  {i}. {source}")
        lines.append(f"\n共 {len(website_sources)} 个网站")
        text = "\n".join(lines)
    else:
        text = (
            f"网站信息源\n"
            f"{'─' * 24}\n\n"
            "还没有配置网站信息源。\n\n"
            "点击「添加网站」添加 RSS 源。"
        )

    keyboard = [
        [InlineKeyboardButton("添加网站", callback_data="sources_add_website")],
        [InlineKeyboardButton("返回", callback_data="sources_back")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def start_source_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the source suggestion conversation."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"推荐信息源\n"
        f"{'─' * 24}\n\n"
        "告诉我们你想监控的信息源。\n\n"
        "示例：\n"
        "  • @DefiLlama - DeFi 分析\n"
        "  • defillama.com - TVL 追踪\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_SOURCE_SUGGESTION


async def start_add_twitter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding a Twitter account."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"添加 Twitter 账号\n"
        f"{'─' * 24}\n\n"
        "请输入 Twitter 账号和 RSS 地址。\n\n"
        "格式：\n"
        "  账号名 | RSS 地址\n\n"
        "示例：\n"
        "  @VitalikButerin | https://rss.app/feeds/xxx\n"
        "  lookonchain | https://nitter.net/lookonchain/rss\n\n"
        "提示：可使用 rss.app 或 nitter 获取 RSS\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_TWITTER_ADD


async def handle_twitter_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Twitter account addition."""
    from services.rss_fetcher import add_custom_source

    user_input = update.message.text.strip()

    # Parse input: "handle | URL" format
    if "|" in user_input:
        parts = user_input.split("|", 1)
        handle = parts[0].strip()
        url = parts[1].strip()
    else:
        # No URL provided
        handle = user_input
        url = ""

    # Validate and add
    result = await add_custom_source("twitter", handle, url)

    keyboard = [
        [InlineKeyboardButton("添加更多", callback_data="sources_add_twitter")],
        [InlineKeyboardButton("返回", callback_data="sources_twitter")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if result["success"]:
        await update.message.reply_text(
            f"添加成功\n"
            f"{'─' * 24}\n\n"
            f"{result['message']}",
            reply_markup=reply_markup
        )
        logger.info(f"Added Twitter source: {handle} - {url}")
    else:
        await update.message.reply_text(
            f"添加失败\n"
            f"{'─' * 24}\n\n"
            f"{result['message']}\n\n"
            "请重试。",
            reply_markup=reply_markup
        )
        logger.warning(f"Failed to add Twitter source: {handle} - {result['message']}")

    return ConversationHandler.END


async def start_add_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding a website RSS feed."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"添加网站 RSS\n"
        f"{'─' * 24}\n\n"
        "方式一：只输入域名（自动探测）\n"
        "  theblock.co\n"
        "  decrypt.co\n\n"
        "方式二：指定名称和地址\n"
        "  The Block | https://theblock.co/rss.xml\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_WEBSITE_ADD


async def handle_website_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle website RSS feed addition."""
    from services.rss_fetcher import add_custom_source

    user_input = update.message.text.strip()

    # Parse input: "Name | URL" or just URL
    if "|" in user_input:
        parts = user_input.split("|", 1)
        name = parts[0].strip()
        url = parts[1].strip()
    else:
        # Try to extract name from URL
        url = user_input
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            name = parsed.netloc.replace("www.", "").split(".")[0].title()
        except Exception:
            name = "Custom Source"

    keyboard = [
        [InlineKeyboardButton("添加更多", callback_data="sources_add_website")],
        [InlineKeyboardButton("返回", callback_data="sources_websites")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Validate and add
    result = await add_custom_source("websites", name, url)

    if result["success"]:
        await update.message.reply_text(
            f"添加成功\n"
            f"{'─' * 24}\n\n"
            f"{result['message']}",
            reply_markup=reply_markup
        )
        logger.info(f"Added website source: {name} - {url}")
    else:
        await update.message.reply_text(
            f"添加失败\n"
            f"{'─' * 24}\n\n"
            f"{result['message']}\n\n"
            "请检查地址后重试。",
            reply_markup=reply_markup
        )
        logger.warning(f"Failed to add website source: {name} - {result['message']}")

    return ConversationHandler.END


async def handle_source_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user's source suggestion."""
    user = update.effective_user
    telegram_id = str(user.id)
    suggestion = update.message.text

    # In a real implementation, this would be saved to a review queue
    # For MVP, we just acknowledge and log

    logger.info(f"Source suggestion from {telegram_id}: {suggestion}")

    await update.message.reply_text(
        f"已收到推荐\n"
        f"{'─' * 24}\n\n"
        f"{suggestion}\n\n"
        "我们会审核这个信息源。\n"
        "如果通过审核，将添加到监控列表。\n\n"
        "使用 /sources 查看当前信息源。"
    )

    return ConversationHandler.END


async def sources_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to sources menu."""
    query = update.callback_query
    await query.answer()

    # Get source counts
    sources = get_source_list()
    twitter_count = len(sources.get("twitter", []))
    website_count = len(sources.get("websites", []))

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
        f"信息源管理\n"
        f"{'─' * 24}\n\n"
        f"当前监控：\n"
        f"  • Twitter 账号: {twitter_count}\n"
        f"  • 网站 RSS: {website_count}\n\n"
        "选择分类查看详情。",
        reply_markup=reply_markup
    )


async def cancel_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel sources conversation."""
    keyboard = [
        [
            InlineKeyboardButton("信息源", callback_data="sources_back"),
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "已取消。\n\n"
        "随时可以推荐信息源。",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


def get_sources_handler() -> ConversationHandler:
    """Create and return the sources conversation handler."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("sources", sources_command),
            CallbackQueryHandler(start_source_suggestion, pattern="^sources_suggest$"),
            CallbackQueryHandler(start_add_twitter, pattern="^sources_add_twitter$"),
            CallbackQueryHandler(start_add_website, pattern="^sources_add_website$"),
        ],
        states={
            AWAITING_SOURCE_SUGGESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_source_suggestion),
            ],
            AWAITING_TWITTER_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_twitter_add),
            ],
            AWAITING_WEBSITE_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_website_add),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_sources),
        ],
    )


def get_sources_callbacks():
    """Get standalone callback handlers for sources menu."""
    return [
        CallbackQueryHandler(view_twitter_sources, pattern="^sources_twitter$"),
        CallbackQueryHandler(view_website_sources, pattern="^sources_websites$"),
        CallbackQueryHandler(sources_back, pattern="^sources_back$"),
    ]
