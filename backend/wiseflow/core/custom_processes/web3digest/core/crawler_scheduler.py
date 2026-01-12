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

logger = setup_logger(__name__)


class CrawlerScheduler:
    """抓取调度器"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
        self.wiseflow_client = WiseFlowClient()
        self._running = False
    
    async def start(self):
        """启动调度器"""
        if self._running:
            return
        
        # 添加定时抓取任务（每小时抓取一次）
        self.scheduler.add_job(
            func=self._crawl_job,
            trigger=CronTrigger(minute=0),  # 每小时的第0分钟执行
            id="hourly_crawl",
            name="每小时信息抓取",
            replace_existing=True
        )
        
        # 启动调度器
        self.scheduler.start()
        self._running = True
        
        logger.info("抓取调度器已启动，每小时执行一次抓取任务")
    
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self.scheduler.shutdown()
        self._running = False
        logger.info("抓取调度器已停止")
    
    async def _crawl_job(self):
        """抓取任务（使用所有用户的启用源）"""
        logger.info("开始执行定时抓取任务...")
        
        try:
            # 获取所有启用的信息源（合并所有用户的配置）
            # 简化：使用默认源，未来可以优化为按用户分别抓取
            result = await self.wiseflow_client.trigger_crawl()
            
            logger.info(
                f"抓取任务完成: "
                f"状态={result['status']}, "
                f"处理数量={result['apply_count']}, "
                f"RSS源={result['rss_sources']}, "
                f"文章数={result['articles_count']}"
            )
            
            if result.get("warnings"):
                logger.warning(f"抓取警告: {result['warnings']}")
            
        except Exception as e:
            logger.error(f"抓取任务失败: {e}", exc_info=True)
    
    async def trigger_manual_crawl(self) -> dict:
        """手动触发抓取（用于测试）"""
        logger.info("手动触发抓取任务...")
        return await self.wiseflow_client.trigger_crawl()
