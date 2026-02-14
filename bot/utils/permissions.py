"""
Permission System (T5)

Provides plan-based feature access control.
Supports free/pro tiers with configurable limits.
Controlled by FEATURE_PAYMENT feature flag.
"""
import json
import os
import logging
import functools
import copy
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Keys for admin UI iteration (order preserved)
FEATURE_KEYS: List[str] = [
    "daily_digest",
    "custom_sources",
    "ai_chat",
    "advanced_filters",
    "priority_push",
    "source_health_alerts",
]
LIMIT_KEYS: List[str] = [
    "ai_chat_daily",
    "custom_sources_max",
    "digest_items_max",
]

# Default plan configuration
DEFAULT_PLAN_CONFIG = {
    "free": {
        "name": "Free",
        "features": {
            "daily_digest": True,
            "custom_sources": False,
            "ai_chat": True,
            "advanced_filters": False,
            "priority_push": False,
            "source_health_alerts": False,
        },
        "limits": {
            "ai_chat_daily": 5,
            "custom_sources_max": 0,
            "digest_items_max": 15,
        }
    },
    "pro": {
        "name": "Pro",
        "features": {
            "daily_digest": True,
            "custom_sources": True,
            "ai_chat": True,
            "advanced_filters": True,
            "priority_push": True,
            "source_health_alerts": True,
        },
        "limits": {
            "ai_chat_daily": 50,
            "custom_sources_max": 20,
            "digest_items_max": 30,
        }
    }
}


def _load_plan_config() -> Dict[str, Any]:
    """Load plan configuration from file or use defaults."""
    from config import PLAN_CONFIG_FILE
    if os.path.exists(PLAN_CONFIG_FILE):
        try:
            with open(PLAN_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return copy.deepcopy(DEFAULT_PLAN_CONFIG)


def get_plan_config() -> Dict[str, Any]:
    """Return a deep copy of current plan config (for admin edit without mutating live config)."""
    return copy.deepcopy(_load_plan_config())


def save_plan_config(config: Dict[str, Any]) -> bool:
    """Persist plan config to PLAN_CONFIG_FILE. Returns True on success."""
    from config import PLAN_CONFIG_FILE, DATA_DIR
    try:
        os.makedirs(os.path.dirname(PLAN_CONFIG_FILE) or ".", exist_ok=True)
        with open(PLAN_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("Plan config saved to %s", PLAN_CONFIG_FILE)
        return True
    except IOError as e:
        logger.exception("Failed to save plan config: %s", e)
        return False


def get_user_plan(telegram_id: str) -> str:
    """
    Get user's current plan, checking expiry.
    
    Returns 'free' if:
    - User has no plan field (backward compatible)
    - Plan has expired
    - User doesn't exist
    """
    from utils.json_storage import get_user
    
    user = get_user(telegram_id)
    if not user:
        return "free"
    
    plan = user.get("plan", "free")
    if plan == "free":
        return "free"
    
    # Check expiry
    plan_expires = user.get("plan_expires")
    if plan_expires:
        try:
            expires_dt = datetime.fromisoformat(plan_expires)
            if datetime.now() > expires_dt:
                # Plan expired, auto-downgrade
                logger.info(f"User {telegram_id} plan expired, downgrading to free")
                return "free"
        except (ValueError, TypeError):
            pass
    
    return plan


def check_feature(telegram_id: str, feature: str) -> bool:
    """
    Check if a user has access to a specific feature.
    Admin accounts bypass plan restrictions (all features allowed).
    Free users who completed onboarding get one-time redeem for paid features (e.g. custom_sources).
    
    Args:
        telegram_id: User's Telegram ID
        feature: Feature key (e.g., 'custom_sources', 'ai_chat')
    
    Returns:
        True if user has access
    """
    from config import FEATURE_PAYMENT
    if not FEATURE_PAYMENT:
        return True  # If payment system is disabled, all features are available
    
    # Admin bypass: admins have access to all features
    try:
        from handlers.admin import is_admin
        if is_admin(int(telegram_id)):
            return True
    except (ValueError, TypeError):
        pass
    
    plan = get_user_plan(telegram_id)
    config = _load_plan_config()
    plan_config = config.get(plan, config.get("free", {}))
    allowed = plan_config.get("features", {}).get(feature, False)
    if allowed:
        return True
    # Free user: allow once if onboarding redeem available (only for custom_sources, not priority_push etc.)
    if plan == "free" and feature == "custom_sources":
        from utils.json_storage import get_user
        user = get_user(telegram_id)
        if user and user.get("onboarding_paid_redeem_available"):
            return True
    return False


def get_feature_limit(telegram_id: str, feature: str) -> int:
    """
    Get the limit for a feature based on user's plan.
    Admin accounts bypass limits (unlimited).
    Free users with onboarding redeem get limit 1 for custom_sources_max (one free slot).
    
    Args:
        telegram_id: User's Telegram ID
        feature: Limit key (e.g., 'ai_chat_daily', 'custom_sources_max')
    
    Returns:
        Limit value (0 = not allowed, -1 = unlimited)
    """
    from config import FEATURE_PAYMENT
    if not FEATURE_PAYMENT:
        return 999  # No limits when payment is disabled
    
    # Admin bypass: admins have unlimited access
    try:
        from handlers.admin import is_admin
        if is_admin(int(telegram_id)):
            return 999
    except (ValueError, TypeError):
        pass
    
    plan = get_user_plan(telegram_id)
    config = _load_plan_config()
    plan_config = config.get(plan, config.get("free", {}))
    limit = plan_config.get("limits", {}).get(feature, 0)
    # Free user with onboarding redeem: allow 1 custom source
    if plan == "free" and feature == "custom_sources_max" and limit == 0:
        from utils.json_storage import get_user
        user = get_user(telegram_id)
        if user and user.get("onboarding_paid_redeem_available"):
            return 1
    return limit


def require_plan(feature: str):
    """
    Decorator that checks if user has access to a feature.
    
    If user doesn't have access, sends an upgrade prompt instead
    of executing the handler.
    
    Args:
        feature: Feature key to check
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            from config import FEATURE_PAYMENT
            if not FEATURE_PAYMENT:
                return await func(update, context, *args, **kwargs)
            
            user = update.effective_user
            if not user:
                return await func(update, context, *args, **kwargs)
            
            telegram_id = str(user.id)
            if check_feature(telegram_id, feature):
                return await func(update, context, *args, **kwargs)
            
            # User doesn't have access - show upgrade prompt
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from utils.json_storage import get_user_language
            from locales.ui_strings import get_ui_locale
            
            lang = get_user_language(telegram_id)
            ui = get_ui_locale(lang)
            
            plan = get_user_plan(telegram_id)
            upgrade_text = (
                f"🔒 {ui.get('feature_locked', 'This feature requires a Pro plan')}\n\n"
                f"{ui.get('current_plan', 'Current plan')}: {plan.upper()}\n\n"
                f"{ui.get('upgrade_prompt', 'Upgrade to Pro to unlock all features.')}"
            )
            
            keyboard = [
                [InlineKeyboardButton(
                    ui.get("btn_upgrade", "⭐ Upgrade to Pro"),
                    callback_data="payment_plans"
                )],
                [InlineKeyboardButton(ui.get("back", "Back"), callback_data="back_to_start")],
            ]
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    upgrade_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif update.message:
                await update.message.reply_text(
                    upgrade_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            return None
        return wrapper
    return decorator


def upgrade_user_plan(telegram_id: str, plan: str, duration_days: int = 30) -> bool:
    """
    Upgrade a user's plan.
    
    Args:
        telegram_id: User's Telegram ID
        plan: New plan name (e.g., 'pro')
        duration_days: Duration in days
    
    Returns:
        True if successful
    """
    from datetime import timedelta
    from utils.json_storage import _read_json, _write_json, USERS_FILE
    
    data = _read_json(USERS_FILE)
    users = data.get("users", [])
    
    for user in users:
        if user.get("telegram_id") == telegram_id:
            user["plan"] = plan
            user["plan_expires"] = (
                datetime.now() + timedelta(days=duration_days)
            ).isoformat()
            user["payment_history"] = user.get("payment_history", [])
            user["payment_history"].append({
                "plan": plan,
                "date": datetime.now().isoformat(),
                "duration_days": duration_days,
            })
            _write_json(USERS_FILE, data)
            logger.info(f"User {telegram_id} upgraded to {plan} for {duration_days} days")
            return True
    
    return False
