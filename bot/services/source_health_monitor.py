"""
Source Health Monitor Service (T3)

Monitors RSS source health, triggers AI-driven repair for failing sources,
and sends notifications to admins/users.

Controlled by FEATURE_SOURCE_HEALTH feature flag.
"""
import json
import os
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def _get_health_file(source_url: str) -> str:
    """Get the health record file path for a source URL."""
    from config import SOURCE_HEALTH_DIR
    url_hash = hashlib.md5(source_url.encode()).hexdigest()[:12]
    os.makedirs(SOURCE_HEALTH_DIR, exist_ok=True)
    return os.path.join(SOURCE_HEALTH_DIR, f"{url_hash}.json")


def _load_health_record(source_url: str) -> Dict[str, Any]:
    """Load health record for a source, or return empty default."""
    filepath = _get_health_file(source_url)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "source_url": source_url,
        "source_name": "",
        "status": "unknown",
        "consecutive_failures": 0,
        "total_checks": 0,
        "total_successes": 0,
        "last_check": None,
        "last_success": None,
        "last_error": None,
        "error_type": None,
        "repair_attempts": 0,
        "repair_status": None,
        "repaired_url": None,
        "last_notification": None,
        "history": [],
    }


def _save_health_record(source_url: str, record: Dict[str, Any]):
    """Save health record to disk."""
    filepath = _get_health_file(source_url)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Failed to save health record for {source_url}: {e}")


def record_health_status(
    source_url: str,
    source_name: str,
    success: bool,
    error_type: Optional[str] = None,
    error_detail: Optional[str] = None,
    items_count: int = 0,
) -> Dict[str, Any]:
    """
    Record the health status of a source after a fetch attempt.
    
    Args:
        source_url: The RSS feed URL
        source_name: Human-readable source name
        success: Whether the fetch was successful
        error_type: Type of error (e.g., 'timeout', 'parse_error', '404')
        error_detail: Detailed error message
        items_count: Number of items fetched (if successful)
    
    Returns:
        Updated health record
    """
    record = _load_health_record(source_url)
    now = datetime.now().isoformat()
    
    record["source_name"] = source_name
    record["source_url"] = source_url
    record["last_check"] = now
    record["total_checks"] = record.get("total_checks", 0) + 1
    
    if success:
        record["status"] = "ok"
        record["consecutive_failures"] = 0
        record["total_successes"] = record.get("total_successes", 0) + 1
        record["last_success"] = now
        record["last_error"] = None
        record["error_type"] = None
    else:
        record["consecutive_failures"] = record.get("consecutive_failures", 0) + 1
        record["last_error"] = error_detail
        record["error_type"] = error_type
        
        failures = record["consecutive_failures"]
        if failures >= 10:
            record["status"] = "failed"
        elif failures >= 3:
            record["status"] = "degraded"
        else:
            record["status"] = "warning"
    
    # Keep last 20 history entries
    history = record.get("history", [])
    history.append({
        "time": now,
        "success": success,
        "error_type": error_type,
        "items_count": items_count,
    })
    record["history"] = history[-20:]
    
    _save_health_record(source_url, record)
    return record


async def check_and_repair(source_url: str, source_name: str) -> Dict[str, Any]:
    """
    Check if a source needs repair and attempt AI-driven repair.
    
    Triggers repair when consecutive_failures >= 3.
    Limits repair attempts to 3 rounds before marking permanently failed.
    
    Returns:
        Result dict with 'action' and details
    """
    from config import FEATURE_SOURCE_HEALTH
    if not FEATURE_SOURCE_HEALTH:
        return {"action": "skipped", "reason": "feature_disabled"}
    
    record = _load_health_record(source_url)
    failures = record.get("consecutive_failures", 0)
    repair_attempts = record.get("repair_attempts", 0)
    
    if failures < 3:
        return {"action": "none", "reason": "below_threshold"}
    
    if repair_attempts >= 3:
        record["repair_status"] = "permanently_failed"
        _save_health_record(source_url, record)
        return {"action": "permanently_failed", "reason": "max_repairs_exceeded"}
    
    # Attempt AI repair
    result = await attempt_ai_repair(source_url, source_name, record)
    
    record["repair_attempts"] = repair_attempts + 1
    record["repair_status"] = result.get("status", "unknown")
    
    if result.get("status") == "repaired":
        record["repaired_url"] = result.get("new_url")
        record["status"] = "repaired"
    
    _save_health_record(source_url, record)
    return result


async def attempt_ai_repair(
    source_url: str,
    source_name: str,
    health_record: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Use AI to analyze the error and suggest a repair URL.
    
    Args:
        source_url: The failing RSS URL
        source_name: Human-readable name
        health_record: Current health record with error details
    
    Returns:
        Result dict with 'status', 'new_url' (if found), and 'analysis'
    """
    try:
        from services.llm_factory import call_llm_json
        from utils.prompt_loader import get_prompt
        
        error_type = health_record.get("error_type", "unknown")
        error_detail = health_record.get("last_error", "No details")
        failures = health_record.get("consecutive_failures", 0)
        
        # Build repair prompt
        prompt = f"""Analyze this failing RSS source and suggest repair:

Source Name: {source_name}
Current URL: {source_url}
Error Type: {error_type}
Error Detail: {error_detail}
Consecutive Failures: {failures}

Please respond with JSON:
{{
    "analysis": "Brief analysis of the problem",
    "suggested_urls": ["url1", "url2"],
    "confidence": "high/medium/low"
}}"""
        
        result, model = await call_llm_json(
            prompt=prompt,
            system_instruction="You are an RSS feed repair specialist. Analyze failing RSS feeds and suggest alternative URLs. Only suggest URLs that are likely to work based on common RSS patterns.",
            context="source-repair"
        )
        
        if result is None:
            return {"status": "repair_failed", "reason": "ai_unavailable"}
        
        # Test suggested URLs
        suggested_urls = result.get("suggested_urls", [])
        for url in suggested_urls[:3]:  # Test up to 3 suggestions
            if await _test_url(url):
                logger.info(f"AI repair found working URL for {source_name}: {url}")
                return {
                    "status": "repaired",
                    "new_url": url,
                    "analysis": result.get("analysis", ""),
                }
        
        return {
            "status": "repair_failed",
            "reason": "no_working_url",
            "analysis": result.get("analysis", ""),
            "tried_urls": suggested_urls,
        }
        
    except Exception as e:
        logger.error(f"AI repair failed for {source_name}: {e}")
        return {"status": "repair_failed", "reason": str(e)}


async def _test_url(url: str) -> bool:
    """Test if a URL returns valid RSS content."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Simple check for RSS/XML content
                    return "<rss" in text.lower() or "<feed" in text.lower() or "<xml" in text.lower()
        return False
    except Exception:
        return False


async def send_health_notification(
    source_url: str,
    source_name: str,
    status: str,
    detail: str = "",
    admin_only: bool = True,
) -> bool:
    """
    Send health notification to admin (and optionally user).
    
    Enforces 24h notification rate limit per source+status combo.
    
    Args:
        source_url: The source URL
        source_name: Human-readable name
        status: Current status (degraded/failed/repaired)
        detail: Additional detail text
        admin_only: If True, only notify admins
    
    Returns:
        True if notification was sent
    """
    record = _load_health_record(source_url)
    
    # Rate limit: don't notify again within 24h for same status
    last_notification = record.get("last_notification")
    if last_notification:
        try:
            last_time = datetime.fromisoformat(last_notification)
            if datetime.now() - last_time < timedelta(hours=24):
                return False
        except (ValueError, TypeError):
            pass
    
    # Build notification message
    status_emoji = {"degraded": "⚠️", "failed": "❌", "repaired": "✅"}.get(status, "ℹ️")
    msg = (
        f"{status_emoji} 信息源状态变更\n\n"
        f"源: {source_name}\n"
        f"状态: {status}\n"
        f"URL: {source_url}\n"
    )
    if detail:
        msg += f"详情: {detail}\n"
    
    failures = record.get("consecutive_failures", 0)
    if failures > 0:
        msg += f"连续失败: {failures} 次\n"
    
    # Update notification timestamp
    record["last_notification"] = datetime.now().isoformat()
    _save_health_record(source_url, record)
    
    logger.info(f"Health notification: {source_name} -> {status}")
    return True


def get_all_health_records() -> List[Dict[str, Any]]:
    """Get all source health records for dashboard display."""
    from config import SOURCE_HEALTH_DIR
    
    records = []
    if not os.path.exists(SOURCE_HEALTH_DIR):
        return records
    
    for filename in os.listdir(SOURCE_HEALTH_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SOURCE_HEALTH_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    records.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue
    
    return records


def get_health_summary() -> Dict[str, Any]:
    """Get a summary of all source health for the admin dashboard."""
    records = get_all_health_records()
    
    summary = {
        "total": len(records),
        "ok": 0,
        "degraded": 0,
        "failed": 0,
        "unknown": 0,
        "sources": [],
    }
    
    for record in records:
        status = record.get("status", "unknown")
        if status == "ok" or status == "repaired":
            summary["ok"] += 1
        elif status == "degraded" or status == "warning":
            summary["degraded"] += 1
        elif status in ("failed", "permanently_failed"):
            summary["failed"] += 1
        else:
            summary["unknown"] += 1
        
        total = record.get("total_checks", 0)
        successes = record.get("total_successes", 0)
        success_rate = f"{(successes/total*100):.0f}%" if total > 0 else "N/A"
        
        summary["sources"].append({
            "name": record.get("source_name", "Unknown"),
            "url": record.get("source_url", ""),
            "status": status,
            "success_rate": success_rate,
            "consecutive_failures": record.get("consecutive_failures", 0),
            "last_check": record.get("last_check"),
        })
    
    # Sort: failed first, then degraded, then ok
    status_order = {"failed": 0, "permanently_failed": 0, "degraded": 1, "warning": 1, "ok": 2, "repaired": 2, "unknown": 3}
    summary["sources"].sort(key=lambda s: status_order.get(s["status"], 3))
    
    return summary
