"""
Language Service - Unified Language Management

This module provides a single entry point for all language-related operations.
It handles:
- User language detection and storage
- UI string localization (with AI translation for unsupported languages)
- Content translation to user's preferred language

Architecture:
- Primary source: users.json (fast lookup)
- Backup source: profile.txt (AI-visible context)
- UI cache: data/ui_cache/{user_id}.json (for AI-translated UI strings)
"""
import json
import logging
import os
from typing import Dict, Optional, Any

from config import DATA_DIR, TRANSLATION_TEMPERATURE

logger = logging.getLogger(__name__)

# Languages with predefined UI strings
SUPPORTED_UI_LANGUAGES = ["zh", "en", "ja", "ko"]

# UI Version - increment when ui_strings.py is updated
# This ensures cached translations are refreshed when UI strings change
UI_VERSION = "1.0.0"

# Language code to native name mapping (for AI prompts)
LANGUAGE_NATIVE_NAMES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "ar": "العربية",
    "it": "Italiano",
    "tr": "Türkçe",
    "pl": "Polski",
    "uk": "Українська",
    "nl": "Nederlands",
    "id": "Bahasa Indonesia",
    "ms": "Bahasa Melayu",
    "hi": "हिन्दी",
}

# UI Cache directory
UI_CACHE_DIR = os.path.join(DATA_DIR, "ui_cache")


def get_language_native_name(lang_code: str) -> str:
    """
    Get the native name of a language for use in AI prompts.
    
    Args:
        lang_code: Language code (e.g., "zh", "en", "ja")
        
    Returns:
        Native language name (e.g., "中文", "English", "日本語")
    """
    return LANGUAGE_NATIVE_NAMES.get(lang_code, "English")


def normalize_language_code(code: Optional[str]) -> str:
    """
    Normalize Telegram language_code to standard format.
    
    Unlike the old version which only supported 4 languages,
    this version preserves any valid language code.
    
    Args:
        code: Telegram language_code (e.g., "en-US", "zh-hans", "ru")
        
    Returns:
        Normalized language code (e.g., "en", "zh", "ru")
    """
    if not code:
        return "en"  # Default to English
    
    # Convert to lowercase and get base language
    code = code.lower().strip()
    
    # Extract base code (before - or _)
    base_code = code.split("-")[0].split("_")[0]
    
    # Handle Chinese variants specially
    if base_code == "zh":
        return "zh"
    
    return base_code


def get_user_language(telegram_id: str) -> str:
    """
    Get user's language code from storage.
    
    Lookup order:
    1. users.json (fast, primary)
    2. profile.txt (fallback, parse [用户语言] field)
    3. Default to "en"
    
    Args:
        telegram_id: User's Telegram ID
        
    Returns:
        Language code (e.g., "zh", "en", "ja", "ru")
    """
    # Import here to avoid circular imports
    from utils.json_storage import get_user
    
    user = get_user(telegram_id)
    if user:
        lang = user.get("language")
        if lang:
            return lang
    
    # Fallback: try to parse from profile
    try:
        from utils.json_storage import get_user_profile
        profile = get_user_profile(telegram_id)
        if profile:
            # Look for [用户语言] or [User Language] field
            import re
            match = re.search(r'\[(?:用户语言|User Language)\]\s*[:\-]?\s*(\S+)', profile, re.IGNORECASE)
            if match:
                lang_name = match.group(1).lower()
                # Map common names to codes
                name_to_code = {
                    "中文": "zh", "chinese": "zh", "简体中文": "zh",
                    "english": "en", "英文": "en", "英语": "en",
                    "日本語": "ja", "japanese": "ja", "日语": "ja",
                    "한국어": "ko", "korean": "ko", "韩语": "ko",
                    "русский": "ru", "russian": "ru",
                    "español": "es", "spanish": "es",
                }
                if lang_name in name_to_code:
                    return name_to_code[lang_name]
    except Exception as e:
        logger.debug(f"Failed to parse language from profile: {e}")
    
    return "en"  # Default


def update_user_language(telegram_id: str, lang_code: str) -> bool:
    """
    Update user's language in storage (both users.json and profile).
    
    Args:
        telegram_id: User's Telegram ID
        lang_code: New language code
        
    Returns:
        True if successful
    """
    from utils.json_storage import update_user_language as storage_update_lang
    
    # Update users.json
    success = storage_update_lang(telegram_id, lang_code)
    
    # TODO: Also update profile.txt [用户语言] field
    # This requires parsing and modifying the profile text
    
    # Clear UI cache when language changes (for non-supported languages)
    if lang_code not in SUPPORTED_UI_LANGUAGES:
        clear_ui_cache(telegram_id)
    
    return success


# ============ UI Cache Management ============

def _ensure_ui_cache_dir():
    """Ensure UI cache directory exists."""
    os.makedirs(UI_CACHE_DIR, exist_ok=True)


def load_ui_cache(telegram_id: str) -> Optional[Dict[str, str]]:
    """
    Load cached UI strings for a user.
    
    Returns None if:
    - Cache file doesn't exist
    - Cache version doesn't match current UI_VERSION (triggers re-translation)
    - Cache file is corrupted
    
    Args:
        telegram_id: User's Telegram ID
        
    Returns:
        Dict of UI strings, or None if not cached or outdated
    """
    cache_path = os.path.join(UI_CACHE_DIR, f"{telegram_id}.json")
    
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # Check version - if mismatch, return None to trigger re-translation
            cached_version = data.get("ui_version")
            if cached_version != UI_VERSION:
                logger.info(f"UI cache version mismatch for {telegram_id}: {cached_version} != {UI_VERSION}, will refresh")
                return None
            
            return data.get("ui_strings")
    except Exception as e:
        logger.error(f"Failed to load UI cache for {telegram_id}: {e}")
        return None


def save_ui_cache(telegram_id: str, ui_strings: Dict[str, str], lang_code: str) -> bool:
    """
    Save translated UI strings to cache.
    
    Includes UI_VERSION to enable automatic cache invalidation when UI strings are updated.
    
    Args:
        telegram_id: User's Telegram ID
        ui_strings: Dict of translated UI strings
        lang_code: Language code
        
    Returns:
        True if successful
    """
    _ensure_ui_cache_dir()
    cache_path = os.path.join(UI_CACHE_DIR, f"{telegram_id}.json")
    
    try:
        data = {
            "telegram_id": telegram_id,
            "language": lang_code,
            "ui_version": UI_VERSION,  # Store version for cache invalidation
            "ui_strings": ui_strings,
            "created_at": __import__("datetime").datetime.now().isoformat()
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved UI cache for {telegram_id} ({lang_code}) with version {UI_VERSION}")
        return True
    except Exception as e:
        logger.error(f"Failed to save UI cache for {telegram_id}: {e}")
        return False


def clear_ui_cache(telegram_id: str) -> bool:
    """
    Clear UI cache for a user (called when language changes).
    
    Args:
        telegram_id: User's Telegram ID
        
    Returns:
        True if cleared or didn't exist
    """
    cache_path = os.path.join(UI_CACHE_DIR, f"{telegram_id}.json")
    
    try:
        if os.path.exists(cache_path):
            os.remove(cache_path)
            logger.info(f"Cleared UI cache for {telegram_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to clear UI cache for {telegram_id}: {e}")
        return False


# ============ UI Strings with AI Translation ============

async def translate_ui_strings(target_lang: str) -> Dict[str, str]:
    """
    Translate English UI strings to target language using AI.
    
    Uses flash model for cost efficiency.
    
    Args:
        target_lang: Target language code (e.g., "ru", "es")
        
    Returns:
        Dict of translated UI strings
    """
    from locales.ui_strings import UI_STRINGS
    from services.llm_factory import call_llm_json
    
    # Use English as source
    source_strings = UI_STRINGS.get("en", {})
    
    # Select a subset of essential UI strings to translate
    # (to reduce AI cost and response time)
    essential_keys = [
        "menu_view_digest", "menu_preferences", "menu_sources", "menu_stats",
        "welcome_back", "welcome_back_desc", "welcome_choose",
        "onboarding_title", "onboarding_welcome", "onboarding_intro",
        "onboarding_step", "onboarding_thinking",
        "btn_confirm", "btn_restart", "btn_cancel",
        "settings_title", "settings_view", "settings_update", "settings_reset",
        "back", "confirm", "cancel", "retry",
        "feedback_helpful", "feedback_not_helpful", "feedback_thanks",
        "btn_view_original", "btn_not_interested",
        "error_occurred", "processing",
    ]
    
    strings_to_translate = {k: source_strings.get(k, "") for k in essential_keys if k in source_strings}
    
    target_lang_name = get_language_native_name(target_lang)
    
    prompt = f"""Translate the following UI strings to {target_lang_name}.
Output a JSON object with the same keys and translated values.
Keep placeholder variables like {{name}}, {{count}} unchanged.
Output only valid JSON, no extra text.

{json.dumps(strings_to_translate, ensure_ascii=False, indent=2)}"""

    try:
        result, model_used = await call_llm_json(
            prompt=prompt,
            system_instruction="You are a professional UI translator. Output valid JSON only.",
            temperature=TRANSLATION_TEMPERATURE,  # Use configured temperature for stable output
            context="ui-translation"
        )
        
        if result and isinstance(result, dict):
            logger.info(f"Translated {len(result)} UI strings to {target_lang} using {model_used} (temp={TRANSLATION_TEMPERATURE})")
            return result
    except Exception as e:
        logger.error(f"UI translation failed: {e}")
    
    # Fallback: return English strings
    return strings_to_translate


async def get_ui_strings(telegram_id: str) -> Dict[str, str]:
    """
    Get UI strings for a user's language.
    
    For supported languages (zh, en, ja, ko): returns predefined strings
    For other languages: returns AI-translated strings (cached)
    
    Args:
        telegram_id: User's Telegram ID
        
    Returns:
        Dict of UI strings in user's language
    """
    from locales.ui_strings import UI_STRINGS, LocaleDict
    
    lang = get_user_language(telegram_id)
    
    # For supported languages, return predefined strings
    if lang in SUPPORTED_UI_LANGUAGES:
        en_dict = UI_STRINGS.get("en", {})
        lang_dict = UI_STRINGS.get(lang, en_dict)
        return LocaleDict(lang_dict, en_dict)
    
    # For unsupported languages, check cache first
    cached = load_ui_cache(telegram_id)
    if cached:
        logger.debug(f"Using cached UI strings for {telegram_id}")
        # Merge with English fallback
        en_dict = UI_STRINGS.get("en", {})
        return LocaleDict(cached, en_dict)
    
    # No cache, translate with AI
    logger.info(f"Translating UI strings to {lang} for {telegram_id}")
    translated = await translate_ui_strings(lang)
    
    # Save to cache
    save_ui_cache(telegram_id, translated, lang)
    
    # Merge with English fallback
    en_dict = UI_STRINGS.get("en", {})
    return LocaleDict(translated, en_dict)


def get_ui_strings_sync(telegram_id: str) -> Dict[str, str]:
    """
    Synchronous version of get_ui_strings.
    
    For supported languages: returns predefined strings
    For unsupported languages: returns cached strings or English fallback
    
    Note: This does NOT trigger AI translation. Use async version for that.
    
    Args:
        telegram_id: User's Telegram ID
        
    Returns:
        Dict of UI strings
    """
    from locales.ui_strings import UI_STRINGS, LocaleDict
    
    lang = get_user_language(telegram_id)
    
    # For supported languages
    if lang in SUPPORTED_UI_LANGUAGES:
        en_dict = UI_STRINGS.get("en", {})
        lang_dict = UI_STRINGS.get(lang, en_dict)
        return LocaleDict(lang_dict, en_dict)
    
    # For unsupported languages, try cache
    cached = load_ui_cache(telegram_id)
    if cached:
        en_dict = UI_STRINGS.get("en", {})
        return LocaleDict(cached, en_dict)
    
    # No cache, fallback to English
    return UI_STRINGS.get("en", {})


# ============ Content Translation ============

async def translate_to_user_language(text: str, telegram_id: str) -> str:
    """
    Translate text to user's preferred language.
    
    Args:
        text: Text to translate
        telegram_id: User's Telegram ID
        
    Returns:
        Translated text
    """
    from services.content_filter import translate_text
    
    lang = get_user_language(telegram_id)
    target_lang_name = get_language_native_name(lang)
    
    # Don't translate if already in English or target is English
    if lang == "en":
        return text
    
    return await translate_text(text, target_lang_name)
