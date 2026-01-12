"""
简报生成器 - 整合信息抓取、筛选和生成
"""
import asyncio
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.llm_client import LLMClient
from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient

logger = setup_logger(__name__)


class DigestGenerator:
    """简报生成器"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.wiseflow_client = WiseFlowClient()
        self.data_dir = Path(settings.DATA_DIR)
    
    async def generate_digest(self, user_id: int, user_profile: str) -> Optional[str]:
        """为用户生成简报"""
        try:
            # 1. 获取今日原始信息
            raw_info = await self._fetch_raw_info()
            
            if not raw_info:
                logger.warning("没有获取到原始信息")
                return None
            
            # 2. AI 筛选个性化内容
            selected_info = await self._filter_info(raw_info, user_profile)
            
            if not selected_info:
                logger.warning(f"用户 {user_id} 没有符合条件的信息")
                return None
            
            # 3. 生成简报
            stats = await self._calculate_stats(len(raw_info), len(selected_info), user_id)
            digest = await self.llm_client.generate_digest(user_profile, selected_info, stats)
            
            # 4. 保存统计信息
            await self._save_daily_stats(user_id, stats)
            
            return digest
            
        except Exception as e:
            logger.error(f"生成简报失败 {user_id}: {e}")
            return None
    
    async def _fetch_raw_info(self, user_id: int = None) -> List[Dict]:
        """获取今日原始信息"""
        # 从 WiseFlow 获取今日抓取的信息
        # 如果指定了 user_id，可以按用户筛选（未来扩展）
        return await self.wiseflow_client.get_today_info()
    
    async def _filter_info(self, raw_info: List[Dict], user_profile: str) -> List[Dict]:
        """使用 AI 筛选信息"""
        selected = []
        
        # 并发处理，提高效率
        semaphore = asyncio.Semaphore(settings.LLM_CONCURRENT_NUMBER)
        
        async def process_info(info):
            async with semaphore:
                result = await self.llm_client.extract_info(
                    content=info.get("content", ""),
                    user_profile=user_profile
                )
                
                if result.get("is_valuable") and result.get("importance_score", 0) >= 5:
                    # 合并信息
                    return {
                        "id": info.get("id"),
                        "title": result.get("title", info.get("title", "")),
                        "summary": result.get("summary", ""),
                        "source": info.get("source", ""),
                        "url": info.get("url", ""),
                        "importance": result.get("importance_score", 5),
                        "reason": result.get("reason", ""),
                        "publish_time": info.get("publish_time", "")
                    }
                return None
        
        # 并发处理所有信息
        tasks = [process_info(info) for info in raw_info]
        results = await asyncio.gather(*tasks)
        
        # 过滤并排序
        selected = [r for r in results if r is not None]
        selected.sort(key=lambda x: x["importance"], reverse=True)
        
        # 限制数量
        max_count = settings.MAX_INFO_PER_USER
        min_count = settings.MIN_INFO_PER_USER
        
        if len(selected) > max_count:
            selected = selected[:max_count]
        elif len(selected) < min_count and len(raw_info) > min_count:
            # 如果选出的太少，降低标准再选一次
            logger.info(f"初次筛选只选出 {len(selected)} 条，降低标准重新筛选")
            return await self._filter_info_with_lower_threshold(raw_info, user_profile)
        
        return selected
    
    async def _filter_info_with_lower_threshold(self, raw_info: List[Dict], user_profile: str) -> List[Dict]:
        """降低阈值重新筛选"""
        selected = []
        
        for info in raw_info:
            result = await self.llm_client.extract_info(
                content=info.get("content", ""),
                user_profile=user_profile
            )
            
            if result.get("is_valuable") and result.get("importance_score", 0) >= 3:
                selected.append({
                    "id": info.get("id"),
                    "title": result.get("title", info.get("title", "")),
                    "summary": result.get("summary", ""),
                    "source": info.get("source", ""),
                    "url": info.get("url", ""),
                    "importance": result.get("importance_score", 5),
                    "reason": result.get("reason", ""),
                    "publish_time": info.get("publish_time", "")
                })
        
        # 排序并限制数量
        selected.sort(key=lambda x: x["importance"], reverse=True)
        return selected[:settings.MAX_INFO_PER_USER]
    
    async def _get_sources_count(self, user_id: int = None) -> int:
        """获取实际的信息源数量（用户启用的源）"""
        try:
            if user_id:
                # 使用用户自定义的信息源配置
                from core.custom_processes.web3digest.core.source_manager import SourceManager
                source_manager = SourceManager()
                enabled_sources = await source_manager.get_enabled_sources_for_crawl(user_id)
                return len(enabled_sources)
            else:
                # 使用默认源
                sources = await self.wiseflow_client.get_sources()
                enabled_sources = [s for s in sources if s.get("enabled", True)]
                return len(enabled_sources)
        except Exception as e:
            logger.warning(f"获取源数量失败，使用默认值: {e}")
            return 20  # 默认值
    
    async def _get_total_time_saved(self, user_id: int) -> float:
        """获取累计节省时间（小时）"""
        total_hours = 0.0
        
        try:
            # 读取所有历史统计文件
            stats_dir = self.data_dir / "daily_stats"
            if not stats_dir.exists():
                return 0.0
            
            # 遍历所有统计文件
            for stats_file in stats_dir.glob("*.json"):
                try:
                    with open(stats_file, 'r', encoding='utf-8') as f:
                        daily_stats = json.load(f)
                    
                    # 获取该用户的统计
                    user_stats = daily_stats.get("users", {}).get(str(user_id), {})
                    if user_stats:
                        time_saved = user_stats.get("time_saved", 0)
                        if isinstance(time_saved, (int, float)):
                            total_hours += time_saved
                except Exception as e:
                    logger.debug(f"读取统计文件失败 {stats_file}: {e}")
                    continue
            
        except Exception as e:
            logger.warning(f"计算累计节省时间失败: {e}")
        
        return round(total_hours, 1)
    
    async def _calculate_stats(self, raw_count: int, selected_count: int, user_id: int) -> Dict:
        """计算统计数据"""
        filter_rate = f"{(selected_count/raw_count*100):.1f}%" if raw_count > 0 else "0%"
        
        # 假设每条信息平均节省 2 分钟
        time_saved_today = round((raw_count - selected_count) * 2 / 60, 1)
        
        # 获取实际源数量（用户启用的源）
        sources_count = await self._get_sources_count(user_id)
        
        # 获取累计节省时间
        total_time_saved = await self._get_total_time_saved(user_id)
        
        return {
            "sources_count": sources_count,
            "raw_count": raw_count,
            "selected_count": selected_count,
            "filter_rate": filter_rate,
            "time_saved": time_saved_today,
            "total_time_saved": total_time_saved
        }
    
    async def _save_daily_stats(self, user_id: int, stats: Dict):
        """保存每日统计"""
        stats_file = self.data_dir / "daily_stats" / f"{date.today().isoformat()}.json"
        
        # 读取现有统计
        existing_stats = {}
        if stats_file.exists():
            with open(stats_file, 'r', encoding='utf-8') as f:
                existing_stats = json.load(f)
        
        # 更新用户统计
        if "users" not in existing_stats:
            existing_stats["users"] = {}
        
        existing_stats["users"][str(user_id)] = stats
        existing_stats["date"] = date.today().isoformat()
        
        # 保存
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(existing_stats, f, ensure_ascii=False, indent=2)
