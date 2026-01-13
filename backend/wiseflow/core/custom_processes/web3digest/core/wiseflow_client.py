"""
WiseFlow 客户端 - 简化的信息抓取能力
直接使用 RSS 解析获取内容，避免复杂的 WiseFlow 依赖
"""
import json
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
import asyncio
import hashlib

# 使用简化的 RSS 抓取
from core.tools.rss_parsor import fetch_rss
from core.wis.async_cache import SqliteCache

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.config import DefaultRSSSources
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient

logger = setup_logger(__name__)


class WiseFlowClient:
    """WiseFlow 客户端 - 简化版"""
    
    def __init__(self):
        self.cache_manager = None
        self.rss_app_client = RSSAppClient()
        self._initialized = False
        self.data_dir = Path(settings.DATA_DIR) / "raw_info"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """初始化 WiseFlow"""
        if self._initialized:
            return
        
        try:
            # 初始化缓存管理器
            cache_dir = Path(settings.DATA_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_manager = SqliteCache(db_path=str(cache_dir / "cache.db"))
            await self.cache_manager.open()  # 异步打开缓存
            
            self._initialized = True
            logger.info("WiseFlow 客户端初始化成功")
            
        except Exception as e:
            logger.error(f"WiseFlow 初始化失败: {e}")
            raise
    
    async def get_today_info(self) -> List[Dict]:
        """获取今日抓取的信息"""
        if not self._initialized:
            await self.initialize()
        
        try:
            # 从本地 JSON 文件获取今日信息
            today = date.today().isoformat()
            today_file = self.data_dir / f"{today}.json"
            
            if today_file.exists():
                with open(today_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    info_list = data.get("items", [])
                    logger.info(f"获取到 {len(info_list)} 条今日信息")
                    return info_list
            
            logger.info("今日没有已抓取的信息")
            return []
            
        except Exception as e:
            logger.error(f"获取今日信息失败: {e}")
            return []
    
    async def trigger_crawl(self, sources: List[Dict] = None, focus_point: str = "Web3 信息聚合"):
        """
        触发抓取任务 - 简化版，直接使用 RSS 解析
        
        Args:
            sources: 信息源列表，如果为 None 则使用默认源
            focus_point: 关注点（暂不使用）
        
        Returns:
            Dict 包含抓取结果统计
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # 如果没有指定源，使用默认源
            if not sources:
                sources = await self._get_all_sources()
            
            logger.info(f"开始抓取任务，源数量: {len(sources)}")
            
            # 获取所有 RSS URL
            rss_urls = []
            for source in sources:
                if source.get("enabled", True):
                    url = source.get("url")
                    if url:
                        rss_urls.append({
                            "url": url,
                            "name": source.get("name", "未知"),
                            "category": source.get("category", "")
                        })
            
            logger.info(f"准备抓取 {len(rss_urls)} 个 RSS 源")
            
            # 并行抓取所有 RSS 源
            all_items = []
            success_count = 0
            fail_count = 0
            
            # 批量抓取，每次最多 10 个并行（提高速度）
            batch_size = 10
            for i in range(0, len(rss_urls), batch_size):
                batch = rss_urls[i:i+batch_size]
                tasks = [self._fetch_single_rss(src) for src in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        fail_count += 1
                        logger.warning(f"抓取失败: {result}")
                    elif result:
                        all_items.extend(result)
                        success_count += 1
            
            logger.info(f"抓取完成: 成功 {success_count} 源, 失败 {fail_count} 源, 获取 {len(all_items)} 条内容")
            
            # 去重
            unique_items = self._deduplicate_items(all_items)
            logger.info(f"去重后: {len(unique_items)} 条内容")
            
            # 保存到文件
            today = date.today().isoformat()
            await self._save_items(today, unique_items)
            
            return {
                "status": 0 if success_count > 0 else 1,
                "apply_count": len(unique_items),
                "rss_sources": success_count,
                "web_sources": 0,
                "articles_count": len(unique_items),
                "warnings": [] if fail_count == 0 else [f"{fail_count} 个源抓取失败"]
            }
            
        except Exception as e:
            logger.error(f"触发抓取失败: {e}", exc_info=True)
            raise
    
    async def _fetch_single_rss(self, source: Dict) -> List[Dict]:
        """抓取单个 RSS 源"""
        url = source.get("url")
        name = source.get("name", "未知")
        category = source.get("category", "")
        
        try:
            # 使用 WiseFlow 的 RSS 解析器
            results, feed_title, feed_info = await fetch_rss(
                url, 
                existings=set(),
                cache_manager=self.cache_manager
            )
            
            items = []
            for result in results:
                # 转换为标准格式
                # CrawlResult 属性: url, html, markdown, title, author, publish_date
                item = {
                    "id": self._generate_id(result.url or url),
                    "title": result.title or feed_title or name,
                    "content": result.markdown or result.html or "",
                    "source": name,
                    "source_category": category,
                    "url": result.url or url,
                    "publish_time": result.publish_date or "",
                    "crawl_time": datetime.now().isoformat(),
                    "metadata": {
                        "feed_title": feed_title,
                        "author": result.author or "",
                    }
                }
                items.append(item)
            
            logger.debug(f"从 {name} 获取 {len(items)} 条内容")
            return items
            
        except Exception as e:
            logger.warning(f"抓取 {name} ({url}) 失败: {e}")
            return []
    
    def _generate_id(self, url: str) -> str:
        """生成唯一 ID"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def _deduplicate_items(self, items: List[Dict]) -> List[Dict]:
        """去重"""
        seen = set()
        unique = []
        
        for item in items:
            # 使用 URL 或标题做去重
            key = item.get("url") or item.get("title") or item.get("id")
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        
        return unique
    
    async def _save_items(self, today: str, items: List[Dict]):
        """保存抓取的内容到 JSON 文件"""
        today_file = self.data_dir / f"{today}.json"
        
        # 读取现有数据（如果有）
        existing_items = []
        if today_file.exists():
            try:
                with open(today_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_items = data.get("items", [])
            except Exception:
                pass
        
        # 合并新旧数据并去重
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
    
    async def _get_all_sources(self) -> List[Dict]:
        """获取所有信息源（通过 RSS.app 客户端）"""
        return await self.rss_app_client.get_all_rss_sources()
    
    async def add_source(self, source: Dict):
        """添加信息源"""
        logger.info(f"添加信息源: {source}")
    
    async def remove_source(self, source_id: str):
        """移除信息源"""
        logger.info(f"移除信息源: {source_id}")
    
    async def get_sources(self, user_id: int = None) -> List[Dict]:
        """获取信息源列表"""
        return await self._get_all_sources()
