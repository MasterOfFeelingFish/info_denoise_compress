"""
WiseFlow 客户端 - 集成 WiseFlow 信息抓取能力
"""
import json
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import asyncio

# 使用标准导入，不再需要 sys.path.append
from core.async_database import AsyncDatabaseManager
from core.wis import (
    AsyncWebCrawler,
    SqliteCache,
    ExtractManager
)
from core.tools.rss_parsor import fetch_rss
from core.general_process import main_process as wiseflow_main_process

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.config import DefaultRSSSources
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient

logger = setup_logger(__name__)


class WiseFlowClient:
    """WiseFlow 客户端"""
    
    def __init__(self):
        self.db_manager: Optional[AsyncDatabaseManager] = None
        self.cache_manager = None
        self.crawlers = None
        self.rss_app_client = RSSAppClient()
        self._initialized = False
    
    async def initialize(self):
        """初始化 WiseFlow"""
        if self._initialized:
            return
        
        try:
            # 初始化数据库管理器
            self.db_manager = AsyncDatabaseManager()
            await self.db_manager.initialize()
            
            # 初始化缓存管理器
            self.cache_manager = SqliteCache()
            
            # 初始化爬虫
            self.crawlers = {}
            await self._setup_crawlers()
            
            self._initialized = True
            logger.info("WiseFlow 客户端初始化成功")
            
        except Exception as e:
            logger.error(f"WiseFlow 初始化失败: {e}")
            raise
    
    async def _setup_crawlers(self):
        """设置爬虫"""
        # Web 爬虫
        self.crawlers["web"] = AsyncWebCrawler(
            db_manager=self.db_manager,
            cache_manager=self.cache_manager
        )
        
        # RSS 通过 fetch_rss 函数处理，不需要单独的爬虫类
        # TODO: 添加其他类型的爬虫
    
    async def get_today_info(self) -> List[Dict]:
        """获取今日抓取的信息"""
        if not self._initialized:
            await self.initialize()
        
        try:
            # 从数据库获取今日信息
            today = date.today().isoformat()
            
            # 查询今日的所有信息
            query = f"""
            SELECT id, title, content, source, url, publish_time, metadata
            FROM info_items
            WHERE date(created_at) = '{today}'
            ORDER BY created_at DESC
            """
            
            results = await self.db_manager.fetch_all(query)
            
            # 转换为标准格式
            info_list = []
            for row in results:
                info_list.append({
                    "id": row["id"],
                    "title": row["title"] or "无标题",
                    "content": row["content"] or "",
                    "source": row["source"] or "未知",
                    "url": row["url"] or "",
                    "publish_time": row["publish_time"] or "",
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                })
            
            logger.info(f"获取到 {len(info_list)} 条今日信息")
            return info_list
            
        except Exception as e:
            logger.error(f"获取今日信息失败: {e}")
            return []
    
    async def trigger_crawl(self, sources: List[Dict] = None, focus_point: str = "Web3 信息聚合"):
        """
        触发抓取任务
        
        Args:
            sources: 信息源列表，如果为 None 则使用默认源
            focus_point: 关注点，用于 WiseFlow 的 focus 配置
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # 如果没有指定源，使用默认源
            if not sources:
                sources = await self._get_all_sources()
            
            logger.info(f"开始抓取任务，源数量: {len(sources)}")
            
            # 准备 WiseFlow 的 focus 配置
            focus = {
                "id": "web3digest_default",
                "focuspoint": focus_point,
                "restrictions": "",
                "role": "Web3 信息聚合助手",
                "purpose": "抓取和筛选 Web3 相关信息"
            }
            
            # 转换源格式为 WiseFlow 格式
            wiseflow_sources = self._convert_sources_to_wiseflow_format(sources)
            
            # 调用 WiseFlow 的 main_process
            status, warning_msg, apply_count, recorder = await wiseflow_main_process(
                focus=focus,
                sources=wiseflow_sources,
                search=[],  # 不使用搜索引擎
                limit_hours=24,  # 抓取最近24小时的内容
                crawlers=self.crawlers,
                db_manager=self.db_manager,
                cache_manager=self.cache_manager
            )
            
            logger.info(f"抓取任务完成，状态: {status}, 处理数量: {apply_count}")
            logger.info(f"抓取统计: RSS源={recorder.rss_source}, Web源={recorder.web_source}, 文章数={len(recorder.article_queue)}")
            
            if warning_msg:
                logger.warning(f"抓取警告: {warning_msg}")
            
            return {
                "status": status,
                "apply_count": apply_count,
                "rss_sources": recorder.rss_source,
                "web_sources": recorder.web_source,
                "articles_count": len(recorder.article_queue),
                "warnings": list(warning_msg)
            }
            
        except Exception as e:
            logger.error(f"触发抓取失败: {e}", exc_info=True)
            raise
    
    async def _get_all_sources(self) -> List[Dict]:
        """获取所有信息源（通过 RSS.app 客户端）"""
        return await self.rss_app_client.get_all_rss_sources()
    
    def _convert_sources_to_wiseflow_format(self, sources: List[Dict]) -> List[Dict]:
        """
        将我们的源格式转换为 WiseFlow 格式
        
        WiseFlow 格式：
        {
            "type": "rss",
            "detail": ["url1", "url2", ...]  # 列表格式
        }
        """
        # 按类型分组
        rss_urls = []
        web_urls = []
        
        for source in sources:
            if not source.get("enabled", True):
                continue
            
            source_type = source.get("type", "rss")
            url = source.get("url")
            
            if not url:
                continue
            
            if source_type == "rss":
                rss_urls.append(url)
            elif source_type == "web":
                web_urls.append(url)
        
        # 构建 WiseFlow 格式的源列表
        wiseflow_sources = []
        
        if rss_urls:
            wiseflow_sources.append({
                "type": "rss",
                "detail": rss_urls
            })
        
        if web_urls:
            wiseflow_sources.append({
                "type": "web",
                "detail": web_urls
            })
        
        return wiseflow_sources
    
    async def add_source(self, source: Dict):
        """添加信息源"""
        # TODO: 实现添加信息源逻辑
        logger.info(f"添加信息源: {source}")
    
    async def remove_source(self, source_id: str):
        """移除信息源"""
        # TODO: 实现移除信息源逻辑
        logger.info(f"移除信息源: {source_id}")
    
    async def get_sources(self, user_id: int = None) -> List[Dict]:
        """获取信息源列表"""
        return await self._get_all_sources()
