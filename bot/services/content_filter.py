"""
AI Content Filter Service

Uses Gemini 3 to intelligently filter content based on user profiles.
Selects relevant items from raw content and ranks by importance.

Reference: Plan specification for content filtering with Gemini 3
"""
import json
import logging
from typing import List, Dict, Any, Optional

from services.gemini import call_gemini_json, call_gemini
from utils.json_storage import get_user_profile, get_user_feedbacks
from utils.prompt_loader import get_prompt

logger = logging.getLogger(__name__)


DEFAULT_PROFILE = """This is a new user who hasn't set specific preferences yet.

[Focus Areas]
- General Web3 news and updates
- Major protocol and ecosystem developments
- Market-moving news and announcements

[Content Preferences]
- Balanced mix of news and analysis
- Moderate volume (10-15 items per day)

[Sources]
- No specific preferences yet"""


def summarize_feedbacks(feedbacks: List[Dict[str, Any]]) -> str:
    """Summarize recent user feedbacks for AI context."""
    if not feedbacks:
        return "No feedback history available."

    positive_count = 0
    negative_count = 0
    reasons = []

    for fb in feedbacks:
        if fb.get("overall") == "positive":
            positive_count += 1
        elif fb.get("overall") == "negative":
            negative_count += 1
            if fb.get("reason_selected"):
                reasons.extend(fb["reason_selected"])
            if fb.get("reason_text"):
                reasons.append(fb["reason_text"])

    summary_parts = [
        f"Recent 7 days: {positive_count} positive, {negative_count} negative ratings."
    ]

    if reasons:
        unique_reasons = list(set(reasons))[:5]
        summary_parts.append(f"Main concerns: {', '.join(unique_reasons)}")

    return " ".join(summary_parts)


async def filter_content_for_user(
    telegram_id: str,
    raw_content: List[Dict[str, Any]],
    max_items: int = 20
) -> List[Dict[str, Any]]:
    """
    Filter raw content based on user profile using AI.

    Args:
        telegram_id: User's Telegram ID
        raw_content: List of raw content items to filter
        max_items: Maximum number of items to return

    Returns:
        List of filtered and ranked content items
    """
    if not raw_content:
        logger.warning(f"No content to filter for user {telegram_id}")
        return []

    # Get user profile
    profile = get_user_profile(telegram_id)
    if not profile:
        logger.info(f"No profile found for {telegram_id}, using default")
        profile = DEFAULT_PROFILE

    # Get feedback history
    feedbacks = get_user_feedbacks(telegram_id, days=7)
    feedback_summary = summarize_feedbacks(feedbacks)

    # Prepare content list for AI
    content_for_ai = []
    for item in raw_content[:100]:  # Limit to 100 items for API context
        content_for_ai.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "summary": item.get("summary", "")[:200],
            "source": item.get("source", ""),
            "link": item.get("link", ""),
            "category": item.get("category", ""),
        })

    # Build prompt
    system_instruction = get_prompt(
        "filtering.txt",
        user_profile=profile,
        feedback_summary=feedback_summary
    )

    prompt = f"""## Today's Content to Filter (Total: {len(content_for_ai)} items)

{json.dumps(content_for_ai, ensure_ascii=False, indent=2)}

Please select the most relevant items for this user (max {max_items} items)."""

    try:
        # Call Gemini for filtering
        filtered_items = await call_gemini_json(
            prompt=prompt,
            system_instruction=system_instruction
        )

        if not isinstance(filtered_items, list):
            logger.error(f"Unexpected response format: {type(filtered_items)}")
            # Return fallback with consistent structure
            return [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "summary": item.get("summary", "")[:100],
                    "source": item.get("source"),
                    "link": item.get("link"),
                    "importance": "medium",
                    "reason": "Fallback: invalid AI response"
                }
                for item in raw_content[:max_items]
            ]

        logger.info(f"AI selected {len(filtered_items)} items for user {telegram_id}")
        return filtered_items[:max_items]

    except Exception as e:
        logger.error(f"AI filtering failed for {telegram_id}: {e}")
        # Fallback: return first N items unfiltered
        return [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "summary": item.get("summary", "")[:100],
                "source": item.get("source"),
                "link": item.get("link"),
                "importance": "medium",
                "reason": "Fallback selection"
            }
            for item in raw_content[:max_items]
        ]


async def categorize_filtered_content(
    filtered_items: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorize filtered content into sections for the report.

    Args:
        filtered_items: List of filtered content items

    Returns:
        Dict with categories as keys and item lists as values
    """
    categories = {
        "top_stories": [],
        "defi": [],
        "nft": [],
        "layer2": [],
        "trading": [],
        "development": [],
        "other": []
    }

    # Separate high importance items as top stories
    for item in filtered_items:
        if item.get("importance") == "high" and len(categories["top_stories"]) < 3:
            categories["top_stories"].append(item)
        else:
            # Simple keyword-based categorization
            title_lower = (item.get("title", "") + " " + item.get("summary", "")).lower()

            if any(kw in title_lower for kw in ["defi", "lending", "yield", "liquidity", "swap"]):
                categories["defi"].append(item)
            elif any(kw in title_lower for kw in ["nft", "opensea", "blur", "collection"]):
                categories["nft"].append(item)
            elif any(kw in title_lower for kw in ["layer2", "l2", "arbitrum", "optimism", "zksync", "rollup"]):
                categories["layer2"].append(item)
            elif any(kw in title_lower for kw in ["trade", "trading", "long", "short", "whale"]):
                categories["trading"].append(item)
            elif any(kw in title_lower for kw in ["developer", "github", "upgrade", "fork", "code"]):
                categories["development"].append(item)
            else:
                categories["other"].append(item)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


async def get_ai_summary(
    items: List[Dict[str, Any]],
    user_profile: str
) -> str:
    """
    Generate a brief AI summary of today's key themes.

    Args:
        items: List of filtered items
        user_profile: User's profile for context

    Returns:
        Brief summary text (2-3 sentences)
    """
    if not items:
        return "No significant updates today."

    titles = [item.get("title", "") for item in items[:10]]

    # Load prompt from file
    prompt = get_prompt(
        "report.txt",
        user_profile=user_profile[:200],
        headlines=json.dumps(titles, ensure_ascii=False)
    )

    try:
        summary = await call_gemini(
            prompt=prompt,
            temperature=0.7
        )
        return summary.strip()
    except Exception as e:
        logger.error(f"Failed to generate AI summary: {e}")
        return "Today's digest covers the latest Web3 developments across your areas of interest."
