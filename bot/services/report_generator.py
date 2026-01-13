"""
Report Generator Service

Generates formatted daily digest reports for Telegram delivery.
Uses a premium text format without emojis.

Reference: Plan specification for report format
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from services.content_filter import categorize_filtered_content, get_ai_summary
from utils.json_storage import get_user_profile

# Separator characters for visual hierarchy
DIVIDER_HEAVY = '━'
DIVIDER_LIGHT = '─'
SEPARATOR_LENGTH = 28

logger = logging.getLogger(__name__)


# Category display names (English, no emoji)
CATEGORY_NAMES = {
    "top_stories": "TOP STORIES",
    "defi": "DeFi",
    "nft": "NFT",
    "layer2": "Layer 2",
    "trading": "Trading",
    "development": "Development",
    "other": "General",
}


def format_top_stories(items: List[Dict[str, Any]]) -> str:
    """Format top stories section with clear visual hierarchy."""
    if not items:
        return ""

    lines = [
        "TOP STORIES",
        ""
    ]

    for i, item in enumerate(items[:3], 1):
        title = item.get("title", "Untitled")[:75]
        summary = item.get("summary", "")[:140]
        source = item.get("source", "Unknown")
        link = item.get("link", "")

        lines.append(f"{i}. {title}")
        if summary:
            lines.append(f"   {summary}")
        lines.append(f"   [{source}]")
        if link:
            lines.append(f"   {link}")
        lines.append("")

    return "\n".join(lines)


def format_category_section(category: str, items: List[Dict[str, Any]]) -> str:
    """Format a category section with compact layout."""
    if not items:
        return ""

    display_name = CATEGORY_NAMES.get(category, category.title())
    lines = [
        f"{display_name} ({len(items)})",
        ""
    ]

    for item in items[:5]:  # Max 5 items per category
        title = item.get("title", "Untitled")[:55]
        source = item.get("source", "")
        link = item.get("link", "")
        lines.append(f"  • {title}")
        if source:
            lines[-1] += f" [{source}]"
        if link:
            lines.append(f"    {link}")

    lines.append("")
    return "\n".join(lines)


def format_metrics_section(
    sources_count: int,
    raw_count: int,
    selected_count: int
) -> str:
    """Format the metrics/statistics section with aligned layout."""
    filter_rate = f"{(selected_count / raw_count * 100):.0f}%" if raw_count > 0 else "N/A"
    time_saved = max(1, raw_count // 30)  # Rough estimate: 2 min per item

    return f"""Stats
  Sources      {sources_count}
  Scanned      {raw_count}
  Selected     {selected_count} ({filter_rate})
  Time saved   ~{time_saved}h
"""


async def generate_daily_report(
    telegram_id: str,
    filtered_items: List[Dict[str, Any]],
    raw_count: int,
    sources_count: int
) -> str:
    """
    Generate the complete daily digest report.

    Args:
        telegram_id: User's Telegram ID
        filtered_items: List of AI-filtered content items
        raw_count: Total number of raw items scanned
        sources_count: Number of sources monitored

    Returns:
        Formatted report string for Telegram
    """
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Get user profile for AI summary
    profile = get_user_profile(telegram_id) or "General Web3 interest"

    # Generate AI summary
    ai_summary = await get_ai_summary(filtered_items, profile)

    # Categorize content
    categories = await categorize_filtered_content(filtered_items)

    # Build report with clear visual hierarchy
    report_parts = []

    # Header with date and summary
    report_parts.append(f"""Web3 Daily Digest
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

{ai_summary}
""")

    # Top stories
    top_stories = categories.pop("top_stories", [])
    if top_stories:
        report_parts.append(format_top_stories(top_stories))
        report_parts.append(DIVIDER_LIGHT * SEPARATOR_LENGTH)
        report_parts.append("")

    # Other categories
    for category, items in categories.items():
        if items:
            report_parts.append(format_category_section(category, items))

    # Divider before metrics
    report_parts.append(DIVIDER_LIGHT * SEPARATOR_LENGTH)
    report_parts.append("")

    # Metrics
    report_parts.append(format_metrics_section(
        sources_count=sources_count,
        raw_count=raw_count,
        selected_count=len(filtered_items)
    ))

    # Footer with feedback prompt
    report_parts.append(DIVIDER_HEAVY * SEPARATOR_LENGTH)
    report_parts.append("")
    report_parts.append("Was this helpful?")

    return "\n".join(report_parts)


def split_report_for_telegram(report: str, max_length: int = 4000) -> List[str]:
    """
    Split a long report into multiple messages for Telegram.

    Telegram has a 4096 character limit per message.

    Args:
        report: Full report text
        max_length: Maximum characters per message

    Returns:
        List of message strings
    """
    if len(report) <= max_length:
        return [report]

    messages = []
    current_message = ""

    # Split by sections (double newlines)
    sections = report.split("\n\n")

    for section in sections:
        if len(current_message) + len(section) + 2 <= max_length:
            if current_message:
                current_message += "\n\n"
            current_message += section
        else:
            if current_message:
                messages.append(current_message)
            current_message = section

    if current_message:
        messages.append(current_message)

    return messages


def generate_empty_report() -> str:
    """Generate a report when no content is available."""
    date_str = datetime.now().strftime("%Y-%m-%d")

    return f"""Web3 Daily Digest
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

No updates matching your preferences today.

Possible reasons:
  • Sources temporarily unavailable
  • Content below relevance threshold
  • Very specific preferences

Check back tomorrow.

{DIVIDER_LIGHT * SEPARATOR_LENGTH}

Tip: Use /settings to adjust preferences.
"""


def generate_preview_report(items: List[Dict[str, Any]]) -> str:
    """
    Generate a preview/sample report for new users.

    Args:
        items: Sample content items

    Returns:
        Formatted preview report
    """
    date_str = datetime.now().strftime("%Y-%m-%d")

    lines = [
        "SAMPLE PREVIEW",
        date_str,
        DIVIDER_HEAVY * SEPARATOR_LENGTH,
        "",
        "This is how your daily digest will look.",
        "",
        "TOP STORIES",
        ""
    ]

    for i, item in enumerate(items[:3], 1):
        title = item.get("title", "Sample headline")[:55]
        lines.append(f"{i}. {title}")
        lines.append("   Brief summary of the article...")
        lines.append("")

    lines.extend([
        DIVIDER_LIGHT * SEPARATOR_LENGTH,
        "",
        "DeFi (3)",
        "  • Sample DeFi news [Source]",
        "  • Another update [Source]",
        "",
        DIVIDER_LIGHT * SEPARATOR_LENGTH,
        "",
        "Stats",
        "  Sources      50+",
        "  Scanned      200+",
        "  Selected     15",
        "  Time saved   ~2h",
        "",
        DIVIDER_HEAVY * SEPARATOR_LENGTH,
        "",
        "Your real digest arrives tomorrow at 9:00 AM."
    ])

    return "\n".join(lines)
