"""
Background Prefetcher - 后台预抓取服务
在系统空闲时预先抓取内容，提高响应速度
"""
import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import json

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.fast_crawler import FastRssCrawler
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient

logger = setup_logger(__name__)


class BackgroundPrefetcher:
    """后台预抓取器"""

    def __init__(self, cache_manager=None):
        self.cache_manager = cache_manager
        self.rss_app_client = RSSAppClient()
        self._running = False
        self._prefetch_schedule_file = Path("data/web3digest/prefetch_schedule.json")
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        self._prefetch_schedule_file.parent.mkdir(parents=True, exist_ok=True)

    async def start(self):
        """启动后台预抓取服务"""
        if self._running:
            return

        self._running = True
        logger.info("Starting background prefetcher...")

        # 启动后台任务
        asyncio.create_task(self._prefetch_worker())

    async def stop(self):
        """停止后台预抓取服务"""
        self._running = False
        logger.info("Stopping background prefetcher...")

    async def _prefetch_worker(self):
        """后台预抓取工作线程"""
        while self._running:
            try:
                # 检查是否是预抓取时间（凌晨2-6点）
                current_hour = datetime.now().hour
                if 2 <= current_hour <= 6:
                    logger.info("Starting background prefetch...")
                    await self._do_prefetch()

                    # 预抓取完成后，等待1小时再检查
                    await asyncio.sleep(3600)
                else:
                    # 不是预抓取时间，等待10分钟再检查
                    await asyncio.sleep(600)

            except Exception as e:
                logger.error(f"Background prefetch error: {e}")
                await asyncio.sleep(300)  # 出错后等待5分钟

    async def _do_prefetch(self):
        """执行预抓取"""
        try:
            # 获取所有启用的源
            all_sources = await self.rss_app_client.get_all_rss_sources()
            enabled_sources = [s for s in all_sources if s.get('enabled', True)]

            logger.info(f"Background prefetching {len(enabled_sources)} sources...")

            # 使用条件请求（ETag/Last-Modified）
            prefetch_results = []

            async with FastRssCrawler(self.cache_manager) as crawler:
                for source in enabled_sources:
                    try:
                        # 检查缓存中是否有ETag或Last-Modified
                        etag = await self._get_etag(source['url'])
                        last_modified = await self._get_last_modified(source['url'])

                        # 如果源支持条件请求，使用它们
                        if etag or last_modified:
                            items = await self._conditional_fetch(crawler, source, etag, last_modified)
                        else:
                            # 不支持条件请求，正常抓取但限制文章数量
                            items = await crawler.fetch_single_rss(source)

                        if items:
                            prefetch_results.append({
                                'source': source['name'],
                                'url': source['url'],
                                'articles': len(items),
                                'timestamp': datetime.now().isoformat()
                            })
                            logger.debug(f"Prefetched {source['name']}: {len(items)} items")

                    except Exception as e:
                        logger.warning(f"Failed to prefetch {source['name']}: {e}")

            # 保存预抓取结果
            await self._save_prefetch_results(prefetch_results)

            logger.info(f"Background prefetch completed: {len(prefetch_results)} sources, {sum(r['articles'] for r in prefetch_results)} items")

        except Exception as e:
            logger.error(f"Background prefetch failed: {e}")

    async def _conditional_fetch(self, crawler: FastRssCrawler, source: dict, etag: Optional[str], last_modified: Optional[str]) -> List[Dict]:
        """执行条件抓取"""
        url = source['url']
        headers = {}

        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified

        try:
            # 尝试条件请求
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(url)

                if resp.status_code == 304:  # Not Modified
                    logger.debug(f"{source['name']} not modified, skipping")
                    return []

                # 更新ETag和Last-Modified
                new_etag = resp.headers.get('ETag')
                new_last_modified = resp.headers.get('Last-Modified')

                if new_etag:
                    await self._save_etag(url, new_etag)
                if new_last_modified:
                    await self._save_last_modified(url, new_last_modified)

                # 解析内容
                parsed = feedparser.parse(resp.content)
                entries = parsed.entries[:30]  # 限制数量

                # 转换为标准格式
                items = []
                for entry in entries:
                    items.append({
                        'id': self._generate_id(entry.get('link', '')),
                        'title': entry.get('title', ''),
                        'content': entry.get('summary', '') or entry.get('description', ''),
                        'source': source.get('name', 'Unknown'),
                        'source_category': source.get('category', ''),
                        'url': entry.get('link', ''),
                        'publish_time': entry.get('published', ''),
                        'crawl_time': datetime.now().isoformat(),
                        'metadata': {
                            'author': entry.get('author', ''),
                        }
                    })

                return items

        except Exception as e:
            logger.warning(f"Conditional fetch failed for {source['name']}, falling back to normal fetch: {e}")
            # 回退到正常抓取
            return await crawler.fetch_single_rss(source)

    def _generate_id(self, url: str) -> str:
        """生成唯一ID"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]

    async def _get_etag(self, url: str) -> Optional[str]:
        """获取保存的ETag"""
        if not self.cache_manager:
            return None
        return await self.cache_manager.get(f"etag:{url}", namespace='prefetch')

    async def _save_etag(self, url: str, etag: str):
        """保存ETag"""
        if self.cache_manager:
            await self.cache_manager.set(f"etag:{url}", etag, 86400, namespace='prefetch')  # 24小时

    async def _get_last_modified(self, url: str) -> Optional[str]:
        """获取保存的Last-Modified"""
        if not self.cache_manager:
            return None
        return await self.cache_manager.get(f"lastmod:{url}", namespace='prefetch')

    async def _save_last_modified(self, url: str, last_modified: str):
        """保存Last-Modified"""
        if self.cache_manager:
            await self.cache_manager.set(f"lastmod:{url}", last_modified, 86400, namespace='prefetch')  # 24小时

    async def _save_prefetch_results(self, results: List[Dict]):
        """保存预抓取结果"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'results': results,
                'total_sources': len(results),
                'total_articles': sum(r['articles'] for r in results)
            }

            # 保存到文件
            with open(self._prefetch_schedule_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved prefetch results for {len(results)} sources")

        except Exception as e:
            logger.error(f"Failed to save prefetch results: {e}")

    def get_prefetch_stats(self) -> Optional[Dict]:
        """获取预抓取统计"""
        try:
            if self._prefetch_schedule_file.exists():
                with open(self._prefetch_schedule_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load prefetch stats: {e}")
        return None

    def is_prefetch_available(self) -> bool:
        """检查是否有可用的预抓取数据"""
        stats = self.get_prefetch_stats()
        if not stats:
            return False

        # 检查数据是否过期（超过2小时）
        prefetch_time = datetime.fromisoformat(stats['timestamp'])
        if datetime.now() - prefetch_time > timedelta(hours=2):
            return False

        return True

    async def get_prefetched_items(self) -> List[Dict]:
        """获取预抓取的项目"""
        stats = self.get_prefetch_stats()
        if not stats:
            return []

        # 合并所有预抓取的文章
        all_items = []
        for result in stats['results']:
            # 这里可以添加更复杂的逻辑，比如只返回最新的文章
            # 目前简单返回所有预抓取的文章
            all_items.extend(result.get('articles', []))

        return all_items

# 全局后台预抓取器实例
background_prefetcher = BackgroundPrefetcher()