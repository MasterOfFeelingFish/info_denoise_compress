"""
Profile Updater Service

Analyzes user feedback and updates user profiles using AI.
Implements the feedback learning loop for personalization.

Reference: Plan specification for profile update with Gemini 3
"""
import logging
from typing import List, Dict, Any, Optional

from services.gemini import call_gemini
from utils.prompt_loader import get_prompt
from utils.json_storage import (
    get_users,
    get_user,
    get_user_profile,
    save_user_profile,
    get_user_feedbacks,
)

logger = logging.getLogger(__name__)


def format_feedbacks_for_ai(feedbacks: List[Dict[str, Any]]) -> str:
    """Format feedback records for AI analysis."""
    if not feedbacks:
        return "No feedback records available."

    formatted = []
    for fb in feedbacks:
        date = fb.get("date", "Unknown")
        time = fb.get("time", "")
        overall = fb.get("overall", "")
        reasons = fb.get("reason_selected", [])
        reason_text = fb.get("reason_text", "")
        item_fbs = fb.get("item_feedbacks", [])

        entry = f"- {date} {time}: {overall.upper()}"
        if reasons:
            entry += f" | Reasons: {', '.join(reasons)}"
        if reason_text:
            entry += f" | Comment: {reason_text}"
        if item_fbs:
            likes = sum(1 for i in item_fbs if i.get("feedback") == "like")
            dislikes = sum(1 for i in item_fbs if i.get("feedback") == "dislike")
            stars = sum(1 for i in item_fbs if i.get("feedback") == "star")
            if likes or dislikes or stars:
                entry += f" | Items: {likes} liked, {dislikes} disliked, {stars} starred"

        formatted.append(entry)

    return "\n".join(formatted)


async def update_user_profile(telegram_id: str) -> Optional[str]:
    """
    Analyze feedback and update a user's profile.

    Args:
        telegram_id: User's Telegram ID

    Returns:
        Updated profile string, or None if update failed
    """
    user = get_user(telegram_id)
    if not user:
        logger.warning(f"Cannot update profile: user {telegram_id} not found")
        return None

    # Get current profile
    current_profile = get_user_profile(telegram_id)
    if not current_profile:
        logger.info(f"No existing profile for {telegram_id}, skipping update")
        return None

    # Get recent feedbacks
    feedbacks = get_user_feedbacks(telegram_id, days=7)
    if not feedbacks:
        logger.info(f"No feedbacks for {telegram_id}, skipping update")
        return current_profile

    # Format feedbacks for AI
    feedbacks_text = format_feedbacks_for_ai(feedbacks)

    # Load prompt from file
    system_instruction = get_prompt(
        "profile_update.txt",
        current_profile=current_profile,
        recent_feedbacks=feedbacks_text
    )

    prompt = """Based on the current profile and recent feedback history,
generate an updated user profile that better reflects their preferences.

If the feedback suggests significant changes are needed, update accordingly.
If feedback is mostly positive with minor issues, make subtle adjustments.
If there's not enough information to make changes, return the current profile with minimal modifications."""

    try:
        updated_profile = await call_gemini(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.5  # Lower temperature for more consistent updates
        )

        # Save the updated profile
        save_user_profile(telegram_id, updated_profile)

        logger.info(f"Updated profile for user {telegram_id}")
        return updated_profile

    except Exception as e:
        logger.error(f"Failed to update profile for {telegram_id}: {e}")
        return None


async def update_all_user_profiles() -> Dict[str, bool]:
    """
    Update profiles for all users with recent feedback.

    Returns:
        Dict mapping telegram_id to success status
    """
    users = get_users()
    results = {}

    for user in users:
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            continue

        try:
            updated = await update_user_profile(telegram_id)
            results[telegram_id] = updated is not None
        except Exception as e:
            logger.error(f"Error updating profile for {telegram_id}: {e}")
            results[telegram_id] = False

    success_count = sum(1 for v in results.values() if v)
    logger.info(f"Profile update complete: {success_count}/{len(results)} successful")

    return results


async def analyze_feedback_trends(telegram_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Analyze long-term feedback trends for a user.

    Args:
        telegram_id: User's Telegram ID
        days: Number of days to analyze

    Returns:
        Dict with trend analysis
    """
    feedbacks = get_user_feedbacks(telegram_id, days=days)

    if not feedbacks:
        return {
            "total_feedbacks": 0,
            "positive_rate": 0.0,
            "common_issues": [],
            "trend": "neutral",
        }

    positive = sum(1 for fb in feedbacks if fb.get("overall") == "positive")
    negative = len(feedbacks) - positive

    # Collect all reasons
    all_reasons = []
    for fb in feedbacks:
        all_reasons.extend(fb.get("reason_selected", []))
        if fb.get("reason_text"):
            all_reasons.append(fb["reason_text"])

    # Find common issues
    reason_counts = {}
    for reason in all_reasons:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    common_issues = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # Determine trend (compare first half vs second half)
    mid = len(feedbacks) // 2
    if mid > 0:
        first_half_positive = sum(1 for fb in feedbacks[:mid] if fb.get("overall") == "positive")
        second_half_positive = sum(1 for fb in feedbacks[mid:] if fb.get("overall") == "positive")

        first_rate = first_half_positive / mid if mid > 0 else 0
        second_rate = second_half_positive / (len(feedbacks) - mid) if (len(feedbacks) - mid) > 0 else 0

        if second_rate > first_rate + 0.1:
            trend = "improving"
        elif second_rate < first_rate - 0.1:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {
        "total_feedbacks": len(feedbacks),
        "positive_count": positive,
        "negative_count": negative,
        "positive_rate": positive / len(feedbacks) if feedbacks else 0,
        "common_issues": [issue[0] for issue in common_issues],
        "trend": trend,
    }
