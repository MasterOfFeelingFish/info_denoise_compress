"""
Web3 Daily Digest - Configuration Management
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro")

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

# Paths
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
FEEDBACK_DIR = os.path.join(DATA_DIR, "feedback")
DAILY_STATS_DIR = os.path.join(DATA_DIR, "daily_stats")
RAW_CONTENT_DIR = os.path.join(DATA_DIR, "raw_content")
