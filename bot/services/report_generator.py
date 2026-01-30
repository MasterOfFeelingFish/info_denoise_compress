"""
Report Generator Service

Generates formatted daily digest reports for Telegram delivery.
Uses a premium text format without emojis.
Supports multiple languages based on user profile.

Reference: Plan specification for report format
"""
import html
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from services.content_filter import categorize_filtered_content, get_ai_summary, translate_text, translate_content, _extract_user_language
from utils.json_storage import get_user_profile
from config import MAX_DIGEST_ITEMS

# Separator characters for visual hierarchy
DIVIDER_HEAVY = '━'
DIVIDER_LIGHT = '─'
SEPARATOR_LENGTH = 28

logger = logging.getLogger(__name__)


def is_summary_duplicate(title: str, summary: str) -> bool:
    """
    判断摘要是否与标题内容重复。
    
    常见情况：
    - BlockBeats 等源的摘要以标题内容开头
    - 摘要直接复制标题
    - 摘要以"据xxx，[标题内容]..."开头
    
    Args:
        title: 标题文本
        summary: 摘要文本
        
    Returns:
        True 如果认为是重复的，否则 False
    """
    if not title or not summary:
        return False
    
    # 规范化：去除常见前缀如 "BlockBeats 消息，1月26日，"
    summary_clean = re.sub(
        r'^(BlockBeats\s*消息[，,]?\s*\d+\s*月\s*\d+\s*日[，,]?\s*'
        r'|据.*?[，,]\s*'
        r'|消息[，,]\s*'
        r'|【.*?】\s*'
        r'|\d+\s*月\s*\d+\s*日[，,]?\s*)',
        '', 
        summary,
        flags=re.IGNORECASE
    ).strip()
    
    title_clean = title.strip().rstrip('。，.!！?？')
    
    # 如果标题很短（少于5个字符），不做去重处理
    if len(title_clean) < 5:
        return False
    
    # 如果摘要核心内容以标题开头，认为是重复
    if summary_clean.startswith(title_clean):
        return True
    
    # 如果标题是摘要的子串（在前50字内），且占比超过 80%
    if title_clean in summary_clean[:len(title_clean) + 30]:
        # 检查重复比例
        overlap_ratio = len(title_clean) / len(summary_clean) if summary_clean else 0
        if overlap_ratio > 0.6:
            return True
    
    # 检查标题和摘要的相似度（简单 Jaccard 相似度）
    title_chars = set(title_clean)
    summary_start_chars = set(summary_clean[:len(title_clean) + 20])
    
    if title_chars and summary_start_chars:
        intersection = len(title_chars & summary_start_chars)
        union = len(title_chars | summary_start_chars)
        similarity = intersection / union if union > 0 else 0
        
        # 如果相似度超过 85%，认为是重复
        if similarity > 0.85:
            return True
    
    return False


# Localized strings - extensible for any language
LOCALE_STRINGS = {
    "zh": {
        "title": "Web3 每日简报",
        "must_read": "今日必看",
        "top_stories": "今日必看",
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
        # New strings for item display
        "reason_prefix": "💡 ",
        "source_prefix": "来源: ",
        "btn_view_original": "查看原文",
        "btn_open_link": "打开链接",
        "btn_like": "👍",
        "btn_not_interested": "不感兴趣",
    },
    "en": {
        "title": "Web3 Daily Digest",
        "must_read": "MUST READ",
        "top_stories": "TOP STORIES",
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
        # New strings for item display
        "reason_prefix": "💡 ",
        "source_prefix": "Source: ",
        "btn_view_original": "View Original",
        "btn_like": "👍",
        "btn_not_interested": "Not interested",
    },
    "ja": {
        "title": "Web3 デイリーダイジェスト",
        "must_read": "今日の必読",
        "top_stories": "今日の必読",
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
        # New strings for item display
        "reason_prefix": "💡 ",
        "source_prefix": "ソース: ",
        "btn_view_original": "原文を見る",
        "btn_open_link": "リンクを開く",
        "btn_like": "👍",
        "btn_not_interested": "興味なし",
    },
    "ko": {
        "title": "Web3 데일리 다이제스트",
        "must_read": "필독",
        "top_stories": "필독",
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
        # New strings for item display
        "reason_prefix": "💡 ",
        "source_prefix": "출처: ",
        "btn_view_original": "원문 보기",
        "btn_open_link": "링크 열기",
        "btn_like": "👍",
        "btn_not_interested": "관심없음",
    },
}


# Language code to full name mapping (for translation API)
LANG_CODE_TO_NAME = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
    "vi": "Vietnamese",
    "th": "Thai",
}


def get_translation_language(lang_code: str) -> str:
    """Convert language code to full language name for translation API."""
    return LANG_CODE_TO_NAME.get(lang_code, "Chinese")


# Category display names per language
CATEGORY_NAMES = {
    "zh": {
        "must_read": "今日必看",
        "macro_insights": "行业大局",
        "recommended": "推荐",
        "other": "其他",
    },
    "en": {
        "must_read": "MUST READ",
        "macro_insights": "Industry Context",
        "recommended": "Recommended",
        "other": "Other",
    },
    "ja": {
        "must_read": "今日の必読",
        "macro_insights": "業界概況",
        "recommended": "おすすめ",
        "other": "その他",
    },
    "ko": {
        "must_read": "필독",
        "macro_insights": "업계 동향",
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


def format_category_section(category: str, items: List[Dict[str, Any]], lang: str = "zh", max_items: int = None) -> str:
    """Format a category section with compact layout.
    
    Args:
        category: Category name
        items: List of items in this category
        lang: Language for display
        max_items: Max items to display (None = show all)
    """
    if not items:
        return ""

    category_names = get_category_names(lang)
    display_name = category_names.get(category, category.title())
    
    # Apply max_items limit if specified
    display_items = items[:max_items] if max_items else items
    
    lines = [
        f"{display_name} ({len(display_items)})",
        ""
    ]

    for item in display_items:
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

    # Generate AI summary (in English)
    ai_summary = await get_ai_summary(filtered_items, profile)
    
    # === Final output translation (all at once) ===
    target_language = _extract_user_language(profile)
    if target_language != "English":
        # Translate both items and summary before output
        filtered_items = await translate_content(filtered_items, target_language)
        ai_summary = await translate_text(ai_summary, target_language)

    # Categorize content (after translation)
    categories = await categorize_filtered_content(filtered_items)

    # Build report with clear visual hierarchy
    report_parts = []

    # Header with date and summary
    report_parts.append(f"""{locale["title"]}
{date_str}
{DIVIDER_HEAVY * SEPARATOR_LENGTH}

{ai_summary}
""")

    # Top stories (separate from quota)
    top_stories = categories.pop("top_stories", [])
    if top_stories:
        report_parts.append(format_top_stories(top_stories, lang))
        report_parts.append(DIVIDER_LIGHT * SEPARATOR_LENGTH)
        report_parts.append("")

    # Dynamic allocation for other categories
    # Total quota for non-top-stories items
    total_quota = MAX_DIGEST_ITEMS
    
    # Get categories with items
    active_categories = {k: v for k, v in categories.items() if v}
    
    if active_categories:
        # Calculate total items across all categories
        total_items = sum(len(items) for items in active_categories.values())
        
        # Allocate proportionally, with minimum 1 per category
        category_limits = {}
        remaining_quota = total_quota
        
        for category, items in active_categories.items():
            if total_items > 0:
                # Proportional allocation
                proportion = len(items) / total_items
                allocated = max(1, int(proportion * total_quota))
                # Don't allocate more than available items
                category_limits[category] = min(allocated, len(items))
            else:
                category_limits[category] = len(items)
        
        # Adjust if over quota
        while sum(category_limits.values()) > total_quota:
            # Reduce from largest category
            largest = max(category_limits, key=category_limits.get)
            if category_limits[largest] > 1:
                category_limits[largest] -= 1
            else:
                break
        
        # Render categories with dynamic limits
        for category, items in active_categories.items():
            max_items = category_limits.get(category, len(items))
            report_parts.append(format_category_section(category, items, lang, max_items))

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

    New format:
    🔴 1. Title (clickable)
    Summary text...
    💡 Recommendation reason
    Source: @author

    Args:
        item: Content item dict
        index: Item index number
        lang: Language code

    Returns:
        Formatted message string
    """
    locale = get_locale(lang)
    
    title = item.get("title", "Untitled")
    summary = item.get("summary", "")
    link = item.get("link", "")
    reason = item.get("reason", "")
    source = item.get("source", "")
    author = item.get("author", "")  # Twitter author if available
    section = item.get("section", "other")

    # Priority indicator based on section
    if section == "must_read":
        priority = "🔴"
    elif section == "macro_insights":
        priority = "🟠"
    else:
        priority = "🔵"

    # Escape HTML special characters to prevent format breaking
    title_escaped = html.escape(title)
    summary_escaped = html.escape(summary) if summary else ""
    reason_escaped = html.escape(reason) if reason else ""

    # Title is now plain text (no hyperlink)
    # Users must use "查看原文" button to access original content
    # This ensures all traffic goes through the monitored button
    title_html = title_escaped

    lines = [f"{priority} <b>{index}. {title_html}</b>"]

    # Add summary if present and not duplicate of title
    # Use original text (not escaped) for duplicate detection
    if summary_escaped and not is_summary_duplicate(title, summary):
        lines.append(f"{summary_escaped}")

    # Add recommendation reason (user-centric explanation)
    if reason_escaped:
        reason_prefix = locale.get("reason_prefix", "💡 ")
        lines.append(f"{reason_prefix}{reason_escaped}")

    # Note: Source line removed per user feedback - considered redundant

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
        Tuple of (header_message, list of (item_message, item_id, item_url) tuples)
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    locale = get_locale(lang)
    category_names = get_category_names(lang)

    # Group items by section (4 categories now)
    must_read = [item for item in filtered_items if item.get("section") == "must_read"]
    macro_insights = [item for item in filtered_items if item.get("section") == "macro_insights"]
    recommended = [item for item in filtered_items if item.get("section") == "recommended"]
    other = [item for item in filtered_items if item.get("section") == "other"]

    # Fallback for legacy format (importance-based)
    if not must_read and not macro_insights and not recommended and not other:
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
    # Each item is (message, item_id, item_url) tuple
    item_messages = []
    item_index = 1

    # Section 1: Must Read (今日必看) - Major events regardless of user preference
    if must_read:
        section_name = category_names.get("must_read", "MUST READ")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_must_read", ""))

        for item in must_read:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_url = item.get("link", "")
            item_messages.append((msg, item_id, item_url))
            item_index += 1

    # Section 2: Macro Insights (行业大局) - Industry context, implicit needs
    if macro_insights:
        section_name = category_names.get("macro_insights", "Industry Context")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_macro_insights", ""))

        for item in macro_insights:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_url = item.get("link", "")
            item_messages.append((msg, item_id, item_url))
            item_index += 1

    # Section 3: Recommended (推荐) - Matching user preferences
    if recommended:
        section_name = category_names.get("recommended", "Recommended")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_recommended", ""))

        for item in recommended:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_url = item.get("link", "")
            item_messages.append((msg, item_id, item_url))
            item_index += 1

    # Section 4: Other (其他)
    if other:
        section_name = category_names.get("other", "Other")
        section_header = f"\n<b>{DIVIDER_LIGHT * 8} {section_name} {DIVIDER_LIGHT * 8}</b>\n"
        item_messages.append((section_header, "section_other", ""))

        for item in other:
            msg = format_single_item(item, item_index, lang)
            item_id = item.get("id", f"item_{item_index}")
            item_url = item.get("link", "")
            item_messages.append((msg, item_id, item_url))
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
