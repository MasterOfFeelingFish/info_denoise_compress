"""
Payment Handler (T5)

Handles plan upgrades via:
1. Telegram Payments (when PAYMENT_PROVIDER_TOKEN is configured)
2. Manual redemption codes (always available)

Controlled by FEATURE_PAYMENT feature flag.
"""
import json
import logging
import os
import secrets
from datetime import datetime
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

from utils.json_storage import get_user_language
from locales.ui_strings import get_ui_locale
from utils.permissions import get_user_plan, upgrade_user_plan

logger = logging.getLogger(__name__)

# Conversation state for redeem code
AWAITING_REDEEM_CODE = 200


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available subscription plans."""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    telegram_id = str(user.id)
    lang = get_user_language(telegram_id)
    ui = get_ui_locale(lang)
    current_plan = get_user_plan(telegram_id)
    
    plan_text = (
        f"💳 {ui['payment_plans_title']}\n"
        f"{'─' * 24}\n\n"
        f"{ui['current_plan']}: {current_plan.upper()}\n\n"
        f"🆓 Free\n"
        f"  • {ui['plan_free_digest']}\n"
        f"  • {ui['plan_free_chat']}\n\n"
        f"⭐ Pro — $4.99/{ui['per_month']}\n"
        f"  • {ui['plan_pro_digest']}\n"
        f"  • {ui['plan_pro_chat']}\n"
        f"  • {ui['plan_pro_sources']}\n"
        f"  • {ui['plan_pro_alerts']}\n"
        f"  • {ui['plan_pro_priority']}\n"
    )
    
    keyboard = []
    if current_plan != "pro":
        keyboard.append([InlineKeyboardButton(
            ui['btn_subscribe_pro'],
            callback_data="payment_subscribe_pro"
        )])
        keyboard.append([InlineKeyboardButton(
            ui['btn_redeem_code'],
            callback_data="payment_redeem"
        )])
    keyboard.append([InlineKeyboardButton(ui['back'], callback_data="back_to_start")])
    
    if query:
        await query.edit_message_text(plan_text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.message:
        await update.message.reply_text(plan_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def initiate_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate Telegram payment for Pro plan."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    telegram_id = str(user.id)
    lang = get_user_language(telegram_id)
    ui = get_ui_locale(lang)
    
    from config import PAYMENT_PROVIDER_TOKEN
    
    if not PAYMENT_PROVIDER_TOKEN:
        # No payment token configured - show manual upgrade path
        from config import ADMIN_TELEGRAM_IDS
        admin_list = ", ".join([f"[Admin](tg://user?id={aid})" for aid in ADMIN_TELEGRAM_IDS[:2]])
        await query.edit_message_text(
            f"💳 {ui['payment_manual_title']}\n"
            f"{'─' * 24}\n\n"
            f"**{ui['payment_manual_contact']}**\n"
            f"{ui['payment_manual_contact_desc'].format(admins=admin_list)}\n\n"
            f"**{ui['payment_manual_redeem']}**\n"
            f"{ui['payment_manual_redeem_desc']}\n\n"
            f"{ui['payment_manual_price']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    ui['btn_redeem_code'],
                    callback_data="payment_redeem"
                )],
                [InlineKeyboardButton(ui['back'], callback_data="payment_plans")]
            ])
        )
        return
    
    # Send invoice via Telegram Payments
    title = "Web3 Digest Pro"
    description = "Monthly Pro subscription - unlimited features"
    payload = f"pro_monthly_{telegram_id}"
    currency = "USD"
    prices = [LabeledPrice("Pro Monthly", 499)]  # Amount in cents
    
    await context.bot.send_invoice(
        chat_id=query.message.chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pre-checkout query from Telegram."""
    query = update.pre_checkout_query
    
    # Validate the payment
    if query.invoice_payload.startswith("pro_monthly_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Invalid payment payload")


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payment confirmation."""
    user = update.effective_user
    telegram_id = str(user.id)
    lang = get_user_language(telegram_id)
    ui = get_ui_locale(lang)
    
    # Upgrade user plan
    success = upgrade_user_plan(telegram_id, "pro", duration_days=30)
    
    if success:
        await update.message.reply_text(
            f"🎉 {ui['payment_success']}\n\n"
            f"{ui['plan_upgraded']}\n"
            f"{ui['enjoy_features']}"
        )
    else:
        await update.message.reply_text(
            f"⚠️ {ui['payment_error']}\n"
            f"{ui['contact_admin']}"
        )


# ============ Redemption Code System ============

def _get_codes_file():
    from config import DATA_DIR
    return os.path.join(DATA_DIR, "redeem_codes.json")


def _load_codes():
    path = _get_codes_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_codes(codes):
    path = _get_codes_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)


def generate_redeem_code(days=30, created_by="admin"):
    """Generate a new redemption code. Returns the code string."""
    code = secrets.token_hex(4).upper()  # 8-char hex code
    codes = _load_codes()
    codes[code] = {
        "days": days,
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
        "used": False,
        "used_by": None,
        "used_at": None,
    }
    _save_codes(codes)
    return code


def redeem_code(code, telegram_id):
    """Try to redeem a code. Returns (success, message, days)."""
    codes = _load_codes()
    code = code.strip().upper()

    if code not in codes:
        return False, "invalid", 0

    info = codes[code]
    if info["used"]:
        return False, "already_used", 0

    days = info.get("days", 30)

    # Mark as used
    codes[code]["used"] = True
    codes[code]["used_by"] = telegram_id
    codes[code]["used_at"] = datetime.now().isoformat()
    _save_codes(codes)

    # Upgrade user
    upgrade_user_plan(telegram_id, "pro", duration_days=days)

    return True, "success", days


async def payment_redeem_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show prompt for user to enter redemption code."""
    from utils.conv_manager import activate_conv
    activate_conv(context, "payment")

    query = update.callback_query
    await query.answer()

    user = update.effective_user
    telegram_id = str(user.id)
    lang = get_user_language(telegram_id)
    ui = get_ui_locale(lang)

    await query.edit_message_text(
        f"🎫 {ui['redeem_title']}\n"
        f"{'─' * 24}\n\n"
        f"{ui['redeem_prompt']}\n\n"
        f"👇 {ui['redeem_hint']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(ui['cancel'], callback_data="payment_plans")]
        ])
    )
    return AWAITING_REDEEM_CODE


async def handle_redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle redemption code input."""
    from utils.conv_manager import is_active_conv
    if not is_active_conv(context, "payment"):
        return ConversationHandler.END

    user = update.effective_user
    telegram_id = str(user.id)
    lang = get_user_language(telegram_id)
    ui = get_ui_locale(lang)

    code_input = update.message.text.strip()

    success, status, days = redeem_code(code_input, telegram_id)

    if success:
        await update.message.reply_text(
            f"🎉 {ui['redeem_success']}\n\n"
            f"{ui['plan_upgraded']}\n"
            f"⏳ {ui['redeem_duration']}: {days} {ui['days']}\n\n"
            f"{ui['enjoy_features']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(ui['back_to_main'], callback_data="back_to_start")]
            ])
        )
    elif status == "already_used":
        await update.message.reply_text(
            f"⚠️ {ui['redeem_already_used']}\n"
            f"{ui['contact_admin']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(ui['btn_redeem_code'], callback_data="payment_redeem")],
                [InlineKeyboardButton(ui['back'], callback_data="payment_plans")]
            ])
        )
    else:
        await update.message.reply_text(
            f"❌ {ui['redeem_invalid']}\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(ui['btn_redeem_code'], callback_data="payment_redeem")],
                [InlineKeyboardButton(ui['back'], callback_data="payment_plans")]
            ])
        )

    return ConversationHandler.END


async def admin_generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to generate a redemption code."""
    from handlers.admin import is_admin
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("🔒 Admin only.")
        return

    # Parse days from args
    days = 30
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass

    code = generate_redeem_code(days=days, created_by=str(user.id))

    lang = get_user_language(str(user.id))
    ui = get_ui_locale(lang)

    await update.message.reply_text(
        f"{ui['admin_code_generated']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Code: `{code}`\n"
        f"⏳ {ui['admin_code_duration'].format(days=days)}\n"
        f"👤 {ui['admin_code_creator'].format(name=user.first_name)}\n\n"
        f"{ui['admin_code_instruction']}",
        parse_mode="Markdown"
    )


def get_payment_handlers():
    """Get all payment-related handlers."""
    from config import FEATURE_PAYMENT

    handlers = []

    # Redemption code ConversationHandler (always available)
    redeem_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(payment_redeem_prompt, pattern="^payment_redeem$"),
        ],
        states={
            AWAITING_REDEEM_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem_code),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(show_plans, pattern="^payment_plans$"),
        ],
        per_message=False,
    )
    handlers.append(redeem_conv)

    # Plan display (always available)
    handlers.append(CallbackQueryHandler(show_plans, pattern="^payment_plans$"))
    handlers.append(CallbackQueryHandler(initiate_payment, pattern="^payment_subscribe_pro$"))

    # Admin code generation command (always available)
    handlers.append(CommandHandler("gencode", admin_generate_code))

    if FEATURE_PAYMENT:
        # Telegram Payments handlers (only when payment token is configured)
        handlers.append(PreCheckoutQueryHandler(precheckout_callback))
        handlers.append(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    return handlers
