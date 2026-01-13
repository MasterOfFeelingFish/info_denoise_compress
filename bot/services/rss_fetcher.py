"""
RSS Fetcher Service

Fetches content from RSS sources using httpx for async HTTP and feedparser for parsing.
Supports Twitter (via RSS.app) and website RSS feeds.

Reference: Exa search verified on 2025-01-12 for feedparser async patterns
"""
import feedparser
import httpx
import hashlib
import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from email.utils import parsedate_to_datetime

from config import DATA_DIR

logger = logging.getLogger(__name__)

# Path to shared sources.json
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")

# Default RSS Sources Configuration (used if sources.json doesn't exist)
DEFAULT_RSS_SOURCES = {
    "twitter": {
        # Configure via /sources command in Telegram Bot
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


def load_sources() -> Dict[str, Dict[str, str]]:
    """Load RSS sources from sources.json or return defaults."""
    try:
        if os.path.exists(SOURCES_FILE):
            with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                sources = json.load(f)
                logger.info(f"Loaded sources from {SOURCES_FILE}")
                return sources
    except Exception as e:
        logger.warning(f"Failed to load sources.json: {e}, using defaults")
    return DEFAULT_RSS_SOURCES


def save_sources(sources: Dict[str, Dict[str, str]]) -> bool:
    """Save RSS sources to sources.json."""
    try:
        os.makedirs(os.path.dirname(SOURCES_FILE), exist_ok=True)
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(sources, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved sources to {SOURCES_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save sources.json: {e}")
        return False


# Load sources on module import
RSS_SOURCES = load_sources()


def generate_item_id(entry: Dict[str, Any], source: str) -> str:
    """Generate a unique ID for an RSS entry."""
    # Use link or guid as primary identifier
    identifier = entry.get("id") or entry.get("link") or entry.get("title", "")
    hash_input = f"{source}:{identifier}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:12]


def parse_published_date(entry: Dict[str, Any]) -> Optional[datetime]:
    """Parse published date from RSS entry."""
    date_fields = ["published", "updated", "created"]

    for field in date_fields:
        date_str = entry.get(field)
        if date_str:
            try:
                # Try standard RFC 2822 format
                return parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                pass

            # Try ISO format
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

    # Fallback to current time if no date found
    return datetime.now(timezone.utc)


def extract_summary(entry: Dict[str, Any], max_length: int = 500) -> str:
    """Extract and clean summary from RSS entry."""
    summary = entry.get("summary", "") or entry.get("description", "")

    # Strip HTML tags (basic)
    import re
    summary = re.sub(r"<[^>]+>", "", summary)
    summary = re.sub(r"\s+", " ", summary).strip()

    # Truncate if too long
    if len(summary) > max_length:
        summary = summary[:max_length].rsplit(" ", 1)[0] + "..."

    return summary


async def fetch_single_source(
    client: httpx.AsyncClient,
    name: str,
    url: str,
    category: str,
    hours_back: int = 24
) -> List[Dict[str, Any]]:
    """Fetch and parse a single RSS source."""
    if not url:
        logger.debug(f"Skipping {name}: no URL configured")
        return []

    items = []
    # Use UTC for consistent timezone comparison
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    try:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()

        feed = feedparser.parse(response.text)

        if feed.bozo and not feed.entries:
            logger.warning(f"Feed parse error for {name}: {feed.bozo_exception}")
            return []

        for entry in feed.entries:
            published = parse_published_date(entry)

            # Filter by time - convert to UTC if timezone-aware, otherwise assume UTC
            if published:
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if published < cutoff_time:
                    continue

            item = {
                "id": generate_item_id(entry, name),
                "title": entry.get("title", "Untitled"),
                "summary": extract_summary(entry),
                "link": entry.get("link", ""),
                "source": name,
                "category": category,
                "published": published.isoformat() if published else None,
                "fetched_at": datetime.now().isoformat(),
            }
            items.append(item)

        logger.info(f"Fetched {len(items)} items from {name}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {name}: {e.response.status_code}")
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching {name}")
    except Exception as e:
        logger.error(f"Error fetching {name}: {e}")

    return items


async def fetch_all_sources(
    hours_back: int = 24,
    sources: Optional[Dict[str, Dict[str, str]]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch content from all configured RSS sources.

    Args:
        hours_back: Only include items from the past N hours
        sources: Optional custom sources dict, defaults to RSS_SOURCES

    Returns:
        List of content items sorted by published date (newest first)
    """
    if sources is None:
        sources = RSS_SOURCES

    all_items = []
    seen_ids = set()  # Track seen IDs for deduplication

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Web3DailyDigest/1.0 (+https://github.com/web3digest)"
        },
        follow_redirects=True
    ) as client:
        for category, source_urls in sources.items():
            for name, url in source_urls.items():
                items = await fetch_single_source(
                    client=client,
                    name=name,
                    url=url,
                    category=category,
                    hours_back=hours_back
                )
                # Deduplicate by ID
                for item in items:
                    item_id = item.get("id")
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        all_items.append(item)

    # Sort by published date (newest first)
    all_items.sort(
        key=lambda x: x.get("published") or "",
        reverse=True
    )

    logger.info(f"Total fetched: {len(all_items)} items from {sum(len(s) for s in sources.values())} sources")

    return all_items


async def fetch_category(
    category: str,
    hours_back: int = 24
) -> List[Dict[str, Any]]:
    """Fetch content from a specific category only."""
    if category not in RSS_SOURCES:
        logger.warning(f"Unknown category: {category}")
        return []

    return await fetch_all_sources(
        hours_back=hours_back,
        sources={category: RSS_SOURCES[category]}
    )


def add_source(category: str, name: str, url: str) -> bool:
    """Add a new RSS source and persist to sources.json."""
    global RSS_SOURCES
    if category not in RSS_SOURCES:
        RSS_SOURCES[category] = {}

    RSS_SOURCES[category][name] = url
    logger.info(f"Added source: {name} ({category})")
    return save_sources(RSS_SOURCES)


def remove_source(category: str, name: str) -> bool:
    """Remove an RSS source and persist to sources.json."""
    global RSS_SOURCES
    if category in RSS_SOURCES and name in RSS_SOURCES[category]:
        del RSS_SOURCES[category][name]
        logger.info(f"Removed source: {name} ({category})")
        return save_sources(RSS_SOURCES)
    return False


def reload_sources() -> Dict[str, Dict[str, str]]:
    """Reload sources from sources.json file."""
    global RSS_SOURCES
    RSS_SOURCES = load_sources()
    return RSS_SOURCES


def get_source_list() -> Dict[str, List[str]]:
    """Get list of all configured sources by category."""
    return {
        category: list(sources.keys())
        for category, sources in RSS_SOURCES.items()
    }


async def validate_twitter_handle(handle: str) -> Dict[str, Any]:
    """
    Validate a Twitter handle format.

    Args:
        handle: Twitter handle (with or without @)

    Returns:
        Dict with 'valid' bool and 'error' message if invalid
    """
    import re

    # Normalize handle
    handle = handle.strip()
    if handle.startswith("@"):
        handle = handle[1:]

    # Check format: 1-15 alphanumeric characters and underscores
    if not re.match(r"^[A-Za-z0-9_]{1,15}$", handle):
        return {
            "valid": False,
            "handle": handle,
            "error": "Twitter 账号格式无效。请使用 1-15 个字母、数字或下划线。"
        }

    return {
        "valid": True,
        "handle": f"@{handle}",
        "error": None
    }


async def validate_url(url: str) -> Dict[str, Any]:
    """
    Validate a URL and check if it's accessible.

    Args:
        url: URL to validate

    Returns:
        Dict with 'valid' bool, 'url' normalized, and 'error' message if invalid
    """
    import re

    url = url.strip()

    # Basic URL format check
    url_pattern = r"^https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+(:\d+)?(/.*)?$"
    if not re.match(url_pattern, url):
        return {
            "valid": False,
            "url": url,
            "error": "URL 格式无效。请使用 http:// 或 https://"
        }

    # Try to fetch the URL to verify accessibility
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code >= 400:
                return {
                    "valid": False,
                    "url": url,
                    "error": f"URL 返回错误：{response.status_code}"
                }
    except httpx.TimeoutException:
        return {
            "valid": False,
            "url": url,
            "error": "URL 超时。请检查网站是否可访问。"
        }
    except Exception as e:
        return {
            "valid": False,
            "url": url,
            "error": f"无法访问 URL：{str(e)[:50]}"
        }

    return {
        "valid": True,
        "url": url,
        "error": None
    }


async def auto_detect_rss(domain: str) -> Dict[str, Any]:
    """
    Auto-detect RSS feed URL for a domain.

    Args:
        domain: Website domain (e.g., theblock.co)

    Returns:
        Dict with 'found' bool, 'url' if found, 'error' if not
    """
    # Normalize domain
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        from urllib.parse import urlparse
        parsed = urlparse(domain)
        domain = parsed.netloc or parsed.path.split("/")[0]

    domain = domain.replace("www.", "")

    # Common RSS paths to try
    rss_paths = [
        "/rss.xml",
        "/rss",
        "/feed",
        "/feed.xml",
        "/feeds/posts/default",
        "/atom.xml",
        "/index.xml",
        "/feed/rss",
        "/blog/rss",
        "/news/rss",
        "/?feed=rss2",
        "/arc/outboundfeeds/rss/",
    ]

    base_url = f"https://{domain}"

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for path in rss_paths:
            test_url = base_url + path
            try:
                response = await client.get(test_url)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "").lower()
                    content_start = response.text[:500].lower()

                    # Check if it looks like RSS/Atom
                    if (
                        "xml" in content_type
                        or "rss" in content_type
                        or "atom" in content_type
                        or "<rss" in content_start
                        or "<feed" in content_start
                        or "<?xml" in content_start
                    ):
                        return {
                            "found": True,
                            "url": test_url,
                            "error": None
                        }
            except Exception:
                continue

    return {
        "found": False,
        "url": None,
        "error": f"未找到 {domain} 的 RSS 源。请手动输入完整 RSS 地址。"
    }


async def add_custom_source(
    category: str,
    name: str,
    url: str = ""
) -> Dict[str, Any]:
    """
    Add a custom source with validation.

    Args:
        category: 'twitter' or 'websites'
        name: Source name (Twitter handle or website name)
        url: RSS URL (required for websites, optional for Twitter)

    Returns:
        Dict with 'success' bool, 'message', and optional 'error'
    """
    if category == "twitter":
        # Validate Twitter handle
        validation = await validate_twitter_handle(name)
        if not validation["valid"]:
            return {
                "success": False,
                "message": validation["error"]
            }

        handle = validation["handle"]

        # Check if already exists
        if handle in RSS_SOURCES.get("twitter", {}):
            return {
                "success": False,
                "message": f"{handle} 已在信息源列表中。"
            }

        # If URL provided, validate it
        if url:
            url_validation = await validate_url(url)
            if not url_validation["valid"]:
                return {
                    "success": False,
                    "message": f"RSS 地址无效：{url_validation['error']}"
                }

            # Add to sources with URL
            add_source("twitter", handle, url)
            return {
                "success": True,
                "message": f"已添加 {handle}，RSS 已配置。"
            }
        else:
            # Add to sources without URL (needs manual configuration)
            add_source("twitter", handle, "")
            return {
                "success": True,
                "message": f"已添加 {handle}。\n注意：需要配置 RSS 地址才能抓取。"
            }

    elif category == "websites":
        # Check if already exists
        if name in RSS_SOURCES.get("websites", {}):
            return {
                "success": False,
                "message": f"{name} 已在信息源列表中。"
            }

        # If URL provided, validate it directly
        if url:
            validation = await validate_url(url)
            if not validation["valid"]:
                return {
                    "success": False,
                    "message": validation["error"]
                }
            final_url = url
        else:
            # No URL provided - try to auto-detect RSS from name (treat as domain)
            detection = await auto_detect_rss(name)
            if not detection["found"]:
                return {
                    "success": False,
                    "message": detection["error"]
                }
            final_url = detection["url"]

            # Update name if it looks like a domain
            if "." in name and not name.startswith("http"):
                # Extract clean name from domain
                clean_name = name.replace("www.", "").split(".")[0].title()
                name = clean_name

        # Add to sources
        add_source("websites", name, final_url)

        return {
            "success": True,
            "message": f"已添加 {name}。\nRSS: {final_url}"
        }

    else:
        return {
            "success": False,
            "message": f"未知分类：{category}"
        }
