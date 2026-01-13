"""
JSON Storage Utilities

Handles all file-based data storage operations.
Uses JSON files for users, profiles, feedback, and content.
"""
import json
import os
import logging
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# File locking is only available on Unix systems
if sys.platform != "win32":
    import fcntl

from config import (
    DATA_DIR,
    USERS_FILE,
    PROFILES_DIR,
    FEEDBACK_DIR,
    DAILY_STATS_DIR,
    RAW_CONTENT_DIR,
)

logger = logging.getLogger(__name__)


def _ensure_dir(path: str) -> None:
    """Ensure directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)


def _read_json(file_path: str) -> Dict[str, Any]:
    """Read JSON file with file locking."""
    try:
        if not os.path.exists(file_path):
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            # File locking for concurrent access (Unix only)
            if sys.platform != "win32":
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                if sys.platform != "win32":
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in {file_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return {}


def _write_json(file_path: str, data: Dict[str, Any]) -> bool:
    """Write JSON file with file locking."""
    try:
        _ensure_dir(os.path.dirname(file_path))

        with open(file_path, "w", encoding="utf-8") as f:
            # File locking for concurrent access (Unix only)
            if sys.platform != "win32":
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, ensure_ascii=False, indent=2)
                return True
            finally:
                if sys.platform != "win32":
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"Error writing {file_path}: {e}")
        return False


# ============ User Management ============

def get_users() -> List[Dict[str, Any]]:
    """Get all users."""
    data = _read_json(USERS_FILE)
    return data.get("users", [])


def get_user(telegram_id: str) -> Optional[Dict[str, Any]]:
    """Get user by Telegram ID."""
    users = get_users()
    for user in users:
        if user.get("telegram_id") == telegram_id:
            return user
    return None


def create_user(
    telegram_id: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new user."""
    data = _read_json(USERS_FILE)
    if "users" not in data:
        data["users"] = []

    # Check if user already exists
    for user in data["users"]:
        if user.get("telegram_id") == telegram_id:
            return user

    # Create new user
    user = {
        "id": f"user_{len(data['users']) + 1:03d}",
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "created": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
    }

    data["users"].append(user)
    _write_json(USERS_FILE, data)

    logger.info(f"Created user: {user['id']} (telegram_id: {telegram_id})")
    return user


def update_user_activity(telegram_id: str) -> None:
    """Update user's last activity timestamp."""
    data = _read_json(USERS_FILE)
    for user in data.get("users", []):
        if user.get("telegram_id") == telegram_id:
            user["last_active"] = datetime.now().isoformat()
            _write_json(USERS_FILE, data)
            break


# ============ User Profile Management ============

def get_user_profile(telegram_id: str) -> Optional[str]:
    """Get user's natural language profile."""
    user = get_user(telegram_id)
    if not user:
        return None

    profile_path = os.path.join(PROFILES_DIR, f"{user['id']}.txt")
    if not os.path.exists(profile_path):
        return None

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading profile for {telegram_id}: {e}")
        return None


def save_user_profile(telegram_id: str, profile: str) -> bool:
    """Save user's natural language profile."""
    user = get_user(telegram_id)
    if not user:
        logger.error(f"Cannot save profile: user {telegram_id} not found")
        return False

    _ensure_dir(PROFILES_DIR)
    profile_path = os.path.join(PROFILES_DIR, f"{user['id']}.txt")

    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile)
        logger.info(f"Saved profile for user {user['id']}")
        return True
    except Exception as e:
        logger.error(f"Error saving profile for {telegram_id}: {e}")
        return False


# ============ Feedback Management ============

def save_feedback(
    telegram_id: str,
    overall_rating: str,
    reason_selected: Optional[List[str]] = None,
    reason_text: Optional[str] = None,
    item_feedbacks: Optional[List[Dict[str, str]]] = None
) -> bool:
    """Save user feedback for a day."""
    user = get_user(telegram_id)
    if not user:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    feedback_path = os.path.join(FEEDBACK_DIR, f"{today}.json")

    data = _read_json(feedback_path)
    if "date" not in data:
        data["date"] = today
        data["feedbacks"] = []

    feedback = {
        "user_id": user["id"],
        "telegram_id": telegram_id,
        "time": datetime.now().strftime("%H:%M"),
        "overall": overall_rating,
        "reason_selected": reason_selected or [],
        "reason_text": reason_text,
        "item_feedbacks": item_feedbacks or [],
    }

    data["feedbacks"].append(feedback)
    return _write_json(feedback_path, data)


def get_user_feedbacks(telegram_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """Get user's feedback history for the past N days."""
    user = get_user(telegram_id)
    if not user:
        return []

    feedbacks = []
    from datetime import timedelta

    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        feedback_path = os.path.join(FEEDBACK_DIR, f"{date}.json")

        data = _read_json(feedback_path)
        for feedback in data.get("feedbacks", []):
            if feedback.get("user_id") == user["id"]:
                feedback["date"] = date
                feedbacks.append(feedback)

    return feedbacks


# ============ Daily Stats Management ============

def save_daily_stats(
    date: str,
    sources_monitored: int,
    raw_items_scanned: int,
    user_stats: Dict[str, Dict[str, Any]]
) -> bool:
    """Save daily statistics."""
    stats_path = os.path.join(DAILY_STATS_DIR, f"{date}.json")

    data = {
        "date": date,
        "sources_monitored": sources_monitored,
        "raw_items_scanned": raw_items_scanned,
        "users": user_stats,
    }

    return _write_json(stats_path, data)


def get_daily_stats(date: Optional[str] = None) -> Dict[str, Any]:
    """Get daily statistics."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    stats_path = os.path.join(DAILY_STATS_DIR, f"{date}.json")
    return _read_json(stats_path)


# ============ Raw Content Management ============

def save_raw_content(date: str, items: List[Dict[str, Any]]) -> bool:
    """Save raw fetched content for a day."""
    content_path = os.path.join(RAW_CONTENT_DIR, f"{date}.json")

    data = {
        "date": date,
        "fetched_at": datetime.now().isoformat(),
        "count": len(items),
        "items": items,
    }

    return _write_json(content_path, data)


def get_raw_content(date: Optional[str] = None) -> Dict[str, Any]:
    """Get raw content for a day."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    content_path = os.path.join(RAW_CONTENT_DIR, f"{date}.json")
    return _read_json(content_path)
