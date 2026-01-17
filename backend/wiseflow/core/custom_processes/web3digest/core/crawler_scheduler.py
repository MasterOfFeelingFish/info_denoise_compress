"""
抓取调度器 - 定期触发信息抓取任务
"""
import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient
from core.custom_processes.web3digest.core.wiseflow_client_fast import FastWiseFlowClient
from core.custom_processes.web3digest.core.background_prefetcher import background_prefetcher
from core.custom_processes.web3digest.core.rss_history_manager import RssHistoryManager

logger = setup_logger(__name__)


class CrawlerScheduler:
    """抓取调度器"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
        self.wiseflow_client = WiseFlowClient()
        self.rss_history_manager = RssHistoryManager()
        self.fast_wiseflow_client = FastWiseFlowClient(rss_history_manager=self.rss_history_manager)
        self._running = False
    
    async def start(self):
        """启动调度器"""
        if self._running:
            return

        # 初始化高速爬虫客户端
        await self.fast_wiseflow_client.initialize()

        # 启动后台预抓取器
        await background_prefetcher.start()

        # 添加定时抓取任务（每小时抓取一次）
        self.scheduler.add_job(
            func=self._crawl_job,
            trigger=CronTrigger(minute=0),  # 每小时的第0分钟执行
            id="hourly_crawl",
            name="每小时信息抓取",
            replace_existing=True
        )

        # 添加RSS历史抓取任务（每30分钟抓取一次，保存历史数据）
        self.scheduler.add_job(
            func=self._rss_history_job,
            trigger=CronTrigger(minute="*/30"),  # 每30分钟执行
            id="rss_history_crawl",
            name="RSS历史数据抓取",
            replace_existing=True
        )

        # 添加定期清理任务（每天凌晨2点清理超过7天的旧数据）
        self.scheduler.add_job(
            func=self._cleanup_history_job,
            trigger=CronTrigger(hour=2, minute=0),  # 每天凌晨2点执行
            id="cleanup_rss_history",
            name="清理RSS历史数据",
            replace_existing=True
        )

        # 启动调度器
        self.scheduler.start()
        self._running = True

        logger.info("抓取调度器已启动，每小时执行一次抓取任务，每30分钟执行RSS历史抓取，后台预抓取已启用")
    
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return

        # 停止后台预抓取器
        await background_prefetcher.stop()

        self.scheduler.shutdown()
        self._running = False
        logger.info("抓取调度器已停止")
    
    async def _crawl_job(self):
        """抓取任务（优先使用预抓取数据）"""
        logger.info("开始执行定时抓取任务...")

        try:
            # 首先检查是否有可用的预抓取数据
            if background_prefetcher.is_prefetch_available():
                logger.info("使用预抓取数据...")
                prefetched_items = await background_prefetcher.get_prefetched_items()

                # 保存预抓取的数据
                today = datetime.now().date().isoformat()
                await self.fast_wiseflow_client._save_items(today, prefetched_items)

                logger.info(f"使用预抓取数据完成: {len(prefetched_items)} 条内容")

                # 返回预抓取结果
                return {
                    "status": 0,
                    "apply_count": len(prefetched_items),
                    "rss_sources": len(prefetched_items),  # 估算
                    "web_sources": 0,
                    "articles_count": len(prefetched_items),
                    "elapsed_time": 0.1,  # 几乎瞬时
                    "items_per_second": len(prefetched_items) / 0.1
                }

            # 没有预抓取数据，执行正常抓取
            logger.info("没有预抓取数据，执行正常抓取...")
            result = await self.fast_wiseflow_client.trigger_crawl()

            logger.info(
                f"抓取任务完成: "
                f"状态={result['status']}, "
                f"处理数量={result['apply_count']}, "
                f"RSS源={result['rss_sources']}, "
                f"文章数={result['articles_count']}, "
                f"耗时={result.get('elapsed_time', 0):.2f}秒"
            )

            if result.get("warnings"):
                logger.warning(f"抓取警告: {result['warnings']}")

        except Exception as e:
            logger.error(f"抓取任务失败: {e}", exc_info=True)
            # 降级使用普通爬虫
            logger.info("尝试使用普通爬虫...")
            try:
                result = await self.wiseflow_client.trigger_crawl()
                logger.info(f"普通爬虫完成: {result}")
            except Exception as e2:
                logger.error(f"普通爬虫也失败: {e2}", exc_info=True)

    async def _rss_history_job(self):
        """RSS历史抓取任务（每30分钟执行）"""
        logger.info("开始执行RSS历史抓取任务...")

        try:
            # 获取所有启用的RSS源
            sources = await self.fast_wiseflow_client._get_enabled_sources()

            if not sources:
                logger.warning("没有启用的RSS源，跳过历史抓取")
                return

            logger.info(f"开始抓取 {len(sources)} 个RSS源的历史数据...")

            # 使用FastRssCrawler抓取（会自动保存到历史存储）
            from core.custom_processes.web3digest.core.fast_crawler import FastRssCrawler
            async with FastRssCrawler(
                self.fast_wiseflow_client.cache_manager,
                rss_history_manager=self.rss_history_manager
            ) as crawler:
                # 并发抓取所有源
                all_items, source_metrics = await crawler.crawl_multiple(sources)

                logger.info(
                    f"RSS历史抓取完成: {len(sources)} 个源, "
                    f"{len(all_items)} 条数据已保存到历史存储"
                )

        except Exception as e:
            logger.error(f"RSS历史抓取任务失败: {e}", exc_info=True)

    async def _cleanup_history_job(self):
        """清理RSS历史数据任务（每天执行）"""
        logger.info("开始清理超过7天的RSS历史数据...")

        try:
            cleaned_count = await self.rss_history_manager.cleanup_old_items(days=7)

            logger.info(f"RSS历史数据清理完成: 清理了 {cleaned_count} 条旧数据")

        except Exception as e:
            logger.error(f"清理RSS历史数据失败: {e}", exc_info=True)
    
    async def trigger_manual_crawl(self) -> dict:
        """手动触发抓取（用于测试）"""
        logger.info("手动触发抓取任务...")
        # 使用高速爬虫
        try:
            result = await self.fast_wiseflow_client.trigger_crawl()
            logger.info(f"高速爬虫手动触发完成: {result}")
            return result
        except Exception as e:
            logger.error(f"高速爬虫手动触发失败: {e}")
            # 降级使用普通爬虫
            logger.info("降级使用普通爬虫...")
            return await self.wiseflow_client.trigger_crawl()
