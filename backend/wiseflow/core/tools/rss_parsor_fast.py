"""
Fast RSS Parser - 优化的RSS解析器，专注于速度
"""
import httpx
import feedparser
from core.async_logger import wis_logger
from core.wis import CrawlResult, SqliteCache
from typing import List, Tuple
from core.tools.general_utils import normalize_publish_date
import asyncio
from datetime import datetime

# 优化的超时配置 - 根据源的速度表现
FAST_SOURCES = {
    "cointelegraph.com": 2,
    "coindesk.com": 2,
    "decrypt.co": 2,
    "chainfeeds.me": 3,
    "defirate.com": 3,
    "substack.com": 3,
    "theblock.co": 2,
    "chaincatcher.com": 3,
    "techflowpost.com": 3,
    "foresightnews.pro": 2,
    "twitter.com": 2,
    "x.com": 2,
}

DEFAULT_TIMEOUT = 3  # 降低默认超时
MAX_RETRIES = 1

# 连接池配置
limits = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=50,
    keepalive_expiry=30
)

async def fetch_rss_fast(url, existings: set = set(), cache_manager: SqliteCache = None) -> Tuple[List[CrawlResult], str, dict]:
    """优化的RSS获取函数，注重速度"""

    parsed = None  # 初始化 parsed 变量，避免作用域问题

    # 检查缓存
    if cache_manager:
        entries = await cache_manager.get(url, namespace='rss')
        if entries == '**empty**':
            return [], '', {}
        if entries:
            wis_logger.debug(f"RSS cache hit for {url}")
    else:
        entries = None

    if not entries:
        # 根据域名确定超时时间
        domain = url.split('/')[2].replace('www.', '')
        timeout = FAST_SOURCES.get(domain, DEFAULT_TIMEOUT)

        try:
            # 使用连接池的客户端
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                follow_redirects=True
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content

        except asyncio.TimeoutError:
            wis_logger.warning(f"RSS timeout ({timeout}s) for {url}")
            return [], '', {}
        except Exception as e:
            wis_logger.debug(f"RSS fetch failed for {url}: {str(e)}")
            return [], '', {}

        # 快速解析
        try:
            parsed = feedparser.parse(content)
            if parsed.get("bozo", False):
                # 轻微的解析错误也接受，继续处理
                if "not well-formed" in str(parsed.get('bozo_exception', '')).lower():
                    wis_logger.debug(f"XML format issue for {url}, continuing...")
                else:
                    wis_logger.warning(f"RSS parse error for {url}: {parsed.get('bozo_exception', '')}")

            entries = parsed.entries

            # 缓存结果 - 缩短缓存时间以获取更新内容
            if cache_manager and entries:
                await cache_manager.set(url, entries, 60*6, namespace='rss')  # 6小时缓存

        except Exception as e:
            wis_logger.error(f"RSS processing failed for {url}: {str(e)}")
            return [], '', {}

    # 快速处理条目
    results = []
    link_dict = {}
    feed_title = getattr(parsed, 'feed', {}).get('title', '') if parsed else ''

    # 限制处理的文章数量以提高速度
    max_entries = min(len(entries), 50)  # 每个源最多50篇文章

    for i, entry in enumerate(entries[:max_entries]):
        try:
            article_url = entry.get('link', url)
            if article_url in existings:
                continue

            # 快速提取内容
            content = ''

            # 优先使用 summary/description
            content = entry.get('summary', '') or entry.get('description', '')

            # 如果内容太短，尝试其他字段
            if len(content) < 100:
                if 'content' in entry and entry['content']:
                    content = entry['content'][0].get('value', content)

            # 跳过无内容的文章
            if not content or len(content.strip()) < 50:
                continue

            # 快速提取其他字段
            title = entry.get('title', '') or feed_title or 'Untitled'
            author = entry.get('author', '')[:100]  # 限制长度
            publish_date = normalize_publish_date(entry.get('published', ''))

            # 创建结果
            results.append(CrawlResult(
                url=article_url,
                html=content,
                title=title,
                author=author,
                publish_date=publish_date,
            ))

        except Exception as e:
            wis_logger.debug(f"Error processing entry {i} from {url}: {str(e)}")
            continue

    wis_logger.debug(f"Fast RSS parse: {url} -> {len(results)} items (from {max_entries} entries)")
    return results, feed_title, link_dict

# 向后兼容的别名
fetch_rss_optimized = fetch_rss_fast