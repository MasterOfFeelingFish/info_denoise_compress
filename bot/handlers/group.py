"""
Group Chat Handler (T7)

Handles group chat functionality:
- /setup command for group configuration
- Group profile (interests, push time, language)
- Bot removal detection
- Group digest generation

Controlled by FEATURE_GROUP_CHAT feature flag.
"""
import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ChatMemberUpdated,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)

# Conversation states
GROUP_PROFILE, GROUP_PUSH_TIME, GROUP_LANGUAGE = range(3)


def _get_group_config_path(group_id: str) -> str:
    """Get path to group config file."""
    from config import GROUP_CONFIGS_DIR
    os.makedirs(GROUP_CONFIGS_DIR, exist_ok=True)
    return os.path.join(GROUP_CONFIGS_DIR, f"{group_id}.json")


def load_group_config(group_id: str) -> Optional[Dict[str, Any]]:
    """Load group configuration."""
    path = _get_group_config_path(group_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def save_group_config(group_id: str, config: Dict[str, Any]) -> bool:
    """Save group configuration."""
    path = _get_group_config_path(group_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        logger.error(f"Failed to save group config for {group_id}: {e}")
        return False


def get_all_group_configs() -> list:
    """Get all enabled group configurations."""
    from config import GROUP_CONFIGS_DIR
    configs = []
    if not os.path.exists(GROUP_CONFIGS_DIR):
        return configs
    for filename in os.listdir(GROUP_CONFIGS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(GROUP_CONFIGS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if config.get("enabled", True):
                        configs.append(config)
            except (json.JSONDecodeError, IOError):
                continue
    return configs


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is a group admin."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not user or not chat:
        return False
    
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        admin_ids = [admin.user.id for admin in admins]
        return user.id in admin_ids
    except Exception as e:
        logger.error(f"Failed to check admin status: {e}")
        return False


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /setup command in group chat."""
    from config import FEATURE_GROUP_CHAT
    
    if not FEATURE_GROUP_CHAT:
        return ConversationHandler.END
    
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            "⚠️ /setup 命令仅在群组中使用。\n"
            "Please use /setup in a group chat."
        )
        return ConversationHandler.END
    
    # Check admin permission
    if not await _is_group_admin(update, context):
        await update.message.reply_text(
            "🔒 仅群管理员可以配置 Bot。\n"
            "Only group admins can configure the bot."
        )
        return ConversationHandler.END
    
    group_id = str(chat.id)
    existing = load_group_config(group_id)
    
    if existing:
        keyboard = [
            [InlineKeyboardButton("更新配置 / Update", callback_data="group_update")],
            [InlineKeyboardButton("查看当前配置 / View", callback_data="group_view")],
            [InlineKeyboardButton("禁用推送 / Disable", callback_data="group_disable")],
        ]
        await update.message.reply_text(
            f"📋 群组已配置\n\n"
            f"群名: {existing.get('group_title', chat.title)}\n"
            f"偏好: {existing.get('profile', 'N/A')}\n"
            f"推送时间: {existing.get('push_hour', 9)}:00\n"
            f"语言: {existing.get('language', 'zh')}\n\n"
            f"选择操作:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "🤖 欢迎配置 Web3 Daily Digest!\n\n"
            "请描述这个群组关注的 Web3 领域:\n"
            "例如: DeFi、Layer2、NFT、链上数据分析\n\n"
            "Please describe this group's Web3 interests:"
        )
    
    return GROUP_PROFILE


async def handle_group_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle group profile input."""
    profile = update.message.text.strip()
    
    if len(profile) < 3:
        await update.message.reply_text("请输入更详细的描述。/ Please provide more detail.")
        return GROUP_PROFILE
    
    context.chat_data["group_profile"] = profile
    
    keyboard = [
        [
            InlineKeyboardButton("7:00", callback_data="group_time_7"),
            InlineKeyboardButton("8:00", callback_data="group_time_8"),
            InlineKeyboardButton("9:00", callback_data="group_time_9"),
        ],
        [
            InlineKeyboardButton("10:00", callback_data="group_time_10"),
            InlineKeyboardButton("12:00", callback_data="group_time_12"),
            InlineKeyboardButton("18:00", callback_data="group_time_18"),
        ],
    ]
    
    await update.message.reply_text(
        f"✅ 偏好已记录: {profile}\n\n"
        f"请选择每日推送时间 (北京时间):\n"
        f"Select daily push time (Beijing time):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return GROUP_PUSH_TIME


async def handle_push_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle push time selection."""
    query = update.callback_query
    await query.answer()
    
    hour = int(query.data.replace("group_time_", ""))
    context.chat_data["push_hour"] = hour
    
    keyboard = [
        [
            InlineKeyboardButton("🇨🇳 中文", callback_data="group_lang_zh"),
            InlineKeyboardButton("🇺🇸 English", callback_data="group_lang_en"),
        ],
        [
            InlineKeyboardButton("🇯🇵 日本語", callback_data="group_lang_ja"),
            InlineKeyboardButton("🇰🇷 한국어", callback_data="group_lang_ko"),
        ],
    ]
    
    await query.edit_message_text(
        f"⏰ 推送时间: {hour}:00\n\n"
        f"请选择简报语言:\n"
        f"Select digest language:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return GROUP_LANGUAGE


async def handle_language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection and save config."""
    query = update.callback_query
    await query.answer()
    
    lang = query.data.replace("group_lang_", "")
    chat = update.effective_chat
    group_id = str(chat.id)
    
    config = {
        "group_id": group_id,
        "group_title": chat.title or "Unknown Group",
        "admin_id": str(update.effective_user.id),
        "profile": context.chat_data.get("group_profile", ""),
        "push_hour": context.chat_data.get("push_hour", 9),
        "language": lang,
        "created": datetime.now().isoformat(),
        "enabled": True,
    }
    
    save_group_config(group_id, config)
    
    lang_names = {"zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어"}
    
    await query.edit_message_text(
        f"✅ 群组配置完成!\n\n"
        f"📋 偏好: {config['profile']}\n"
        f"⏰ 推送: 每天 {config['push_hour']}:00\n"
        f"🌐 语言: {lang_names.get(lang, lang)}\n\n"
        f"🤖 Bot 将每天在指定时间推送 Web3 简报。\n"
        f"使用 /setup 随时更新配置。\n\n"
        f"Setup complete! Bot will push daily digest at {config['push_hour']}:00."
    )
    
    # Clear chat data
    context.chat_data.clear()
    
    return ConversationHandler.END


async def handle_group_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View current group config."""
    query = update.callback_query
    await query.answer()
    
    group_id = str(update.effective_chat.id)
    config = load_group_config(group_id)
    
    if config:
        await query.edit_message_text(
            f"📋 当前群组配置\n\n"
            f"偏好: {config.get('profile', 'N/A')}\n"
            f"推送时间: {config.get('push_hour', 9)}:00\n"
            f"语言: {config.get('language', 'zh')}\n"
            f"状态: {'✅ 启用' if config.get('enabled', True) else '❌ 禁用'}\n"
            f"创建: {config.get('created', 'N/A')[:10]}\n\n"
            f"使用 /setup 更新配置。"
        )
    else:
        await query.edit_message_text("未找到配置。请使用 /setup 开始配置。")
    
    return ConversationHandler.END


async def handle_group_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Disable group push."""
    query = update.callback_query
    await query.answer()
    
    group_id = str(update.effective_chat.id)
    config = load_group_config(group_id)
    
    if config:
        config["enabled"] = False
        save_group_config(group_id, config)
        await query.edit_message_text(
            "❌ 群组推送已禁用。\n\n"
            "使用 /setup 重新启用。\n"
            "Group push disabled. Use /setup to re-enable."
        )
    
    return ConversationHandler.END


async def handle_group_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start config update flow."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "请描述群组关注的 Web3 领域:\n"
        "Please describe the group's Web3 interests:"
    )
    
    return GROUP_PROFILE


async def handle_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot being removed from group."""
    from config import FEATURE_GROUP_CHAT
    if not FEATURE_GROUP_CHAT:
        return
    
    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return
    
    new_status = my_chat_member.new_chat_member.status
    chat = my_chat_member.chat
    
    if new_status in ("left", "kicked"):
        group_id = str(chat.id)
        config = load_group_config(group_id)
        if config:
            config["enabled"] = False
            save_group_config(group_id, config)
            logger.info(f"Bot removed from group {group_id} ({chat.title}), disabled config")


def get_group_handler() -> Optional[ConversationHandler]:
    """Create group setup conversation handler. Returns None if feature disabled."""
    from config import FEATURE_GROUP_CHAT
    if not FEATURE_GROUP_CHAT:
        return None
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("setup", setup_command),
        ],
        states={
            GROUP_PROFILE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_profile),
                CallbackQueryHandler(handle_group_update, pattern="^group_update$"),
                CallbackQueryHandler(handle_group_view, pattern="^group_view$"),
                CallbackQueryHandler(handle_group_disable, pattern="^group_disable$"),
            ],
            GROUP_PUSH_TIME: [
                CallbackQueryHandler(handle_push_time, pattern=r"^group_time_\d+$"),
            ],
            GROUP_LANGUAGE: [
                CallbackQueryHandler(handle_language_choice, pattern=r"^group_lang_\w+$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
        ],
        per_chat=True,
    )


def get_group_callbacks():
    """Get standalone group callback handlers."""
    from config import FEATURE_GROUP_CHAT
    if not FEATURE_GROUP_CHAT:
        return []
    return [
        ChatMemberHandler(handle_bot_removed, ChatMemberHandler.MY_CHAT_MEMBER),
    ]
