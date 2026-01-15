"""
Report Generator Service

Generates formatted daily digest reports for Telegram delivery.
Uses a premium text format without emojis.
Supports multiple languages based on user profile.

Reference: Plan specification for report format
"""
import html
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


# Localized strings - extensible for any language
LOCALE_STRINGS = {
    "zh": {
        "title": "Web3 每日简报",
        "must_read": "今日必看",
        "recommended": "推荐",
        "stats": "统计",
        "sources": "信息源",
        "scanned": "扫描条数",
        "selected": "精选条数",
        "time_saved": "节省时间",
        "helpful_prompt": "这份简报有帮助吗？",
        "no_content": "今天没有符合你偏好的更新。",
        "possible_reasons": "可能原因：",
        "reason_1": "信息源暂时不可用",
        "reason_2": "内容相关度不够",
        "reason_3": "偏好设置较为具体",
        "check_tomorrow": "明天再看看。",
        "tip": "提示：使用 /settings 调整偏好。",
        "sample_preview": "示例预览",
        "preview_desc": "以下是你每日简报的样式预览。",
        "preview_footer": "你的真实简报将于明天 9:00 推送。",
    },
    "en": {
        "title": "Web3 Daily Digest",
        "must_read": "MUST READ",
        "recommended": "Recommended",
        "stats": "Stats",
        "sources": "Sources",
        "scanned": "Scanned",
        "selected": "Selected",
        "time_saved": "Time saved",
        "helpful_prompt": "Was this helpful?",
        "no_content": "No updates matching your preferences today.",
        "possible_reasons": "Possible reasons:",
        "reason_1": "Sources temporarily unavailable",
        "reason_2": "Content below relevance threshold",
        "reason_3": "Very specific preferences",
        "check_tomorrow": "Check back tomorrow.",
        "tip": "Tip: Use /settings to adjust preferences.",
        "sample_preview": "SAMPLE PREVIEW",
        "preview_desc": "This is how your daily digest will look.",
        "preview_footer": "Your real digest arrives tomorrow at 9:00 AM.",
    },
    "ja": {
        "title": "Web3 デイリーダイジェスト",
        "must_read": "今日の必読",
        "recommended": "おすすめ",
        "stats": "統計",
        "sources": "ソース",
        "scanned": "スキャン",
        "selected": "選択",
        "time_saved": "節約時間",
        "helpful_prompt": "このダイジェストは役に立ちましたか？",
        "no_content": "今日はお好みに合う更新がありません。",
        "possible_reasons": "考えられる理由：",
        "reason_1": "ソースが一時的に利用不可",
        "reason_2": "関連性が低いコンテンツ",
        "reason_3": "非常に具体的な設定",
        "check_tomorrow": "明日また確認してください。",
        "tip": "ヒント：/settings で設定を調整できます。",
        "sample_preview": "サンプルプレビュー",
        "preview_desc": "これがデイリーダイジェストの表示例です。",
        "preview_footer": "実際のダイジェストは明日9:00に届きます。",
    },
    "ko": {
        "title": "Web3 데일리 다이제스트",
        "must_read": "필독",
        "recommended": "추천",
        "stats": "통계",
        "sources": "소스",
        "scanned": "스캔",
        "selected": "선택",
        "time_saved": "절약 시간",
        "helpful_prompt": "이 다이제스트가 도움이 되었나요?",
        "no_content": "오늘은 맞춤 업데이트가 없습니다.",
        "possible_reasons": "가능한 이유:",
        "reason_1": "소스를 일시적으로 사용할 수 없음",
        "reason_2": "관련성이 낮은 콘텐츠",
        "reason_3": "매우 구체적인 설정",
        "check_tomorrow": "내일 다시 확인하세요.",
        "tip": "팁: /settings로 설정을 조정하세요.",
        "sample_preview": "샘플 미리보기",
        "preview_desc": "데일리 다이제스트는 이렇게 보입니다.",
        "preview_footer": "실제 다이제스트는 내일 오전 9시에 도착합니다.",
    },
}


# Category display names per language
CATEGORY_NAMES = {
    "zh": {
        "must_read": "今日必看",
        "recommended": "推荐",
        "other": "其他",
    },
    "en": {
        "must_read": "MUST READ",
        "recommended": "Recommended",
        "other": "Other",
    },
    "ja": {
        "must_read": "今日の必読",
        "recommended": "おすすめ",
        "other": "その他",
    },
    "ko": {
        "must_read": "필독",
        "recommended": "추천",
        "other": "기타",
    },
}


# Language detection patterns
LANGUAGE_MARKERS = {
    "zh": ["中文", "简体", "繁體", "chinese"],
    "en": ["english", "英文", "英语"],
    "ja": ["日本語", "japanese", "日语"],
    "ko": ["한국어", "korean", "韩语", "韓語"],
    "ru": ["русский", "russian", "俄语"],
    "es": ["español", "spanish", "西班牙语"],
    "fr": ["français", "french", "法语"],
    "de": ["deutsch", "german", "德语"],
    "pt": ["português", "portuguese", "葡萄牙语"],
    "ar": ["العربية", "arabic", "阿拉伯语"],
    "vi": ["tiếng việt", "vietnamese", "越南语"],
    "th": ["ไทย", "thai", "泰语"],
}


def detect_user_language(profile: str) -> str:
    """
    Detect user's preferred language from profile.
    Returns language code (zh, en, ja, ko, etc.) or 'zh' as default.
    """
    if not profile:
        return "zh"  # Default to Chinese

    profile_lower = profile.lower()

    # Check for explicit language markers
    for lang_code, markers in LANGUAGE_MARKERS.items():
        for marker in markers:
            if marker.lower() in profile_lower:
                return lang_code

    # Check for language field pattern like "[用户语言] xxx" or "[User Language] xxx"
    import re
    lang_pattern = r'\[(?:用户语言|user language)\]\s*[:\-]?\s*(\w+)'
    match = re.search(lang_pattern, profile_lower)
    if match:
        detected = match.group(1).lower()
        # Map common names to codes
        name_to_code = {
            "chinese": "zh", "中文": "zh", "简体中文": "zh",
            "english": "en", "英文": "en",
            "japanese": "ja", "日本語": "ja", "日语": "ja",
            "korean": "ko", "한국어": "ko", "韩语": "ko",
            "russian": "ru", "русский": "ru",
            "spanish": "es", "español": "es",
            "french": "fr", "français": "fr",
            "german": "de", "deutsch": "de",
        }
        if detected in name_to_code:
            return name_to_code[detected]

    # Detect by character ranges
    for char in profile:
        # Chinese characters
        if '\u4e00' <= char <= '\u9fff':
            return "zh"
        # Japanese Hiragana/Katakana
        if '\u3040' <= char <= '\u30ff':
            return "ja"
        # Korean Hangul
        if '\uac00' <= char <= '\ud7af' or '\u1100' <= char <= '\u11ff':
            return "ko"
        # Cyrillic (Russian, etc.)
        if '\u0400' <= char <= '\u04ff':
            return "ru"
        # Arabic
        if '\u0600' <= char <= '\u06ff':
            return "ar"
        # Thai
        if '\u0e00' <= char <= '\u0e7f':
            return "th"

    return "zh"  # Default to Chinese


def get_locale(lang: str) -> dict:
    """Get locale strings for a language, with English fallback for unsupported languages."""
    if lang in LOCALE_STRINGS:
        return LOCALE_STRINGS[lang]
    # For unsupported languages, use English as fallback
    return LOCALE_STRINGS["en"]


def get_category_names(lang: str) -> dict:
    """Get category names for a language, with English fallback."""
    if lang in CATEGORY_NAMES:
        return CATEGORY_NAMES[lang]
    return CATEGORY_NAMES["en"]


def format_top_stories(items: List[Dict[str, Any]], lang: str = "zh") -> str:
    """Format top stories section with clear visual hierarchy."""
    if not items:
        return ""

    locale = get_locale(lang)

    lines = [
        locale["top_stories"],
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
        if link:
            # HTML format: <a href="url">text</a>
            lines.append(f'   <a href="{link}">{source}</a>')
        else:
            lines.append(f"   [{source}]")
        lines.append("")

    return "\n".join(lines)


def format_category_section(category: str, items: List[Dict[str, Any]], lang: str = "zh") -> str:
    """Format a category section with compact layout."""
    if not items:
        return ""

    category_names = get_category_names(lang)
    display_name = category_names.get(category, category.title())
    lines = [
        f"{display_name} ({len(items)})",
        ""
    ]

    for item in items[:5]:  # Max 5 items per category
        title = item.get("title", "Untitled")[:55]
        source = item.get("source", "")
        link = item.get("link", "")

        if link:
            # HTML format for clickable source link
            lines.append(f'  • {title} <a href="{link}">{source}</a>')
        elif source:
            lines.append(f"  • {title} [{source}]")
        else:
            lines.append(f"  • {title}")

    lines.append("")
    return "\n".join(lines)


def format_metrics_section(
    sources_count: int,
    raw_count: int,
    selected_count: int,
    lang: str = "zh"
) -> str:
    """Format the metrics/statistics section with aligned layout."""
    locale = get_locale(lang)
    filter_rate = f"{(selected_count / raw_count * 100):.0f}%" if raw_count > 0 else "N/A"
    time_saved = max(1, raw_count // 30)  # Rough estimate: 2 min per item

    return f"""{locale["stats"]}
  {locale["sources"]}      {sources_count}
  {locale["scanned"]}      {raw_count}
  {locale["selected"]}     {selected_count} ({filter_rate})
  {locale["time_saved"]}   ~{time_saved}h
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

    # Get user profile for AI summary and language detection
    profile = get_user_profile(telegram_id) or "General Web3 interest"

    # Detect user language
    lang = detect_user_language(profile)
    locale = get_locale(lang)

    # Generate AI summary
    ai_summary = await get_ai_summary(filtered_items, profile)

    # Categorize content
    categories = await categorize_filtered_content(filtered_items)

    # Build report with clear visual hierarchy
    report_parts = []

    # Header with date and summary
    report_parts.append(f"""{locale["title"]}
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

{ai_summary}
""")

    # Top stories
    top_stories = categories.pop("top_stories", [])
    if top_stories:
        report_parts.append(format_top_stories(top_stories, lang))
        report_parts.append(DIVIDER_LIGHT * SEPARATOR_LENGTH)
        report_parts.append("")

    # Other categories
    for category, items in categories.items():
        if items:
            report_parts.append(format_category_section(category, items, lang))

    # Divider before metrics
    report_parts.append(DIVIDER_LIGHT * SEPARATOR_LENGTH)
    report_parts.append("")

    # Metrics
    report_parts.append(format_metrics_section(
        sources_count=sources_count,
        raw_count=raw_count,
        selected_count=len(filtered_items),
        lang=lang
    ))

    # Footer with feedback prompt
    report_parts.append(DIVIDER_HEAVY * SEPARATOR_LENGTH)
    report_parts.append("")
    report_parts.append(locale["helpful_prompt"])

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


def format_single_item(item: Dict[str, Any], index: int, lang: str = "zh") -> str:
    """
    Format a single news item for individual message with feedback buttons.

    Args:
        item: Content item dict
        index: Item index number
        lang: Language code

    Returns:
        Formatted message string
    """
    title = item.get("title", "Untitled")
    summary = item.get("summary", "")
    link = item.get("link", "")
    importance = item.get("importance", "medium")

    # Priority indicator
    priority = "🔴" if importance == "high" else "🔵"

    # Escape HTML special characters to prevent format breaking
    title_escaped = html.escape(title)
    summary_escaped = html.escape(summary) if summary else ""

    # Make title clickable if link exists
    if link:
        # Escape link URL for HTML attribute safety
        link_escaped = html.escape(link, quote=True)
        title_html = f'<a href="{link_escaped}">{title_escaped}</a>'
    else:
        title_html = title_escaped

    lines = [f"{priority} <b>{index}. {title_html}</b>"]

    if summary_escaped:
        lines.append(f"{summary_escaped}")

    # Source line removed - link is now in title

    return "\n".join(lines)


def generate_summary_header(
    date_str: str,
    ai_summary: str,
    sources_count: int,
    raw_count: int,
    selected_count: int,
    lang: str = "zh"
) -> str:
    """
    Generate the summary header message (without individual items).

    Args:
        date_str: Date string
        ai_summary: AI-generated summary
        sources_count: Number of sources
        raw_count: Raw items count
        selected_count: Selected items count
        lang: Language code

    Returns:
        Formatted header message
    """
    locale = get_locale(lang)
    filter_rate = f"{(selected_count / raw_count * 100):.0f}%" if raw_count > 0 else "N/A"

    return f"""<b>{locale["title"]}</b>
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

{ai_summary}

{DIVIDER_LIGHT * SEPARATOR_LENGTH}

<b>{locale["stats"]}</b>
  {locale["sources"]}: {sources_count}
  {locale["scanned"]}: {raw_count}
  {locale["selected"]}: {selected_count} ({filter_rate})

{DIVIDER_HEAVY * SEPARATOR_LENGTH}
"""


def prepare_digest_messages(
    filtered_items: List[Dict[str, Any]],
    ai_summary: str,
    sources_count: int,
    raw_count: int,
    lang: str = "zh"
) -> tuple:
    """
    Prepare digest as separate messages: header + individual items with hierarchy.

    Items are grouped by section: must_read, recommended, other.

    Args:
        filtered_items: List of filtered content items with 'section' field
        ai_summary: AI-generated summary
        sources_count: Number of sources
        raw_count: Raw items count
        lang: Language code

    Returns:
        Tuple of (header_message, list of (item_message, item_id) tuples)
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    locale = get_locale(lang)
    category_names = get_category_names(lang)

    # Group items by section
    must_read = [item for item in filtered_items if item.get("section") == "must_read"]
    recommended = [item for item in filtered_items if item.get("section") == "recommended"]
    other = [item for item in filtered_items if item.get("section") == "other"]

    # Fallback for legacy format (importance-based)
    if not must_read and not recommended and not other:
        must_read = [item for item in filtered_items if item.get("importance") == "high"]
        other = [item for item in filtered_items if item.get("importance") != "high"]

    # Generate header with stats
    filter_rate = f"{(len(filtered_items) / raw_count * 100):.0f}%" if raw_count > 0 else "N/A"

    header = f"""<b>{locale["title"]}</b>
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

{ai_summary}

{DIVIDER_LIGHT * SEPARATOR_LENGTH}

<b>{locale["stats"]}</b>
  {locale["sources"]}: {sources_count}
  {locale["scanned"]}: {raw_count}
  {locale["selected"]}: {len(filtered_items)} ({filter_rate})

{DIVIDER_HEAVY * SEPARATOR_LENGTH}
"""

    # Generate individual item messages with hierarchy
    item_messages = []
    item_index = 1

    # Section 1: Must Read (今日必看) - Major events regardless of user preference
    if must_read:
        section_name = category_names.get("must_read", "MUST READ")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_must_read"))

        for item in must_read:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_messages.append((msg, item_id))
            item_index += 1

    # Section 2: Recommended (推荐) - Matching user preferences
    if recommended:
        section_name = category_names.get("recommended", "Recommended")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_recommended"))

        for item in recommended:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_messages.append((msg, item_id))
            item_index += 1

    # Section 3: Other (其他)
    if other:
        section_name = category_names.get("other", "Other")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_other"))

        for item in other:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_messages.append((msg, item_id))
            item_index += 1

    return header, item_messages


def generate_empty_report(lang: str = "zh") -> str:
    """Generate a report when no content is available."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    locale = get_locale(lang)

    return f"""{locale["title"]}
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

{locale["no_content"]}

{locale["possible_reasons"]}
  • {locale["reason_1"]}
  • {locale["reason_2"]}
  • {locale["reason_3"]}

{locale["check_tomorrow"]}

{DIVIDER_LIGHT * SEPARATOR_LENGTH}

{locale["tip"]}
"""


def generate_preview_report(items: List[Dict[str, Any]], lang: str = "zh") -> str:
    """
    Generate a preview/sample report for new users.

    Args:
        items: Sample content items
        lang: Language code

    Returns:
        Formatted preview report
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    locale = get_locale(lang)
    category_names = get_category_names(lang)

    lines = [
        f"【{locale['sample_preview']}】",
        date_str,
        DIVIDER_HEAVY * SEPARATOR_LENGTH,
        "",
        locale["preview_desc"],
        "",
        DIVIDER_LIGHT * SEPARATOR_LENGTH,
        "",
        f"▎{category_names['must_read']}",
        ""
    ]

    # Sample must-read items
    must_read_samples = [
        "ETH 突破 $5000，创历史新高" if lang == "zh" else "ETH breaks $5000, new ATH",
        "SEC 批准现货以太坊 ETF" if lang == "zh" else "SEC approves spot ETH ETF",
    ]
    for i, title in enumerate(must_read_samples, 1):
        lines.append(f"  {i}. {title}")
    lines.append("")

    lines.extend([
        DIVIDER_LIGHT * SEPARATOR_LENGTH,
        "",
        f"▎{category_names['recommended']}",
        ""
    ])

    # Sample recommended items
    recommended_samples = [
        "Uniswap V4 发布新治理提案" if lang == "zh" else "Uniswap V4 governance proposal",
        "Arbitrum 生态 TVL 突破 200 亿" if lang == "zh" else "Arbitrum TVL exceeds $20B",
        "新 DeFi 协议融资 5000 万美元" if lang == "zh" else "New DeFi protocol raises $50M",
    ]
    for i, title in enumerate(recommended_samples, len(must_read_samples) + 1):
        lines.append(f"  {i}. {title}")
    lines.append("")

    lines.extend([
        DIVIDER_LIGHT * SEPARATOR_LENGTH,
        "",
        f"▎{category_names['other']}",
        ""
    ])

    # Sample other items
    other_samples = [
        "Polygon 发布开发者工具更新" if lang == "zh" else "Polygon developer tools update",
        "Chainlink 新增数据喂价" if lang == "zh" else "Chainlink adds new price feeds",
    ]
    total_prev = len(must_read_samples) + len(recommended_samples)
    for i, title in enumerate(other_samples, total_prev + 1):
        lines.append(f"  {i}. {title}")
    lines.append("")

    lines.extend([
        DIVIDER_LIGHT * SEPARATOR_LENGTH,
        "",
        f"{locale['stats']}",
        f"  {locale['sources']}      10",
        f"  {locale['scanned']}      150",
        f"  {locale['selected']}     20 (13%)",
        f"  {locale['time_saved']}   ~2h",
        "",
        DIVIDER_HEAVY * SEPARATOR_LENGTH,
        "",
        locale["preview_footer"]
    ])

    return "\n".join(lines)
