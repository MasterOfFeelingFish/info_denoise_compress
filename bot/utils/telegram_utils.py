"""
Telegram Bot utility functions.
"""
import logging
from telegram import CallbackQuery
from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def safe_answer_callback_query(query: CallbackQuery, text: str = "", show_alert: bool = False):
    """
    Safely answer a callback query, ignoring timeout errors.

    When a callback query is too old (> ~30 seconds), Telegram will reject the answer.
    This is not a critical error, so we catch and log it.
    """
    try:
        await query.answer(text, show_alert=show_alert)
    except BadRequest as e:
        if "query is too old" in str(e).lower() or "timeout expired" in str(e).lower():
            # Query expired, not a problem
            logger.debug(f"Callback query expired (expected for slow operations)")
        else:
            # Other BadRequest, re-raise
            raise
