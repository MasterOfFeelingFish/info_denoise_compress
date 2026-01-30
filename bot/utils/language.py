"""
Language Utilities

Handles language detection, normalization, and user language preferences.
"""
from typing import Optional

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
