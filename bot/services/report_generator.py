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
from services.language_service import get_user_language as get_lang_from_storage, get_language_native_name
from utils.json_storage import get_user_profile
from config import MAX_DIGEST_ITEMS

# Separator characters for visual hierarchy
DIVIDER_HEAVY = '━'
DIVIDER_LIGHT = '─'
SEPARATOR_LENGTH = 28

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """
    规范化文本：去除标点、多余空白、统一大小写。
    同时处理中英文混合内容。
    """
    if not text:
        return ""
    # 去除常见新闻前缀
    cleaned = re.sub(
        r'^(BlockBeats\s*消息[，,]?\s*\d+\s*月\s*\d+\s*日[，,]?\s*'
        r'|据.*?[，,]\s*'
        r'|消息[，,]\s*'
        r'|【.*?】\s*'
        r'|\d+\s*月\s*\d+\s*日[，,]?\s*'
        r'|Breaking:\s*'
        r'|BREAKING:\s*'
        r'|Update:\s*'
        r'|Just in:\s*)',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()
    # 去除标点符号（中英文）
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    # 统一空白
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
    return cleaned


def _tokenize(text: str) -> List[str]:
    """
    简单分词：对英文按空格分词，对中文按单字分词。
    返回去重后的 token 列表。
    """
    if not text:
        return []
    tokens = []
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            # CJK 字符：单字作为 token
            tokens.append(char)
        elif char == ' ':
            tokens.append(' ')
        else:
            tokens.append(char)
    # 按空格合并英文 token
    result = []
    current_word = []
    for t in tokens:
        if t == ' ':
            if current_word:
                result.append(''.join(current_word))
                current_word = []
        else:
            current_word.append(t)
    if current_word:
        result.append(''.join(current_word))
    return result


def _word_overlap_ratio(text_a: str, text_b: str) -> float:
    """
    计算两段文本的词级别 Jaccard 相似度。
    """
    tokens_a = set(_tokenize(_normalize_text(text_a)))
    tokens_b = set(_tokenize(_normalize_text(text_b)))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _extract_key_terms(text: str, top_n: int = 8) -> set:
    """
    从文本中提取关键词（去除停用词后的高信息量词汇）。
    用于跨源语义去重。
    """
    STOP_WORDS = {
        # English
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
        'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'between', 'and', 'but', 'or',
        'not', 'no', 'so', 'if', 'than', 'too', 'very', 'just', 'about',
        'up', 'out', 'its', 'it', 'this', 'that', 'these', 'those', 'he',
        'she', 'they', 'we', 'you', 'i', 'me', 'him', 'her', 'us', 'them',
        'my', 'your', 'his', 'our', 'their', 'what', 'which', 'who', 'whom',
        'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
        'few', 'more', 'most', 'other', 'some', 'such', 'only', 'own',
        'same', 'also', 'new', 'says', 'said', 'according',
        # Chinese common
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
        '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
        '没有', '看', '好', '自己', '这', '他', '她', '它', '们', '那',
        '被', '从', '把', '让', '用', '为', '与', '及', '等', '将', '已',
        '而', '但', '如', '或', '即', '若', '因', '于', '其', '中', '对',
        '表示', '认为', '可以', '目前', '以及', '通过', '进行', '据悉',
    }
    tokens = _tokenize(_normalize_text(text))
    # 过滤停用词和过短 token
    key_tokens = [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
    # 取前 N 个（保持出现顺序，靠前的通常更重要）
    seen = set()
    result = set()
    for t in key_tokens:
        if t not in seen:
            seen.add(t)
            result.add(t)
            if len(result) >= top_n:
                break
    return result


def is_summary_duplicate(title: str, summary: str) -> bool:
    """
    判断摘要是否与标题内容重复（增强版）。
    
    检测策略（任一命中即视为重复）：
    1. 前缀匹配：摘要去除新闻前缀后以标题内容开头
    2. 子串匹配：标题出现在摘要中，且占比超过阈值
    3. 词级别 Jaccard 相似度：> 0.65 视为重复
    4. SequenceMatcher 模糊匹配：> 0.75 视为重复
    5. 包含度检查：标题关键词大部分出现在摘要中
    
    Args:
        title: 标题文本
        summary: 摘要文本
        
    Returns:
        True 如果认为是重复的，否则 False
    """
    if not title or not summary:
        return False
    
    title_clean = _normalize_text(title)
    summary_clean = _normalize_text(summary)
    
    # 如果标题很短（少于5个字符），不做去重处理
    if len(title_clean) < 5:
        return False
    
    # 1. 前缀匹配
    if summary_clean.startswith(title_clean):
        return True
    
    # 2. 子串匹配（标题出现在摘要的任意位置）
    if title_clean in summary_clean:
        overlap_ratio = len(title_clean) / len(summary_clean) if summary_clean else 0
        if overlap_ratio > 0.4:
            return True
    
    # 3. 词级别 Jaccard 相似度
    word_sim = _word_overlap_ratio(title, summary)
    if word_sim > 0.65:
        return True
    
    # 4. SequenceMatcher 模糊匹配（捕捉改写/重排序）
    from difflib import SequenceMatcher
    seq_sim = SequenceMatcher(None, title_clean, summary_clean).ratio()
    if seq_sim > 0.75:
        return True
    
    # 5. 关键词包含度：标题关键词有 80%+ 出现在摘要中
    title_terms = _extract_key_terms(title, top_n=6)
    if len(title_terms) >= 2:
        summary_terms = _extract_key_terms(summary, top_n=15)
        overlap = title_terms & summary_terms
        containment = len(overlap) / len(title_terms)
        if containment >= 0.8:
            return True
    
    return False


def _compute_cross_similarity(item_a: Dict[str, Any], item_b: Dict[str, Any]) -> float:
    """
    计算两条新闻的综合相似度（多维度加权）。
    
    维度：
    1. 标题 SequenceMatcher 相似度 (权重 0.40)
    2. 标题词级别 Jaccard 相似度 (权重 0.25)
    3. 摘要词级别 Jaccard 相似度 (权重 0.15)
    4. 关键词重合度 (权重 0.20)
    
    Returns:
        0.0 ~ 1.0 的综合相似度分数
    """
    from difflib import SequenceMatcher
    
    title_a = item_a.get("title", "").strip()
    title_b = item_b.get("title", "").strip()
    summary_a = item_a.get("summary", "") or ""
    summary_b = item_b.get("summary", "") or ""
    
    # Dimension 1: Title SequenceMatcher
    title_seq_sim = 0.0
    if title_a and title_b:
        title_seq_sim = SequenceMatcher(
            None, _normalize_text(title_a), _normalize_text(title_b)
        ).ratio()
    
    # Dimension 2: Title word-level Jaccard
    title_word_sim = _word_overlap_ratio(title_a, title_b)
    
    # Dimension 3: Summary word-level Jaccard
    summary_word_sim = 0.0
    if summary_a and summary_b:
        summary_word_sim = _word_overlap_ratio(summary_a, summary_b)
    
    # Dimension 4: Key terms overlap (title + summary combined)
    combined_a = f"{title_a} {summary_a}"
    combined_b = f"{title_b} {summary_b}"
    terms_a = _extract_key_terms(combined_a, top_n=10)
    terms_b = _extract_key_terms(combined_b, top_n=10)
    
    keyword_sim = 0.0
    if terms_a and terms_b:
        intersection = len(terms_a & terms_b)
        union = len(terms_a | terms_b)
        keyword_sim = intersection / union if union > 0 else 0.0
    
    # Weighted combination
    combined_score = (
        title_seq_sim * 0.40 +
        title_word_sim * 0.25 +
        summary_word_sim * 0.15 +
        keyword_sim * 0.20
    )
    
    # Bonus: 如果标题非常相似（> 0.85），直接提高综合分数
    # 这确保标题几乎相同的条目一定被去重
    if title_seq_sim > 0.85:
        combined_score = max(combined_score, title_seq_sim)
    
    # Bonus: 如果关键词高度重合（> 0.7），也提高分数
    # 这捕捉标题不同但说的是同一事件的情况
    if keyword_sim > 0.7 and summary_word_sim > 0.5:
        combined_score = max(combined_score, 0.75)
    
    return combined_score


def _pick_best_item(item_a: Dict[str, Any], item_b: Dict[str, Any]) -> tuple:
    """
    在两条重复新闻中选择保留哪条。
    
    优先级：
    1. 有摘要的优先
    2. 摘要更长的优先（信息更丰富）
    3. section 优先级更高的优先（must_read > macro_insights > recommended > other）
    4. 有链接的优先
    
    Returns:
        (keeper, merged) 元组
    """
    section_priority = {"must_read": 0, "macro_insights": 1, "recommended": 2, "other": 3}
    
    summary_a = item_a.get("summary", "") or ""
    summary_b = item_b.get("summary", "") or ""
    
    # 评分系统
    score_a = 0
    score_b = 0
    
    # 有摘要 +2
    if summary_a:
        score_a += 2
    if summary_b:
        score_b += 2
    
    # 摘要长度
    if len(summary_a) > len(summary_b):
        score_a += 1
    elif len(summary_b) > len(summary_a):
        score_b += 1
    
    # Section 优先级
    sec_a = section_priority.get(item_a.get("section", "other"), 3)
    sec_b = section_priority.get(item_b.get("section", "other"), 3)
    if sec_a < sec_b:
        score_a += 1
    elif sec_b < sec_a:
        score_b += 1
    
    # 有链接 +1
    if item_a.get("link"):
        score_a += 1
    if item_b.get("link"):
        score_b += 1
    
    if score_b > score_a:
        return (item_b, item_a)
    return (item_a, item_b)


def deduplicate_by_similarity(items: List[Dict[str, Any]], threshold: float = 0.65) -> List[Dict[str, Any]]:
    """
    跨源语义去重（增强版）。
    
    使用多维度相似度计算（标题 SequenceMatcher + 词级 Jaccard + 
    摘要相似度 + 关键词重合度），比单纯标题匹配更准确。
    
    当多个来源报道同一事件时，保留信息最丰富的版本。
    
    Args:
        items: 内容条目列表，包含 'title' 和 'summary' 字段
        threshold: 综合相似度阈值 (0.0-1.0)，默认 0.65
        
    Returns:
        去重后的列表
    """
    if not items or len(items) <= 1:
        return items
    
    # Track which items to keep (by index)
    merged_into = {}  # index -> merged_target_index
    
    for i in range(len(items)):
        if i in merged_into:
            continue
        
        title_i = items[i].get("title", "").strip()
        if not title_i:
            continue
            
        for j in range(i + 1, len(items)):
            if j in merged_into:
                continue
            title_j = items[j].get("title", "").strip()
            if not title_j:
                continue
            
            # 计算综合相似度
            similarity = _compute_cross_similarity(items[i], items[j])
            
            if similarity >= threshold:
                keeper, merged = _pick_best_item(items[i], items[j])
                keeper_idx = i if keeper is items[i] else j
                merged_idx = j if keeper is items[i] else i
                
                merged_into[merged_idx] = keeper_idx
                
                # 标注综合来源
                source_keeper = keeper.get("source", "")
                source_merged = merged.get("source", "")
                if source_keeper and source_merged and source_keeper != source_merged:
                    existing_reason = keeper.get("reason", "")
                    keeper["reason"] = f"{existing_reason} [综合 {source_keeper}+{source_merged} 报道]".strip()
                
                # 如果被合并的有更好的摘要片段，补充到 keeper
                merged_summary = merged.get("summary", "") or ""
                keeper_summary = keeper.get("summary", "") or ""
                if merged_summary and not keeper_summary:
                    keeper["summary"] = merged_summary
                
                logger.debug(
                    f"Dedup merge: [{merged_idx}] \"{items[merged_idx].get('title', '')[:40]}\" "
                    f"-> [{keeper_idx}] \"{items[keeper_idx].get('title', '')[:40]}\" "
                    f"(sim={similarity:.2f})"
                )
                
                if merged_idx == i:
                    break  # i is merged, move to next i
    
    # Build deduplicated list preserving order
    result = [item for idx, item in enumerate(items) if idx not in merged_into]
    
    removed = len(items) - len(result)
    if removed > 0:
        logger.info(f"Deduplication: {len(items)} -> {len(result)} items ({removed} duplicates removed)")
    
    return result


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

    # Detect user language from storage first, then fallback to profile parsing
    lang = get_lang_from_storage(telegram_id)
    if not lang or lang == "en":
        # Fallback: try to detect from profile (for backwards compatibility)
        profile_lang = detect_user_language(profile)
        if profile_lang != "zh":  # Use profile lang if it's not default
            lang = profile_lang
    
    locale = get_locale(lang)

    # Generate AI summary (in English)
    ai_summary = await get_ai_summary(filtered_items, profile)
    
    # === Final output translation (all at once) ===
    # Get target language name for translation
    target_language = get_language_native_name(lang)
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

    # T2: Normalize dashes (double em-dash to single)
    title_escaped = title_escaped.replace("——", "—")
    summary_escaped = summary_escaped.replace("——", "—") if summary_escaped else ""

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

    # 显示 Twitter 作者（如果有）
    if author and author.startswith("@"):
        lines.append(f"📣 {author}")

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

    # T1: Apply cross-source deduplication
    filtered_items = deduplicate_by_similarity(filtered_items)

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
