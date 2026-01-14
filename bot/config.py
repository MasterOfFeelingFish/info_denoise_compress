"""
Web3 Daily Digest - Configuration Management
"""
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")

# Thinking level: LOW or HIGH (default HIGH for better reasoning)
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "HIGH")

# Build API URL: supports both base URL and full URL
_api_base = os.getenv("GEMINI_API_URL", "").rstrip("/")
if _api_base:
    # User provided custom URL
    if "/v1beta/models/" in _api_base or ":generateContent" in _api_base:
        # Full URL provided, use as-is
        GEMINI_API_URL = _api_base
    else:
        # Base URL provided, append path
        GEMINI_API_URL = f"{_api_base}/v1beta/models/{GEMINI_MODEL}:generateContent"
else:
    # Default Google API
    GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Push Schedule (Beijing Time)
def _parse_int_env(key: str, default: int) -> int:
    """Parse an integer environment variable with fallback."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

PUSH_HOUR = _parse_int_env("PUSH_HOUR", 9)
PUSH_MINUTE = _parse_int_env("PUSH_MINUTE", 0)

# Data Directory
DATA_DIR = os.getenv("DATA_DIR", "./data")

# Logging Configuration
LOG_ROTATE_DAYS = _parse_int_env("LOG_ROTATE_DAYS", 1)  # 每几天轮转一次日志
LOG_BACKUP_COUNT = _parse_int_env("LOG_BACKUP_COUNT", 30)  # 最多保留多少个备份

# Data Retention Configuration (days)
# 数据保留天数配置
RAW_CONTENT_RETENTION_DAYS = _parse_int_env("RAW_CONTENT_RETENTION_DAYS", 7)  # 原始内容保留天数
DAILY_STATS_RETENTION_DAYS = _parse_int_env("DAILY_STATS_RETENTION_DAYS", 30)  # 每日统计保留天数
FEEDBACK_RETENTION_DAYS = _parse_int_env("FEEDBACK_RETENTION_DAYS", 30)  # 反馈记录保留天数

# Digest Configuration
# 简报配置
MIN_DIGEST_ITEMS = _parse_int_env("MIN_DIGEST_ITEMS", 15)  # 每日精选最少条数
MAX_DIGEST_ITEMS = _parse_int_env("MAX_DIGEST_ITEMS", 30)  # 每日精选最多条数

# AI Chat Configuration
# AI 对话配置
CHAT_CONTEXT_DAYS = _parse_int_env("CHAT_CONTEXT_DAYS", 1)  # 对话上下文保留天数 (0=当天, 1=昨天, 2=前天)

# Paths
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
FEEDBACK_DIR = os.path.join(DATA_DIR, "feedback")
DAILY_STATS_DIR = os.path.join(DATA_DIR, "daily_stats")
RAW_CONTENT_DIR = os.path.join(DATA_DIR, "raw_content")
USER_SOURCES_DIR = os.path.join(DATA_DIR, "user_sources")  # Per-user source configs


# ============ Default Sources Configuration ============

# Hardcoded default sources (used if env not set)
_DEFAULT_SOURCES = {
    "twitter": {
        "@VitalikButerin": "",
        "@lookonchain": "",
        "@whale_alert": "",
        "@EmberCN": "",
        "@ai_9684xtpa": "",
        "@ethereum": "",
        "@solana": "",
        "@arbitrum": "",
        "@CoinDesk": "",
        "@TheBlock__": "",
        "@WuBlockchain": "",
        "@BlockBeatsAsia": "",
    },
    "websites": {
        "The Block": "https://www.theblock.co/rss.xml",
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "Decrypt": "https://decrypt.co/feed",
        "Cointelegraph": "https://cointelegraph.com/rss",
    }
}


def _parse_sources_env() -> dict:
    """
    Parse default sources from environment variables.

    Supports two formats:
    1. JSON format: DEFAULT_SOURCES='{"twitter": {"@user": "url"}, "websites": {"name": "url"}}'
    2. Simple format (comma-separated):
       DEFAULT_TWITTER_SOURCES='@VitalikButerin,@lookonchain,@whale_alert'
       DEFAULT_WEBSITE_SOURCES='The Block|https://theblock.co/rss.xml,CoinDesk|https://coindesk.com/rss'

    Returns:
        Dict with twitter and websites sources
    """
    # Try JSON format first
    json_sources = os.getenv("DEFAULT_SOURCES", "")
    if json_sources:
        try:
            parsed = json.loads(json_sources)
            if isinstance(parsed, dict):
                return {
                    "twitter": parsed.get("twitter", {}),
                    "websites": parsed.get("websites", {})
                }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse DEFAULT_SOURCES JSON: {e}")

    # Try simple format
    result = {"twitter": {}, "websites": {}}

    # Parse Twitter sources: @user1,@user2 or @user1|rss_url,@user2|rss_url
    twitter_env = os.getenv("DEFAULT_TWITTER_SOURCES", "")
    if twitter_env:
        for item in twitter_env.split(","):
            item = item.strip()
            if not item:
                continue
            if "|" in item:
                parts = item.split("|", 1)
                handle = parts[0].strip()
                url = parts[1].strip()
            else:
                handle = item
                url = ""
            # Ensure @ prefix
            if not handle.startswith("@"):
                handle = f"@{handle}"
            result["twitter"][handle] = url

    # Parse website sources: Name|url,Name2|url2
    website_env = os.getenv("DEFAULT_WEBSITE_SOURCES", "")
    if website_env:
        for item in website_env.split(","):
            item = item.strip()
            if not item:
                continue
            if "|" in item:
                parts = item.split("|", 1)
                name = parts[0].strip()
                url = parts[1].strip()
                result["websites"][name] = url

    # If nothing from env, return None to use hardcoded defaults
    if not result["twitter"] and not result["websites"]:
        return None

    return result


# Load default sources: env > hardcoded defaults
_env_sources = _parse_sources_env()
DEFAULT_USER_SOURCES = _env_sources if _env_sources else _DEFAULT_SOURCES
