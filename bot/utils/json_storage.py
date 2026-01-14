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
    USER_SOURCES_DIR,
    DEFAULT_USER_SOURCES,
    RAW_CONTENT_RETENTION_DAYS,
    DAILY_STATS_RETENTION_DAYS,
    FEEDBACK_RETENTION_DAYS,
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


def get_user_setting(telegram_id: str, key: str, default: Any = None) -> Any:
    """Get a user setting value."""
    user = get_user(telegram_id)
    if not user:
        return default
    return user.get("settings", {}).get(key, default)


def set_user_setting(telegram_id: str, key: str, value: Any) -> bool:
    """Set a user setting value."""
    data = _read_json(USERS_FILE)
    for user in data.get("users", []):
        if user.get("telegram_id") == telegram_id:
            if "settings" not in user:
                user["settings"] = {}
            user["settings"][key] = value
            return _write_json(USERS_FILE, data)
    return False


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


# ============ User Sources Management ============


def get_user_sources(telegram_id: str) -> Dict[str, Dict[str, str]]:
    """Get user's RSS source configuration."""
    user = get_user(telegram_id)
    if not user:
        return DEFAULT_USER_SOURCES.copy()

    _ensure_dir(USER_SOURCES_DIR)
    sources_path = os.path.join(USER_SOURCES_DIR, f"{user['id']}.json")

    if not os.path.exists(sources_path):
        # Initialize with default sources
        save_user_sources(telegram_id, DEFAULT_USER_SOURCES)
        return DEFAULT_USER_SOURCES.copy()

    data = _read_json(sources_path)
    return data.get("sources", DEFAULT_USER_SOURCES.copy())


def save_user_sources(telegram_id: str, sources: Dict[str, Dict[str, str]]) -> bool:
    """Save user's RSS source configuration."""
    user = get_user(telegram_id)
    if not user:
        logger.error(f"Cannot save sources: user {telegram_id} not found")
        return False

    _ensure_dir(USER_SOURCES_DIR)
    sources_path = os.path.join(USER_SOURCES_DIR, f"{user['id']}.json")

    data = {
        "user_id": user["id"],
        "telegram_id": telegram_id,
        "updated": datetime.now().isoformat(),
        "sources": sources,
    }

    result = _write_json(sources_path, data)
    if result:
        logger.info(f"Saved sources for user {user['id']}")
    return result


def add_user_source(telegram_id: str, category: str, name: str, url: str) -> bool:
    """Add a source to user's configuration."""
    sources = get_user_sources(telegram_id)

    if category not in sources:
        sources[category] = {}

    sources[category][name] = url
    return save_user_sources(telegram_id, sources)


def remove_user_source(telegram_id: str, category: str, name: str) -> bool:
    """Remove a source from user's configuration."""
    sources = get_user_sources(telegram_id)

    if category in sources and name in sources[category]:
        del sources[category][name]
        return save_user_sources(telegram_id, sources)
    return False


# ============ Per-User Raw Content ============

def save_user_raw_content(telegram_id: str, date: str, items: List[Dict[str, Any]]) -> bool:
    """Save raw fetched content for a user on a specific day."""
    user = get_user(telegram_id)
    if not user:
        return False

    user_content_dir = os.path.join(RAW_CONTENT_DIR, user["id"])
    _ensure_dir(user_content_dir)
    content_path = os.path.join(user_content_dir, f"{date}.json")

    data = {
        "date": date,
        "user_id": user["id"],
        "fetched_at": datetime.now().isoformat(),
        "count": len(items),
        "items": items,
    }

    return _write_json(content_path, data)


def get_user_raw_content(telegram_id: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Get raw content for a user on a specific day."""
    user = get_user(telegram_id)
    if not user:
        return {}

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    user_content_dir = os.path.join(RAW_CONTENT_DIR, user["id"])
    content_path = os.path.join(user_content_dir, f"{date}.json")
    return _read_json(content_path)


# ============ Per-User Daily Stats ============

def save_user_daily_stats(
    telegram_id: str,
    date: str,
    sources_monitored: int,
    raw_items_scanned: int,
    items_sent: int,
    status: str = "success",
    filtered_items: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """Save daily statistics for a specific user."""
    user = get_user(telegram_id)
    if not user:
        return False

    user_stats_dir = os.path.join(DAILY_STATS_DIR, user["id"])
    _ensure_dir(user_stats_dir)
    stats_path = os.path.join(user_stats_dir, f"{date}.json")

    data = {
        "date": date,
        "user_id": user["id"],
        "sources_monitored": sources_monitored,
        "raw_items_scanned": raw_items_scanned,
        "items_sent": items_sent,
        "status": status,
    }

    # Save filtered items for re-viewing the digest
    if filtered_items is not None:
        data["filtered_items"] = filtered_items

    return _write_json(stats_path, data)


def get_user_daily_stats(telegram_id: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Get daily statistics for a specific user."""
    user = get_user(telegram_id)
    if not user:
        return {}

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    user_stats_dir = os.path.join(DAILY_STATS_DIR, user["id"])
    stats_path = os.path.join(user_stats_dir, f"{date}.json")
    return _read_json(stats_path)


# ============ Data Cleanup ============

def _cleanup_old_files_in_dir(directory: str, retention_days: int) -> int:
    """
    Delete files older than retention_days in a directory.

    清理指定目录中超过保留天数的文件。
    支持 {date}.json 格式的文件名。

    Returns:
        Number of files deleted
    """
    if not os.path.exists(directory):
        return 0

    deleted_count = 0
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    try:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)

            # Skip directories (handle user subdirectories separately)
            if os.path.isdir(filepath):
                continue

            # Extract date from filename (format: {date}.json)
            if filename.endswith(".json"):
                date_part = filename.replace(".json", "")
                try:
                    # Validate date format
                    datetime.strptime(date_part, "%Y-%m-%d")
                    if date_part < cutoff_str:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.debug(f"Deleted old file: {filepath}")
                except ValueError:
                    # Not a date-formatted file, skip
                    continue
    except Exception as e:
        logger.error(f"Error cleaning up {directory}: {e}")

    return deleted_count


def cleanup_old_data() -> Dict[str, int]:
    """
    Clean up old data files based on retention settings.

    根据配置的保留天数清理过期数据：
    - raw_content: RAW_CONTENT_RETENTION_DAYS (默认7天)
    - daily_stats: DAILY_STATS_RETENTION_DAYS (默认30天)
    - feedback: FEEDBACK_RETENTION_DAYS (默认30天)

    Returns:
        Dict with cleanup counts for each category
    """
    results = {
        "raw_content": 0,
        "daily_stats": 0,
        "feedback": 0,
    }

    # Clean feedback directory
    results["feedback"] = _cleanup_old_files_in_dir(
        FEEDBACK_DIR, FEEDBACK_RETENTION_DAYS
    )

    # Clean raw_content - handle per-user subdirectories
    if os.path.exists(RAW_CONTENT_DIR):
        for item in os.listdir(RAW_CONTENT_DIR):
            item_path = os.path.join(RAW_CONTENT_DIR, item)
            if os.path.isdir(item_path):
                # User subdirectory
                results["raw_content"] += _cleanup_old_files_in_dir(
                    item_path, RAW_CONTENT_RETENTION_DAYS
                )
            elif item.endswith(".json"):
                # Legacy global files
                results["raw_content"] += _cleanup_old_files_in_dir(
                    RAW_CONTENT_DIR, RAW_CONTENT_RETENTION_DAYS
                )
                break  # Only need to run once for root level

    # Clean daily_stats - handle per-user subdirectories
    if os.path.exists(DAILY_STATS_DIR):
        for item in os.listdir(DAILY_STATS_DIR):
            item_path = os.path.join(DAILY_STATS_DIR, item)
            if os.path.isdir(item_path):
                # User subdirectory
                results["daily_stats"] += _cleanup_old_files_in_dir(
                    item_path, DAILY_STATS_RETENTION_DAYS
                )
            elif item.endswith(".json"):
                # Legacy global files
                results["daily_stats"] += _cleanup_old_files_in_dir(
                    DAILY_STATS_DIR, DAILY_STATS_RETENTION_DAYS
                )
                break

    total = sum(results.values())
    if total > 0:
        logger.info(
            f"Data cleanup complete: {results['raw_content']} raw_content, "
            f"{results['daily_stats']} daily_stats, {results['feedback']} feedback files deleted"
        )

    return results
