"""
Fast WiseFlow Client - 优化的WiseFlow客户端，专注于速度
"""
import json
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict
import asyncio
import hashlib
import time

from core.wis.async_cache import SqliteCache
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.fast_crawler import FastRssCrawler
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient
from core.custom_processes.web3digest.core.intelligent_scheduler import IntelligentScheduler

logger = setup_logger(__name__)


class FastWiseFlowClient:
    """高速WiseFlow客户端"""

    def __init__(self):
        self.cache_manager = None
        self.rss_app_client = RSSAppClient()
        self.intelligent_scheduler = IntelligentScheduler()
        self._initialized = False
        self.data_dir = Path(settings.DATA_DIR) / "raw_info"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """初始化"""
        if self._initialized:
            return

        try:
            # 初始化缓存
            cache_dir = Path(settings.DATA_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_manager = SqliteCache(db_path=str(cache_dir / "cache.db"))
            await self.cache_manager.open()

            self._initialized = True
            logger.info("Fast WiseFlow 客户端初始化成功")

        except Exception as e:
            logger.error(f"Fast WiseFlow 初始化失败: {e}")
            raise

    async def trigger_crawl(self, sources: List[Dict] = None) -> Dict:
        """
        智能高速触发抓取任务

        Args:
            sources: 信息源列表，如果为 None 则使用默认源

        Returns:
            Dict 包含抓取结果统计
        """
        if not self._initialized:
            await self.initialize()

        try:
            # 获取所有源
            if not sources:
                sources = await self._get_enabled_sources()

            # 使用智能调度器选择要抓取的源
            optimized_sources = self.intelligent_scheduler.get_optimized_crawl_list(sources)

            logger.info(f"开始智能抓取任务，原始源数量: {len(sources)}, 优化后: {len(optimized_sources)}")

            # 打印调度器统计
            self.intelligent_scheduler.print_stats()

            start_time = time.time()
            crawl_results = []

            # 使用高速爬虫
            async with FastRssCrawler(self.cache_manager) as crawler:
                # 并发抓取所有源
                try:
                    all_items, source_metrics = await crawler.crawl_multiple(optimized_sources)

                    # 更新智能调度器指标
                    for source in optimized_sources:
                        metrics = source_metrics.get(source['url'], {})
                        self.intelligent_scheduler.update_source_metrics(
                            source,
                            metrics.get('response_time', 0),
                            success=metrics.get('success', False),
                            articles_count=metrics.get('article_count', 0)
                        )

                    crawl_results = all_items
                    logger.info(f"Parallel crawl completed: {len(all_items)} items from {len(optimized_sources)} sources")

                except Exception as parallel_error:
                    # 降级到顺序处理（保持向后兼容）
                    logger.warning(f"Parallel crawl failed, falling back to sequential: {parallel_error}")

                    crawl_results = []
                    for source in optimized_sources:
                        source_start = time.time()
                        try:
                            items = await crawler.fetch_single_rss(source)
                            source_time = time.time() - source_start
                            self.intelligent_scheduler.update_source_metrics(
                                source, source_time, success=True, articles_count=len(items)
                            )
                            crawl_results.extend(items)
                            logger.debug(f"Fetched {source['name']}: {len(items)} items in {source_time:.2f}s")
                        except Exception as e:
                            source_time = time.time() - source_start
                            self.intelligent_scheduler.update_source_metrics(
                                source, source_time, success=False, articles_count=0
                            )
                            logger.warning(f"Failed to fetch {source['name']}: {e}")

            # 去重
            unique_items = self._deduplicate_items(crawl_results)

            # 保存结果
            today = date.today().isoformat()
            await self._save_items(today, unique_items)

            elapsed = time.time() - start_time
            logger.info(f"智能抓取完成: {len(unique_items)} 条内容，耗时 {elapsed:.2f}秒")

            # 保存调度器指标
            self.intelligent_scheduler.save_metrics()

            return {
                "status": 0,
                "apply_count": len(unique_items),
                "rss_sources": len(optimized_sources),
                "web_sources": 0,
                "articles_count": len(unique_items),
                "elapsed_time": elapsed,
                "items_per_second": len(unique_items) / elapsed if elapsed > 0 else 0
            }

        except Exception as e:
            logger.error(f"智能抓取失败: {e}", exc_info=True)
            return {
                "status": 1,
                "error": str(e),
                "apply_count": 0,
                "rss_sources": 0,
                "web_sources": 0,
                "articles_count": 0
            }

    async def _get_enabled_sources(self) -> List[Dict]:
        """获取启用的源"""
        all_sources = await self.rss_app_client.get_all_rss_sources()
        return [s for s in all_sources if s.get('enabled', True)]

    def _deduplicate_items(self, items: List[Dict]) -> List[Dict]:
        """去重"""
        seen = set()
        unique = []

        for item in items:
            key = item.get("url") or item.get("title")
            if key and key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    async def _save_items(self, today: str, items: List[Dict]):
        """保存抓取的内容"""
        today_file = self.data_dir / f"{today}.json"

        # 合并现有数据
        existing_items = []
        if today_file.exists():
            try:
                with open(today_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_items = data.get("items", [])
            except Exception:
                pass

        # 合并并去重
        all_items = existing_items + items
        unique_items = self._deduplicate_items(all_items)

        # 保存
        data = {
            "date": today,
            "updated_at": datetime.now().isoformat(),
            "count": len(unique_items),
            "items": unique_items
        }

        with open(today_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"保存 {len(unique_items)} 条内容到 {today_file}")

    async def get_today_info(self) -> List[Dict]:
        """获取今日信息"""
        if not self._initialized:
            await self.initialize()

        try:
            today = date.today().isoformat()
            today_file = self.data_dir / f"{today}.json"

            if today_file.exists():
                with open(today_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("items", [])

            return []

        except Exception as e:
            logger.error(f"获取今日信息失败: {e}")
            return []