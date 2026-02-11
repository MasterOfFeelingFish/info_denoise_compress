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
        f"💳 {ui.get('payment_plans_title', 'Subscription Plans')}\n"
        f"{'─' * 24}\n\n"
        f"{ui.get('current_plan', 'Current plan')}: {current_plan.upper()}\n\n"
        f"🆓 Free\n"
        f"  • {ui.get('plan_free_digest', 'Daily digest (15 items)')}\n"
        f"  • {ui.get('plan_free_chat', 'AI chat (5/day)')}\n\n"
        f"⭐ Pro — $4.99/{ui.get('per_month', 'month')}\n"
        f"  • {ui.get('plan_pro_digest', 'Daily digest (30 items)')}\n"
        f"  • {ui.get('plan_pro_chat', 'AI chat (50/day)')}\n"
        f"  • {ui.get('plan_pro_sources', 'Custom sources (20)')}\n"
        f"  • {ui.get('plan_pro_alerts', 'Source health alerts')}\n"
        f"  • {ui.get('plan_pro_priority', 'Priority push')}\n"
    )
    
    keyboard = []
    if current_plan != "pro":
        keyboard.append([InlineKeyboardButton(
            ui.get("btn_subscribe_pro", "⭐ Subscribe Pro ($4.99/mo)"),
            callback_data="payment_subscribe_pro"
        )])
        keyboard.append([InlineKeyboardButton(
            ui.get("btn_redeem_code", "🎫 兑换码 / Redeem Code"),
            callback_data="payment_redeem"
        )])
    keyboard.append([InlineKeyboardButton(ui.get("back", "Back"), callback_data="back_to_start")])
    
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
            f"💳 {ui.get('payment_manual_title', '升级 Pro 方式')}\n"
            f"{'─' * 24}\n\n"
            f"📩 **方式一：联系管理员**\n"
            f"私信管理员 {admin_list} 转账后获取兑换码\n\n"
            f"🎫 **方式二：已有兑换码**\n"
            f"如果已有兑换码，点击下方按钮输入\n\n"
            f"💰 价格: $4.99/月 (支持 USDT/微信/支付宝)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    ui.get("btn_redeem_code", "🎫 输入兑换码"),
                    callback_data="payment_redeem"
                )],
                [InlineKeyboardButton(ui.get("back", "Back"), callback_data="payment_plans")]
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
            f"🎉 {ui.get('payment_success', 'Payment successful!')}\n\n"
            f"{ui.get('plan_upgraded', 'Your plan has been upgraded to Pro.')}\n"
            f"{ui.get('enjoy_features', 'Enjoy all Pro features!')}"
        )
    else:
        await update.message.reply_text(
            f"⚠️ {ui.get('payment_error', 'Payment received but upgrade failed.')}\n"
            f"{ui.get('contact_admin', 'Please contact admin.')}"
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
        f"🎫 {ui.get('redeem_title', '输入兑换码')}\n"
        f"{'─' * 24}\n\n"
        f"{ui.get('redeem_prompt', '请在聊天窗口输入你的兑换码：')}\n\n"
        f"👇 {ui.get('redeem_hint', '直接输入兑换码并发送，或 /cancel 取消')}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(ui.get("cancel", "Cancel"), callback_data="payment_plans")]
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
            f"🎉 {ui.get('redeem_success', '兑换成功！')}\n\n"
            f"{ui.get('plan_upgraded', 'Your plan has been upgraded to Pro.')}\n"
            f"⏳ {ui.get('redeem_duration', '有效期')}: {days} {ui.get('days', '天')}\n\n"
            f"{ui.get('enjoy_features', 'Enjoy all Pro features!')}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(ui.get("back_to_main", "Main Menu"), callback_data="back_to_start")]
            ])
        )
    elif status == "already_used":
        await update.message.reply_text(
            f"⚠️ {ui.get('redeem_already_used', '该兑换码已被使用。')}\n"
            f"{ui.get('contact_admin', 'Please contact admin.')}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(ui.get("btn_redeem_code", "🎫 重新输入"), callback_data="payment_redeem")],
                [InlineKeyboardButton(ui.get("back", "Back"), callback_data="payment_plans")]
            ])
        )
    else:
        await update.message.reply_text(
            f"❌ {ui.get('redeem_invalid', '无效的兑换码。请检查后重试。')}\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(ui.get("btn_redeem_code", "🎫 重新输入"), callback_data="payment_redeem")],
                [InlineKeyboardButton(ui.get("back", "Back"), callback_data="payment_plans")]
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

    await update.message.reply_text(
        f"🎫 兑换码已生成\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Code: `{code}`\n"
        f"⏳ 有效期: {days} 天\n"
        f"👤 创建者: {user.first_name}\n\n"
        f"将此码发给用户，用户在 Bot 中点击\n"
        f"「🎫 兑换码」按钮输入即可升级 Pro。",
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
