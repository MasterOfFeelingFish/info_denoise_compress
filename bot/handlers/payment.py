"""
Payment Handler (T5)

Handles Telegram Payments flow for plan upgrades.
Controlled by FEATURE_PAYMENT feature flag.

Note: Without a Payment Provider Token, the actual payment
API calls are placeholder implementations tested via mocks.
"""
import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

from utils.json_storage import get_user_language
from locales.ui_strings import get_ui_locale
from utils.permissions import get_user_plan, upgrade_user_plan

logger = logging.getLogger(__name__)


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
        # No payment token configured - show placeholder
        await query.edit_message_text(
            f"🚧 {ui.get('payment_coming_soon', 'Payment system coming soon!')}\n\n"
            f"{ui.get('payment_contact', 'Contact admin for manual upgrade.')}",
            reply_markup=InlineKeyboardMarkup([
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


def get_payment_handlers():
    """Get all payment-related handlers."""
    from config import FEATURE_PAYMENT
    if not FEATURE_PAYMENT:
        return []
    
    return [
        CallbackQueryHandler(show_plans, pattern="^payment_plans$"),
        CallbackQueryHandler(initiate_payment, pattern="^payment_subscribe_pro$"),
        PreCheckoutQueryHandler(precheckout_callback),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment),
    ]
