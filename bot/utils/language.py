"""
Language Utilities

Handles language detection, normalization, and user language preferences.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Supported languages in order of preference for fallback
SUPPORTED_LANGUAGES = ["zh", "en", "ja", "ko"]


def normalize_language_code(code: Optional[str]) -> str:
    """
    Normalize Telegram language_code to our supported language codes.
    
    Telegram language codes can be:
    - Simple: "en", "zh", "ja", "ko"
    - Regional: "en-US", "en-GB", "zh-hans", "zh-hant"
    
    We map them to our supported languages:
    - "zh", "zh-hans", "zh-hant", "zh-cn", "zh-tw" -> "zh"
    - "en", "en-US", "en-GB", etc. -> "en"
    - "ja" -> "ja"
    - "ko" -> "ko"
    - Others -> "en" (default)
    
    Args:
        code: Telegram language_code (e.g., "en-US", "zh-hans")
        
    Returns:
        Normalized language code (e.g., "en", "zh")
    """
    if not code:
        return "en"  # Default to English for unknown
    
    # Convert to lowercase and get base language
    code = code.lower().strip()
    
    # Handle Chinese variants
    if code.startswith("zh"):
        return "zh"
    
    # Handle English variants
    if code.startswith("en"):
        return "en"
    
    # Handle Japanese
    if code.startswith("ja"):
        return "ja"
    
    # Handle Korean
    if code.startswith("ko"):
        return "ko"
    
    # For other languages, try to match the base code
    base_code = code.split("-")[0].split("_")[0]
    
    if base_code in SUPPORTED_LANGUAGES:
        return base_code
    
    # Default to English for unsupported languages
    return "en"


def detect_language_from_text(text: str) -> Optional[str]:
    """
    Detect language from user's text content (e.g. onboarding reply).
    Returns zh, en, ja, ko based on character ranges, or None if no detection.
    Used to dynamically adjust bot language when user replies in a different language.
    """
    preview = (text or "")[:80].replace("\n", " ")
    if not text or not text.strip():
        logger.info("[lang_detect] input empty or whitespace -> None")
        return None
    # Scan by character ranges (prioritize CJK: ja before zh due to overlap)
    for i, char in enumerate(text):
        if "\u3040" <= char <= "\u30ff":  # Hiragana / Katakana
            logger.info("[lang_detect] text=%r ... -> char[%d]=%r (Hiragana/Katakana) -> ja", preview, i, char)
            return "ja"
        if "\uac00" <= char <= "\ud7af" or "\u1100" <= char <= "\u11ff":  # Hangul
            logger.info("[lang_detect] text=%r ... -> char[%d]=%r (Hangul) -> ko", preview, i, char)
            return "ko"
        if "\u4e00" <= char <= "\u9fff":  # CJK Unified Ideographs (Chinese/Japanese/Kanji)
            logger.info("[lang_detect] text=%r ... -> char[%d]=%r (CJK) -> zh", preview, i, char)
            return "zh"
        if "\u0400" <= char <= "\u04ff":  # Cyrillic
            logger.info("[lang_detect] text=%r ... -> char[%d]=%r (Cyrillic) -> en", preview, i, char)
            return "en"  # Fallback to en (we don't have ru UI)
    # No CJK/Cyrillic: if text has letters (e.g. Latin/English), treat as English
    if any(c.isalpha() for c in text):
        logger.info("[lang_detect] text=%r ... -> has letters (Latin/English) -> en", preview)
        return "en"
    logger.info("[lang_detect] text=%r ... -> no letters (numbers/emoji only) -> None (keep current)", preview)
    return None  # Numbers only or no letters: keep current language


def is_supported_language(code: str) -> bool:
    """
    Check if a language code is supported.
    
    Args:
        code: Language code to check
        
    Returns:
        True if supported, False otherwise
    """
    return code in SUPPORTED_LANGUAGES


def get_language_name(code: str, in_language: str = "en") -> str:
    """
    Get the display name of a language.
    
    Args:
        code: Language code
        in_language: Language to display the name in
        
    Returns:
        Human-readable language name
    """
    names = {
        "zh": {
            "zh": "中文",
            "en": "Chinese",
            "ja": "中国語",
            "ko": "중국어",
        },
        "en": {
            "zh": "英文",
            "en": "English",
            "ja": "英語",
            "ko": "영어",
        },
        "ja": {
            "zh": "日文",
            "en": "Japanese",
            "ja": "日本語",
            "ko": "일본어",
        },
        "ko": {
            "zh": "韩文",
            "en": "Korean",
            "ja": "韓国語",
            "ko": "한국어",
        },
    }
    
    lang_names = names.get(code, {})
    return lang_names.get(in_language, lang_names.get("en", code))
