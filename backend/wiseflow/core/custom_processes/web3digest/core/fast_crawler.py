"""
Fast RSS Crawler - 高性能RSS爬虫
"""
import asyncio
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import aiohttp
import feedparser
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.wis.async_cache import SqliteCache
from core.wis import CrawlResult

# 使用 web3digest 统一日志系统
logger = setup_logger(__name__)


class FastRssCrawler:
    """高性能RSS爬虫"""

    def __init__(self, cache_manager: Optional[SqliteCache] = None):
        self.cache_manager = cache_manager
        self.timeout_config = {
            # 快速源 - 3秒超时
            'cointelegraph.com': 3,
            'coindesk.com': 3,
            'decrypt.co': 3,
            'chainfeeds.me': 3,
            'defirate.com': 3,
            # 中等速度源 - 5秒超时
            'substack.com': 5,
            'techflowpost.com': 5,
            'chaincatcher.com': 5,
            # 默认超时
            'default': 5
        }
        self.max_concurrent = 50  # 最大并发数（提升以支持更多源）
        self.session = None

    async def __aenter__(self):
        """异步上下文管理器"""
        connector = aiohttp.TCPConnector(
            limit=50,  # 总连接池大小
            limit_per_host=10,  # 每个主机的连接数
            ttl_dns_cache=300,  # DNS缓存时间
            use_dns_cache=True,
        )

        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Web3Digest/1.0; +https://github.com/your-repo)'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭会话"""
        if self.session:
            await self.session.close()

    def _get_timeout(self, url: str) -> int:
        """根据URL获取超时时间"""
        domain = url.split('/')[2].replace('www.', '')
        for key, timeout in self.timeout_config.items():
            if key in domain:
                return timeout
        return self.timeout_config['default']

    async def fetch_single_rss(self, source: Dict) -> List[Dict]:
        """快速获取单个RSS源"""
        url = source['url']
        name = source.get('name', 'Unknown')
        category = source.get('category', '')

        start_time = time.time()

        try:
            # 检查缓存
            if self.cache_manager:
                cached = await self.cache_manager.get(url, namespace='rss')
                if cached and cached != '**empty**':
                    logger.debug(f"Cache hit for {name}")
                    return self._parse_cached_entries(cached, source)

            # 获取超时时间
            timeout = self._get_timeout(url)

            # 快速获取RSS内容
            async with asyncio.timeout(timeout):
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"RSS {name} returned status {response.status}")
                        return []

                    content = await response.read()

            # 快速解析
            parsed = feedparser.parse(content)
            entries = parsed.entries

            # 缓存结果 - 缩短缓存时间
            if self.cache_manager and entries:
                await self.cache_manager.set(url, entries, 60*2, namespace='rss')  # 2小时缓存

            # 转换为标准格式
            items = []
            feed_title = getattr(parsed.feed, 'title', name)

            # 限制处理数量以提高速度
            max_items = min(len(entries), 30)

            for entry in entries[:max_items]:
                try:
                    item = self._convert_entry_to_item(entry, source, feed_title)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug(f"Error converting entry from {name}: {e}")
                    continue

            elapsed = time.time() - start_time
            logger.info(f"Fast fetch: {name} -> {len(items)} items in {elapsed:.2f}s")

            return items

        except asyncio.TimeoutError:
            logger.warning(f"RSS timeout ({timeout}s) for {name}")
            return []
        except Exception as e:
            logger.debug(f"RSS fetch error for {name}: {str(e)}")
            return []

    def _parse_cached_entries(self, entries: List, source: Dict) -> List[Dict]:
        """解析缓存的条目"""
        items = []
        name = source.get('name', 'Unknown')
        category = source.get('category', '')

        for entry in entries[:30]:  # 限制数量
            try:
                item = {
                    'id': self._generate_id(entry.get('link', '')),
                    'title': entry.get('title', ''),
                    'content': entry.get('summary', '') or entry.get('description', ''),
                    'source': name,
                    'source_category': category,
                    'url': entry.get('link', ''),
                    'publish_time': entry.get('published', ''),
                    'crawl_time': datetime.now().isoformat(),
                    'metadata': {
                        'author': entry.get('author', ''),
                    }
                }
                items.append(item)
            except Exception as e:
                logger.debug(f"Error parsing cached entry from {name}: {e}")
                continue

        return items

    def _convert_entry_to_item(self, entry, source: Dict, feed_title: str) -> Optional[Dict]:
        """转换条目到标准格式"""
        try:
            url = entry.get('link', '')
            if not url:
                return None

            # 快速提取内容
            content = entry.get('summary', '') or entry.get('description', '')
            if len(content) < 50:
                # 内容太短，跳过
                return None

            return {
                'id': self._generate_id(url),
                'title': entry.get('title', feed_title)[:200],  # 限制长度
                'content': content[:2000],  # 限制长度
                'source': source.get('name', 'Unknown'),
                'source_category': source.get('category', ''),
                'url': url,
                'publish_time': entry.get('published', ''),
                'crawl_time': datetime.now().isoformat(),
                'metadata': {
                    'author': entry.get('author', '')[:100],
                }
            }
        except Exception:
            return None

    def _generate_id(self, url: str) -> str:
        """生成唯一ID"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]

    async def crawl_multiple(self, sources: List[Dict]) -> Tuple[List[Dict], Dict[str, Dict]]:
        """
        并发抓取多个RSS源

        Returns:
            Tuple of (all_items, source_metrics)
            source_metrics = {
                'source_url': {
                    'response_time': float,
                    'success': bool,
                    'article_count': int,
                    'error': Optional[str]
                }
            }
        """
        if not sources:
            return [], {}

        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(self.max_concurrent)
        source_metrics = {}

        async def fetch_with_semaphore(source):
            async with semaphore:
                start_time = time.time()
                try:
                    items = await self.fetch_single_rss(source)
                    elapsed = time.time() - start_time

                    # 存储指标
                    source_metrics[source['url']] = {
                        'response_time': elapsed,
                        'success': True,
                        'article_count': len(items),
                        'error': None
                    }
                    return items

                except Exception as e:
                    elapsed = time.time() - start_time
                    source_metrics[source['url']] = {
                        'response_time': elapsed,
                        'success': False,
                        'article_count': 0,
                        'error': str(e)
                    }
                    logger.warning(f"Source {source.get('name', 'Unknown')} failed: {e}")
                    return []

        # 并发执行所有任务
        tasks = [fetch_with_semaphore(source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # 合并结果并统计
        all_items = []
        success_count = 0
        error_count = 0

        for result in results:
            if result:
                all_items.extend(result)
                success_count += 1
            else:
                error_count += 1

        logger.info(f"Fast crawl completed: {success_count} sources, {error_count} errors, {len(all_items)} items")

        return all_items, source_metrics