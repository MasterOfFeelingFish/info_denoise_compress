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

from locales.ui_strings import get_ui_locale
from services.language_service import normalize_language_code

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


def _get_ui_for_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    group_id: str = None,
    prefer_user_language: bool = False,
):
    """
    Get UI strings for group context.

    When prefer_user_language is False (default):
      1. Existing group config language (if group already configured)
      2. Admin user's Telegram language_code
      3. Fallback to English

    When prefer_user_language is True (e.g. first-time setup / welcome):
      1. Admin user's Telegram language_code (so current admin sees their own language)
      2. Existing group config language
      3. Fallback to English
    """
    user = update.effective_user
    raw_code = getattr(user, "language_code", None) if user else None
    user_lang = normalize_language_code(raw_code) if raw_code else None

    if prefer_user_language:
        # First-time setup / welcome: use admin's language so they see their client language
        resolved = user_lang or "en"
        logger.info(
            "Group setup UI: user_id=%s, language_code=%s, resolved=%s",
            user.id if user else None,
            raw_code,
            resolved,
        )
        return get_ui_locale(resolved)

    # Try existing group config language
    if group_id:
        config = load_group_config(group_id)
        if config and config.get("language"):
            return get_ui_locale(config["language"])

    if user_lang:
        return get_ui_locale(user_lang)

    return get_ui_locale("en")


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
        # Not in a group - show setup guide (use current user's language)
        ui = _get_ui_for_group(update, context, prefer_user_language=True)
        await update.message.reply_text(
            f"{ui['group_guide_title']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ui['group_guide_add_bot']}\n\n"
            f"{ui['group_guide_step1']}\n"
            f"{ui['group_guide_step2']}\n"
            f"{ui['group_guide_step3']}\n"
            f"{ui['group_guide_step4']}\n"
            f"{ui['group_guide_step5']}\n\n"
            f"{ui['group_guide_config_flow']}\n"
            f"{ui['group_guide_config_desc']}\n\n"
            f"{ui['group_guide_footer']}"
        )
        return ConversationHandler.END
    
    # Check admin permission
    if not await _is_group_admin(update, context):
        ui = _get_ui_for_group(update, context, prefer_user_language=True)
        await update.message.reply_text(ui['group_admin_only'])
        return ConversationHandler.END
    
    group_id = str(chat.id)
    existing = load_group_config(group_id)
    # For "already configured" screen use group's saved language; for new-group welcome use admin's language
    ui = _get_ui_for_group(
        update, context, group_id, prefer_user_language=(not existing)
    )
    
    if existing:
        keyboard = [
            [InlineKeyboardButton(ui['group_btn_update'], callback_data="group_update")],
            [InlineKeyboardButton(ui['group_btn_view'], callback_data="group_view")],
            [InlineKeyboardButton(ui['group_btn_disable'], callback_data="group_disable")],
        ]
        await update.message.reply_text(
            f"{ui['group_already_configured']}\n\n"
            f"{ui['group_label_name']}: {existing.get('group_title', chat.title)}\n"
            f"{ui['group_label_interests']}: {existing.get('profile', 'N/A')}\n"
            f"{ui['group_label_push_time']}: {existing.get('push_hour', 9)}:00\n"
            f"{ui['group_label_language']}: {existing.get('language', 'en')}\n\n"
            f"{ui['group_choose_action']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            f"{ui['group_welcome_new']}\n\n"
            f"{ui['group_enter_interests']}\n"
            f"{ui['group_enter_interests_example']}"
        )
    
    return GROUP_PROFILE


async def handle_group_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle group profile input (first-time setup flow: use client language)."""
    profile = update.message.text.strip()
    chat = update.effective_chat
    group_id = str(chat.id) if chat else None
    ui = _get_ui_for_group(update, context, group_id, prefer_user_language=True)
    
    if len(profile) < 3:
        await update.message.reply_text(ui['group_input_too_short'])
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
        f"{ui['group_interests_saved'].format(profile=profile)}\n\n"
        f"{ui['group_select_push_time']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return GROUP_PUSH_TIME


async def handle_push_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle push time selection (first-time setup flow: use client language)."""
    query = update.callback_query
    await query.answer()
    
    hour = int(query.data.replace("group_time_", ""))
    context.chat_data["push_hour"] = hour
    
    chat = update.effective_chat
    group_id = str(chat.id) if chat else None
    ui = _get_ui_for_group(update, context, group_id, prefer_user_language=True)
    
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
        f"{ui['group_time_saved'].format(hour=hour)}\n\n"
        f"{ui['group_select_language']}",
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
    
    # Use the selected language for the completion message
    ui = get_ui_locale(lang)
    
    await query.edit_message_text(
        f"{ui['group_setup_complete']}\n\n"
        f"{ui['group_setup_interests'].format(profile=config['profile'])}\n"
        f"{ui['group_setup_push'].format(hour=config['push_hour'])}\n"
        f"{ui['group_setup_lang'].format(lang_name=lang_names.get(lang, lang))}\n\n"
        f"{ui['group_setup_footer']}"
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
        lang = config.get("language", "en")
        ui = get_ui_locale(lang)
        status = ui['group_status_enabled'] if config.get('enabled', True) else ui['group_status_disabled']
        await query.edit_message_text(
            f"{ui['group_view_title']}\n\n"
            f"{ui['group_label_interests']}: {config.get('profile', 'N/A')}\n"
            f"{ui['group_label_push_time']}: {config.get('push_hour', 9)}:00\n"
            f"{ui['group_label_language']}: {config.get('language', 'en')}\n"
            f"{ui['group_label_status']}: {status}\n"
            f"{ui['group_label_created']}: {config.get('created', 'N/A')[:10]}\n\n"
            f"{ui['group_view_footer']}"
        )
    else:
        ui = _get_ui_for_group(update, context)
        await query.edit_message_text(ui['group_no_config'])
    
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
        lang = config.get("language", "en")
        ui = get_ui_locale(lang)
        await query.edit_message_text(
            f"{ui['group_disabled']}\n\n"
            f"{ui['group_disabled_footer']}"
        )
    
    return ConversationHandler.END


async def handle_group_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start config update flow."""
    query = update.callback_query
    await query.answer()
    
    group_id = str(update.effective_chat.id)
    ui = _get_ui_for_group(update, context, group_id)
    
    await query.edit_message_text(
        f"{ui['group_enter_interests']}\n"
        f"{ui['group_enter_interests_example']}"
    )
    
    return GROUP_PROFILE


async def handle_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when bot is added to a group."""
    from config import FEATURE_GROUP_CHAT
    if not FEATURE_GROUP_CHAT:
        return

    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return

    chat = my_chat_member.chat
    if chat.type not in ("group", "supergroup"):
        return

    # Resolve language from inviter (user who added the bot)
    from_user = my_chat_member.from_user
    raw_code = getattr(from_user, "language_code", None) if from_user else None
    lang = normalize_language_code(raw_code) if raw_code else "en"
    ui = get_ui_locale(lang)

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=ui["group_welcome_on_join"]
        )
        logger.info(f"Welcome message sent to group {chat.id} ({chat.title})")
    except Exception as e:
        logger.warning(f"Failed to send welcome to group {chat.id}: {e}")


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


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route my_chat_member updates to add or remove handler."""
    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return

    new_status = my_chat_member.new_chat_member.status

    if new_status in ("member", "administrator"):
        await handle_bot_added(update, context)
    elif new_status in ("left", "kicked"):
        await handle_bot_removed(update, context)


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
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER),
    ]
