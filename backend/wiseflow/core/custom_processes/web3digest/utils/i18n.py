"""
国际化工具模块
从 Telegram 获取用户语言并翻译消息
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any
from telegram import Update


# 语言资源缓存
_locale_cache: Dict[str, Dict[str, Any]] = {}


def normalize_language_code(lang_code: Optional[str]) -> str:
    """
    标准化语言代码
    
    Args:
        lang_code: Telegram 语言代码（如 'zh', 'zh-CN', 'en', 'en-US', 'ja', 'ko', 'de', 'fr', 'es'）
        
    Returns:
        标准化后的语言代码（'zh', 'en', 'ja', 'ko', 'de', 'fr', 'es'）
    """
    if not lang_code:
        return 'zh'
    
    lang_code = lang_code.lower()
    if lang_code.startswith('zh'):
        return 'zh'
    elif lang_code.startswith('en'):
        return 'en'
    elif lang_code.startswith('ja'):
        return 'ja'
    elif lang_code.startswith('ko'):
        return 'ko'
    elif lang_code.startswith('de'):
        return 'de'
    elif lang_code.startswith('fr'):
        return 'fr'
    elif lang_code.startswith('es'):
        return 'es'
    else:
        # 默认返回中文
        return 'zh'


def get_user_language(update: Update) -> str:
    """
    从 Telegram Update 中获取用户语言代码
    
    Args:
        update: Telegram Update 对象
        
    Returns:
        标准化后的语言代码（'zh', 'en', 'ja', 'ko', 'de', 'fr', 'es'）
    """
    if not update or not update.effective_user:
        return 'zh'
    
    lang_code = update.effective_user.language_code
    return normalize_language_code(lang_code)


def _load_locale(lang: str) -> Dict[str, Any]:
    """
    加载语言资源文件（带缓存）
    
    Args:
        lang: 语言代码（'zh', 'en', 'ja', 'ko', 'de', 'fr', 'es'）
        
    Returns:
        语言资源字典
    """
    # 检查缓存
    if lang in _locale_cache:
        return _locale_cache[lang]
    
    # 确定资源文件路径
    # 从 utils/i18n.py -> web3digest -> locales/{lang}.json
    current_file = Path(__file__)
    locales_dir = current_file.parent.parent / "locales"
    locale_file = locales_dir / f"{lang}.json"
    
    # 加载资源文件
    try:
        with open(locale_file, 'r', encoding='utf-8') as f:
            locale_data = json.load(f)
        
        # 缓存结果
        _locale_cache[lang] = locale_data
        return locale_data
    except FileNotFoundError:
        # 如果找不到文件，返回空字典并使用默认值
        print(f"Warning: Locale file not found: {locale_file}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse locale file {locale_file}: {e}")
        return {}


def _get_nested_value(data: Dict[str, Any], key_path: str) -> Optional[str]:
    """
    从嵌套字典中获取值（支持 'auth.access_denied' 这样的路径）
    
    Args:
        data: 嵌套字典
        key_path: 键路径，用点分隔（如 'auth.access_denied'）
        
    Returns:
        对应的值，如果不存在返回 None
    """
    keys = key_path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    
    return current if isinstance(current, str) else None


def translate(key: str, lang: str, **kwargs) -> str:
    """
    根据 key 和语言返回翻译文本
    
    Args:
        key: 翻译键（如 'auth.access_denied'）
        lang: 语言代码（'zh', 'en', 'ja', 'ko', 'de', 'fr', 'es'）
        **kwargs: 用于格式化文本的参数（如 user_name='张三'）
        
    Returns:
        翻译后的文本，如果找不到则返回 key 本身
    """
    # 标准化语言代码
    lang = normalize_language_code(lang)
    
    # 加载语言资源
    locale_data = _load_locale(lang)
    
    # 获取翻译文本
    text = _get_nested_value(locale_data, key)
    
    if text is None:
        # 如果找不到翻译，返回 key 本身（便于调试）
        print(f"Warning: Translation key not found: {key} (lang: {lang})")
        return key
    
    # 格式化文本（支持 {variable} 参数替换）
    try:
        if kwargs:
            text = text.format(**kwargs)
    except KeyError as e:
        # 如果缺少参数，打印警告但仍返回文本
        print(f"Warning: Missing format parameter {e} for key {key}")
    
    return text


def format_message(template_key: str, lang: str, **params) -> str:
    """
    格式化消息（translate 的别名，保持向后兼容）
    
    Args:
        template_key: 翻译键
        lang: 语言代码
        **params: 格式化参数
        
    Returns:
        翻译并格式化后的文本
    """
    return translate(template_key, lang, **params)
