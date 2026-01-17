"""
RSS历史数据存储管理器
定期抓取RSS数据并持久化到JSON文件，支持去重和数据合并
"""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)

# 默认配置
HISTORY_RETENTION_DAYS = 7  # 数据保留天数
MAX_ITEMS_PER_SOURCE = 1000  # 每个源最大保留条目数


class RssHistoryManager:
    """RSS历史数据管理器"""

    def __init__(self, data_dir: Optional[Path] = None):
        """
        初始化RSS历史数据管理器

        Args:
            data_dir: 数据目录路径，默认使用settings.DATA_DIR/rss_history
        """
        if data_dir is None:
            data_dir = Path(settings.DATA_DIR) / "rss_history"
        else:
            data_dir = Path(data_dir)

        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 文件锁字典，每个文件一个锁
        self._file_locks: Dict[str, asyncio.Lock] = {}

    def _get_file_lock(self, file_path: Path) -> asyncio.Lock:
        """获取文件锁（延迟创建）"""
        file_key = str(file_path)
        if file_key not in self._file_locks:
            self._file_locks[file_key] = asyncio.Lock()
        return self._file_locks[file_key]

    def _get_url_hash(self, url: str) -> str:
        """生成URL的MD5哈希值"""
        return hashlib.md5(url.encode()).hexdigest()

    def _get_history_file_path(self, source_url: str) -> Path:
        """获取历史数据文件路径"""
        url_hash = self._get_url_hash(source_url)
        return self.data_dir / f"{url_hash}.json"

    def _generate_item_id(self, item: Dict) -> str:
        """
        生成条目的唯一ID

        优先使用URL的MD5，如果没有URL则使用标题+发布时间的MD5
        """
        url = item.get('url', '')
        if url:
            return hashlib.md5(url.encode()).hexdigest()

        # 备用：使用标题+发布时间
        title = item.get('title', '')
        publish_time = item.get('publish_time', '')
        combined = f"{title}_{publish_time}"
        return hashlib.md5(combined.encode()).hexdigest()

    async def _load_history_file(self, file_path: Path) -> Dict:
        """
        加载历史数据文件

        Returns:
            历史数据字典，如果文件不存在或损坏返回空字典
        """
        if not file_path.exists():
            return {
                "source_url": "",
                "source_name": "",
                "last_fetch_time": "",
                "items": [],
                "metadata": {
                    "total_items": 0,
                    "oldest_item_time": "",
                    "newest_item_time": ""
                }
            }

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 验证数据结构
                if not isinstance(data, dict) or 'items' not in data:
                    logger.warning(f"Invalid history file format: {file_path}")
                    return {
                        "source_url": data.get("source_url", ""),
                        "source_name": data.get("source_name", ""),
                        "last_fetch_time": "",
                        "items": [],
                        "metadata": {
                            "total_items": 0,
                            "oldest_item_time": "",
                            "newest_item_time": ""
                        }
                    }
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse history file {file_path}: {e}")
            # 备份损坏的文件
            backup_path = file_path.with_suffix('.json.bak')
            try:
                file_path.rename(backup_path)
                logger.info(f"Backed up corrupted file to {backup_path}")
            except Exception as backup_error:
                logger.error(f"Failed to backup corrupted file: {backup_error}")

            return {
                "source_url": "",
                "source_name": "",
                "last_fetch_time": "",
                "items": [],
                "metadata": {
                    "total_items": 0,
                    "oldest_item_time": "",
                    "newest_item_time": ""
                }
            }
        except Exception as e:
            logger.error(f"Failed to load history file {file_path}: {e}")
            return {
                "source_url": "",
                "source_name": "",
                "last_fetch_time": "",
                "items": [],
                "metadata": {
                    "total_items": 0,
                    "oldest_item_time": "",
                    "newest_item_time": ""
                }
            }

    async def _save_history_file(self, file_path: Path, data: Dict):
        """
        保存历史数据文件

        Args:
            file_path: 文件路径
            data: 要保存的数据
        """
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入临时文件，然后原子性重命名
            temp_path = file_path.with_suffix('.json.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # 原子性重命名
            temp_path.replace(file_path)
            logger.debug(f"Saved history file: {file_path} ({data['metadata']['total_items']} items)")
        except Exception as e:
            logger.error(f"Failed to save history file {file_path}: {e}")
            raise

    def _merge_and_deduplicate(self, old_items: List[Dict], new_items: List[Dict]) -> List[Dict]:
        """
        合并并去重条目

        Args:
            old_items: 现有条目列表
            new_items: 新条目列表

        Returns:
            合并并去重后的条目列表，按发布时间倒序排列
        """
        # 使用字典来存储唯一条目，以item_id为key
        items_dict: Dict[str, Dict] = {}

        # 先添加旧条目
        for item in old_items:
            item_id = self._generate_item_id(item)
            if item_id not in items_dict:
                items_dict[item_id] = item

        # 再添加新条目（新条目会覆盖旧条目，如果有相同的ID）
        for item in new_items:
            item_id = self._generate_item_id(item)
            items_dict[item_id] = item

        # 转换为列表并排序（按发布时间倒序，最新的在前）
        merged_items = list(items_dict.values())

        # 按发布时间排序
        def get_publish_time(item: Dict) -> datetime:
            publish_time_str = item.get('publish_time', '')
            if not publish_time_str:
                return datetime.min

            try:
                # 尝试解析ISO格式时间
                if 'T' in publish_time_str:
                    return datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
                # 尝试解析常见格式
                for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%d %H:%M:%S']:
                    try:
                        return datetime.strptime(publish_time_str, fmt)
                    except ValueError:
                        continue
                return datetime.min
            except Exception:
                return datetime.min

        merged_items.sort(key=get_publish_time, reverse=True)

        # 限制最大条目数
        if len(merged_items) > MAX_ITEMS_PER_SOURCE:
            merged_items = merged_items[:MAX_ITEMS_PER_SOURCE]
            logger.debug(f"Limited items to {MAX_ITEMS_PER_SOURCE} (had {len(items_dict)})")

        return merged_items

    def _update_metadata(self, items: List[Dict], source_url: str, source_name: str) -> Dict:
        """
        更新元数据

        Args:
            items: 条目列表
            source_url: 源URL
            source_name: 源名称

        Returns:
            更新后的元数据字典
        """
        if not items:
            return {
                "total_items": 0,
                "oldest_item_time": "",
                "newest_item_time": ""
            }

        # 提取所有发布时间
        publish_times = []
        for item in items:
            publish_time_str = item.get('publish_time', '')
            if publish_time_str:
                publish_times.append(publish_time_str)

        oldest_time = min(publish_times) if publish_times else ""
        newest_time = max(publish_times) if publish_times else ""

        return {
            "total_items": len(items),
            "oldest_item_time": oldest_time,
            "newest_item_time": newest_time
        }

    async def save_rss_items(self, source_url: str, source_name: str, items: List[Dict]) -> bool:
        """
        保存RSS条目到历史文件，自动去重

        Args:
            source_url: RSS源URL
            source_name: RSS源名称
            items: 要保存的条目列表

        Returns:
            是否保存成功
        """
        if not items:
            logger.debug(f"No items to save for {source_name}")
            return True

        file_path = self._get_history_file_path(source_url)
        file_lock = self._get_file_lock(file_path)

        async with file_lock:
            try:
                # 加载现有数据
                history_data = await self._load_history_file(file_path)

                # 合并并去重
                old_items = history_data.get('items', [])
                merged_items = self._merge_and_deduplicate(old_items, items)

                # 更新元数据
                metadata = self._update_metadata(merged_items, source_url, source_name)

                # 构建保存数据
                save_data = {
                    "source_url": source_url,
                    "source_name": source_name,
                    "last_fetch_time": datetime.now().isoformat(),
                    "items": merged_items,
                    "metadata": metadata
                }

                # 保存文件
                await self._save_history_file(file_path, save_data)

                new_count = len(items)
                merged_count = len(merged_items)
                logger.info(
                    f"Saved {new_count} new items for {source_name}, "
                    f"total {merged_count} items after deduplication"
                )

                return True

            except Exception as e:
                logger.error(f"Failed to save RSS items for {source_name}: {e}")
                return False

    async def get_rss_items(
        self, 
        source_url: str, 
        hours: Optional[int] = None
    ) -> List[Dict]:
        """
        获取指定RSS源的历史条目

        Args:
            source_url: RSS源URL
            hours: 时间范围（小时），None表示返回所有条目

        Returns:
            条目列表，按发布时间倒序排列
        """
        file_path = self._get_history_file_path(source_url)
        history_data = await self._load_history_file(file_path)

        items = history_data.get('items', [])

        if hours is None:
            return items

        # 按时间范围过滤
        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered_items = []

        for item in items:
            publish_time_str = item.get('publish_time', '')
            if not publish_time_str:
                continue

            try:
                # 尝试解析发布时间
                if 'T' in publish_time_str:
                    publish_time = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
                else:
                    # 尝试其他格式
                    publish_time = datetime.min
                    for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%d %H:%M:%S']:
                        try:
                            publish_time = datetime.strptime(publish_time_str, fmt)
                            break
                        except ValueError:
                            continue

                # 转换为本地时间（如果需要）
                if publish_time.tzinfo:
                    publish_time = publish_time.replace(tzinfo=None)

                if publish_time >= cutoff_time:
                    filtered_items.append(item)

            except Exception as e:
                logger.debug(f"Failed to parse publish_time '{publish_time_str}': {e}")
                # 如果无法解析时间，保留条目（保守策略）
                filtered_items.append(item)

        return filtered_items

    async def get_all_items(self, hours: Optional[int] = None) -> List[Dict]:
        """
        获取所有RSS源的历史条目

        Args:
            hours: 时间范围（小时），None表示返回所有条目

        Returns:
            所有条目列表，按发布时间倒序排列
        """
        all_items = []

        # 扫描所有历史文件
        for file_path in self.data_dir.glob("*.json"):
            if file_path.name.endswith('.tmp') or file_path.name.endswith('.bak'):
                continue

            try:
                history_data = await self._load_history_file(file_path)
                items = history_data.get('items', [])

                if hours is None:
                    all_items.extend(items)
                else:
                    # 按时间范围过滤
                    source_items = await self.get_rss_items(
                        history_data.get('source_url', ''),
                        hours
                    )
                    all_items.extend(source_items)

            except Exception as e:
                logger.warning(f"Failed to load items from {file_path}: {e}")
                continue

        # 按发布时间排序（最新的在前）
        def get_publish_time(item: Dict) -> datetime:
            publish_time_str = item.get('publish_time', '')
            if not publish_time_str:
                return datetime.min

            try:
                if 'T' in publish_time_str:
                    return datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
                for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%d %H:%M:%S']:
                    try:
                        return datetime.strptime(publish_time_str, fmt)
                    except ValueError:
                        continue
                return datetime.min
            except Exception:
                return datetime.min

        all_items.sort(key=get_publish_time, reverse=True)

        return all_items

    async def cleanup_old_items(self, source_url: Optional[str] = None, days: int = HISTORY_RETENTION_DAYS) -> int:
        """
        清理超过指定天数的旧条目

        Args:
            source_url: 指定源URL，None表示清理所有源
            days: 保留天数，默认7天

        Returns:
            清理的条目数量
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        cleaned_count = 0

        if source_url:
            # 清理指定源
            file_paths = [self._get_history_file_path(source_url)]
        else:
            # 清理所有源
            file_paths = list(self.data_dir.glob("*.json"))
            file_paths = [p for p in file_paths if not p.name.endswith('.tmp') and not p.name.endswith('.bak')]

        for file_path in file_paths:
            file_lock = self._get_file_lock(file_path)
            async with file_lock:
                try:
                    history_data = await self._load_history_file(file_path)
                    items = history_data.get('items', [])

                    if not items:
                        continue

                    # 过滤出需要保留的条目
                    kept_items = []
                    for item in items:
                        publish_time_str = item.get('publish_time', '')
                        if not publish_time_str:
                            # 如果没有发布时间，保留（保守策略）
                            kept_items.append(item)
                            continue

                        try:
                            if 'T' in publish_time_str:
                                publish_time = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
                            else:
                                publish_time = datetime.min
                                for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%d %H:%M:%S']:
                                    try:
                                        publish_time = datetime.strptime(publish_time_str, fmt)
                                        break
                                    except ValueError:
                                        continue

                            if publish_time.tzinfo:
                                publish_time = publish_time.replace(tzinfo=None)

                            if publish_time >= cutoff_time:
                                kept_items.append(item)
                            else:
                                cleaned_count += 1

                        except Exception:
                            # 无法解析时间，保留（保守策略）
                            kept_items.append(item)

                    # 如果没有需要保留的条目，删除文件
                    if not kept_items:
                        try:
                            file_path.unlink()
                            logger.info(f"Deleted empty history file: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete empty file {file_path}: {e}")
                        continue

                    # 更新元数据并保存
                    source_url = history_data.get('source_url', '')
                    source_name = history_data.get('source_name', '')
                    metadata = self._update_metadata(kept_items, source_url, source_name)

                    save_data = {
                        "source_url": source_url,
                        "source_name": source_name,
                        "last_fetch_time": history_data.get('last_fetch_time', ''),
                        "items": kept_items,
                        "metadata": metadata
                    }

                    await self._save_history_file(file_path, save_data)

                    if cleaned_count > 0:
                        logger.info(
                            f"Cleaned {cleaned_count} old items from {source_name} "
                            f"(kept {len(kept_items)} items)"
                        )

                except Exception as e:
                    logger.error(f"Failed to cleanup old items from {file_path}: {e}")
                    continue

        return cleaned_count
