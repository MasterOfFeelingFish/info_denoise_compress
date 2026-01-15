"""
Digest Processor - Handles single user digest generation

This module is separated to avoid circular imports between main.py and handlers/start.py
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from telegram.ext import ContextTypes
from config import MAX_DIGEST_ITEMS
from utils.telegram_utils import send_message_safe

logger = logging.getLogger(__name__)


async def process_single_user(
    context: ContextTypes.DEFAULT_TYPE,
    user: Dict[str, Any],
    today: str,
    global_raw_content: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process digest generation and sending for a single user.

    Args:
        context: Telegram context
        user: User dict with telegram_id
        today: Date string (YYYY-MM-DD)
        global_raw_content: Pre-fetched global RSS data (optional)
                           If provided, will filter from this instead of fetching

    Returns:
        Dict with status info: {"user": telegram_id, "status": "success|error", ...}
    """
    from services.rss_fetcher import fetch_user_sources, get_user_source_list
    from services.content_filter import filter_content_for_user, get_ai_summary
    from services.report_generator import (
        generate_empty_report,
        detect_user_language,
        prepare_digest_messages,
    )
    from utils.json_storage import (
        get_user_profile,
        save_user_raw_content,
        save_user_daily_stats,
    )
    from handlers.feedback import create_feedback_keyboard, create_item_feedback_keyboard

    telegram_id = user.get("telegram_id")
    user_id = user.get("id")  # Extract user_id to avoid race condition
    if not telegram_id:
        return {"user": None, "status": "skipped", "reason": "no telegram_id"}

    try:
        # 1. Fetch content from this user's sources
        user_sources = get_user_source_list(telegram_id)
        sources_count = sum(len(s) for s in user_sources.values())

        # ===== Pre-fetch optimization: Filter from global data if available =====
        if global_raw_content is not None:
            # Filter global data by user's subscribed sources
            user_source_names = set()
            for category_sources in user_sources.values():
                user_source_names.update(category_sources)

            # Filter items that match user's sources
            raw_content = [
                item for item in global_raw_content
                if item.get("source") in user_source_names
            ]

            logger.info(f"User {telegram_id}: Filtered {len(raw_content)} items "
                       f"from global data ({sources_count} sources)")
        else:
            # Fallback: Individual fetch (used for /test command and first digest)
            raw_content = await fetch_user_sources(telegram_id, hours_back=24)
            logger.info(f"User {telegram_id}: Fetched {len(raw_content)} items "
                       f"from {sources_count} sources")
        # ===== Filtering complete =====

        # Save raw content for this user
        save_user_raw_content(telegram_id, today, raw_content, user_id=user_id)

        # Get user profile for language detection
        profile = get_user_profile(telegram_id) or ""
        user_lang = detect_user_language(profile)

        # 2. Filter content for user
        filtered_items = await filter_content_for_user(
            telegram_id=telegram_id,
            raw_content=raw_content,
            max_items=MAX_DIGEST_ITEMS
        )

        chat_id = int(telegram_id)
        report_id = f"{today}_{telegram_id}"

        if filtered_items:
            # Generate AI summary
            ai_summary = await get_ai_summary(filtered_items, profile)

            # Prepare messages: header + individual items
            header, item_messages = prepare_digest_messages(
                filtered_items=filtered_items,
                ai_summary=ai_summary,
                sources_count=sources_count,
                raw_count=len(raw_content),
                lang=user_lang
            )

            # Send header message
            await send_message_safe(context,
                chat_id=chat_id,
                text=header,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

            # Send each item with feedback buttons
            for item_msg, item_id in item_messages:
                # Section headers don't get feedback buttons
                if item_id.startswith("section_"):
                    await send_message_safe(context,
                        chat_id=chat_id,
                        text=item_msg,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                else:
                    item_keyboard = create_item_feedback_keyboard(item_id)
                    await send_message_safe(context,
                        chat_id=chat_id,
                        text=item_msg,
                        reply_markup=item_keyboard,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )

            # Send final feedback message
            final_keyboard = create_feedback_keyboard(report_id)
            locale_prompt = "这份简报有帮助吗？" if user_lang == "zh" else "Was this helpful?"
            await send_message_safe(context,
                chat_id=chat_id,
                text=f"{'─' * 28}\n{locale_prompt}",
                reply_markup=final_keyboard
            )

        else:
            # No content - send empty report
            report = generate_empty_report(lang=user_lang)
            await send_message_safe(context,
                chat_id=chat_id,
                text=report,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        # 3. Save per-user daily stats
        save_user_daily_stats(
            telegram_id=telegram_id,
            date=today,
            sources_monitored=sources_count,
            raw_items_scanned=len(raw_content),
            items_sent=len(filtered_items),
            status="success",
            filtered_items=filtered_items,
            user_id=user_id
        )

        logger.info(f"Sent digest to {telegram_id}: {len(filtered_items)} items")
        return {
            "user": telegram_id,
            "status": "success",
            "items_sent": len(filtered_items)
        }

    except Exception as e:
        logger.error(f"Failed to send digest to {telegram_id}: {e}")
        # Save error status
        save_user_daily_stats(
            telegram_id=telegram_id,
            date=today,
            sources_monitored=0,
            raw_items_scanned=0,
            items_sent=0,
            status=f"error: {str(e)[:50]}",
            user_id=user_id
        )
        return {
            "user": telegram_id,
            "status": "error",
            "error": str(e)[:100]
        }
