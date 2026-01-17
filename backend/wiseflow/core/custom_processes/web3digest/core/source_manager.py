"""
用户信息源管理模块
"""
import json
import asyncio
import tempfile
import shutil
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings, DefaultRSSSources
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient, RSSValidator
from core.custom_processes.web3digest.utils.url_normalizer import URLNormalizer

logger = setup_logger(__name__)


class SourceManager:
    """用户信息源管理器"""

    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR) / "user_sources"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rss_app_client = RSSAppClient()
        self.rss_validator = RSSValidator()
        # 文件锁字典，每个文件一个锁
        self._file_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_user_sources_file(self, user_id: int) -> Path:
        """获取用户信息源文件路径"""
        return self.data_dir / f"{user_id}.json"

    def _get_file_lock(self, file_path: Path) -> asyncio.Lock:
        """获取文件锁（延迟创建）"""
        file_key = str(file_path)
        if file_key not in self._file_locks:
            self._file_locks[file_key] = asyncio.Lock()
        return self._file_locks[file_key]

    async def get_user_sources(self, user_id: int) -> Dict:
        """
        获取用户的信息源配置（线程安全）

        Returns:
            {
                "preset_sources": [
                    {"id": "preset_1", "name": "@VitalikButerin", "enabled": True, ...},
                    ...
                ],
                "custom_sources": [
                    {"id": "custom_1", "name": "@xxx", "type": "twitter", "enabled": True, ...},
                    ...
                ]
            }
        """
        user_file = self._get_user_sources_file(user_id)

        # 如果文件不存在，返回默认配置（所有预设源启用）
        if not user_file.exists():
            return self._get_default_sources_config()

        file_lock = self._get_file_lock(user_file)

        async with file_lock:
            try:
                with open(user_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)

                # 合并预设源和自定义源
                return {
                    "preset_sources": user_config.get("preset_sources", self._get_default_preset_sources()),
                    "custom_sources": user_config.get("custom_sources", [])
                }
            except Exception as e:
                logger.error(f"读取用户信息源配置失败 {user_id}: {e}")
                return self._get_default_sources_config()
    
    def _get_default_sources_config(self) -> Dict:
        """获取默认信息源配置（所有预设源启用）"""
        return {
            "preset_sources": self._get_default_preset_sources(),
            "custom_sources": []
        }
    
    def _get_default_preset_sources(self) -> List[Dict]:
        """获取默认预设源列表（全部启用）"""
        preset_sources = []
        
        # 1. 优先添加已验证的 RSS.app 真实订阅（Twitter）
        if hasattr(DefaultRSSSources, 'RSSAPP_FEEDS'):
            for i, feed in enumerate(DefaultRSSSources.RSSAPP_FEEDS, 1):
                preset_sources.append({
                    "id": f"preset_rssapp_{i}",
                    "name": feed["name"],
                    "type": "twitter",
                    "category": feed.get("category", "行业领袖"),
                    "url": feed["url"],  # 真实的 RSS.app URL
                    "enabled": feed.get("enabled", True),
                    "is_preset": True
                })
        
        # 2. 网站 RSS（这些是真实可用的）
        for i, rss in enumerate(DefaultRSSSources.WEBSITE_RSS, 1):
            preset_sources.append({
                "id": f"preset_website_{i}",
                "name": rss["name"],
                "type": "website",
                "category": rss["category"],
                "url": rss["url"],
                "enabled": rss.get("enabled", True),  # 使用配置中的 enabled 状态
                "is_preset": True
            })
        
        # 注意：TWITTER_ACCOUNTS 中的账号需要用户在 RSS.app 创建订阅后才能使用
        # 这些账号不会自动添加到预设源，但用户可以通过"添加 Twitter"功能手动添加
        
        return preset_sources
    
    async def save_user_sources(self, user_id: int, sources_config: Dict) -> bool:
        """原子保存用户信息源配置（使用临时文件+移动）"""
        try:
            user_file = self._get_user_sources_file(user_id)
            file_lock = self._get_file_lock(user_file)

            # 使用文件锁保护整个读写操作
            async with file_lock:
                # 写入临时文件
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.data_dir,
                    prefix=f".tmp_{user_id}_",
                    suffix=".json"
                )

                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(sources_config, f, ensure_ascii=False, indent=2)

                    # 原子性移动（Windows上需要先删除目标文件）
                    if user_file.exists():
                        user_file.unlink()
                    shutil.move(temp_path, user_file)

                    logger.info(f"保存用户 {user_id} 的信息源配置成功")
                    return True

                except Exception as e:
                    # 清理临时文件
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise e

        except Exception as e:
            logger.error(f"保存用户信息源配置失败 {user_id}: {e}", exc_info=True)
            return False
    
    async def toggle_source(self, user_id: int, source_id: str) -> bool:
        """切换信息源的启用/禁用状态"""
        sources_config = await self.get_user_sources(user_id)

        # 查找预设源
        for source in sources_config["preset_sources"]:
            if source["id"] == source_id:
                source["enabled"] = not source["enabled"]
                await self.save_user_sources(user_id, sources_config)
                return True

        # 查找自定义源
        for source in sources_config["custom_sources"]:
            if source["id"] == source_id:
                source["enabled"] = not source["enabled"]
                await self.save_user_sources(user_id, sources_config)
                return True

        return False

    def _generate_source_id(self, source_type: str) -> str:
        """
        生成唯一的源ID

        格式：custom_{type}_{timestamp}_{uuid_short}
        例如：custom_twitter_20260116153045_a1b2c3d4

        优势：
        - 时间戳保证顺序性，便于调试
        - UUID确保唯一性，避免删除后冲突
        - 类型前缀便于识别

        Args:
            source_type: 源类型（"twitter" 或 "website"）

        Returns:
            唯一ID字符串
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        uuid_short = str(uuid.uuid4())[:8]  # 取UUID前8位
        return f"custom_{source_type}_{timestamp}_{uuid_short}"

    async def check_duplicate_source(self, user_id: int, url: str,
                                     source_type: str, name: str = None) -> Dict:
        """
        检查是否重复

        增强的重复检测：
        - Twitter源：按用户名比较（不区分大小写）
        - 所有源：按规范化URL比较
        - 跨预设源和自定义源检测

        Args:
            user_id: 用户ID
            url: 源URL
            source_type: 源类型（"twitter" 或 "website"）
            name: 源名称（可选，用于Twitter用户名比较）

        Returns:
            {
                "is_duplicate": bool,
                "existing_source": Dict or None,
                "match_type": str  # "twitter_username" 或 "url"
            }
        """
        sources_config = await self.get_user_sources(user_id)
        all_sources = sources_config["preset_sources"] + sources_config["custom_sources"]

        # URL规范化
        normalized_url = URLNormalizer.normalize_url(url)

        # 如果是Twitter源，提取用户名进行比较
        if source_type == "twitter":
            new_username = URLNormalizer.extract_twitter_username(url) or (name or "").lstrip('@')

            for source in all_sources:
                # 按用户名比较
                if source.get("type") == "twitter":
                    existing_username = (
                        URLNormalizer.extract_twitter_username(source["url"]) or
                        source.get("name", "").lstrip('@')
                    )
                    if existing_username.lower() == new_username.lower():
                        return {
                            "is_duplicate": True,
                            "existing_source": source,
                            "match_type": "twitter_username"
                        }

        # 按规范化URL比较（适用于所有类型）
        for source in all_sources:
            source_normalized = URLNormalizer.normalize_url(source["url"])
            if source_normalized == normalized_url:
                return {
                    "is_duplicate": True,
                    "existing_source": source,
                    "match_type": "url"
                }

        return {"is_duplicate": False, "existing_source": None, "match_type": None}

    async def add_custom_twitter(self, user_id: int, twitter_username: str) -> Dict:
        """
        添加自定义 Twitter 账号（增强版）

        新流程：
        1. 输入清理和基本验证
        2. 生成RSS URL
        3. 深度验证RSS源（使用RSSValidator）
        4. 重复检测（使用check_duplicate_source）
        5. 生成唯一ID（使用_generate_source_id）
        6. 添加源元数据（added_at时间戳、验证元数据）
        7. 原子保存（使用文件锁）
        8. 返回结果（包括警告信息）

        Returns:
            {
                "success": bool,
                "message": str,
                "source": Dict or None,
                "warning": str or None,
                "error_code": str or None
            }
        """
        # 1. 输入清理和验证
        username = twitter_username.lstrip('@').strip()

        if not username:
            return {"success": False, "message": "Twitter 用户名不能为空"}

        # 2. 生成 RSS URL
        rss_url = self.rss_app_client.get_twitter_rss_url(username)

        # 3. 深度验证RSS源
        validation_result = await self.rss_validator.verify_twitter_rss(username)

        if not validation_result["valid"]:
            return {
                "success": False,
                "message": validation_result["error_message"],
                "error_code": validation_result["error_code"]
            }

        # 4. 重复检测（增强版）
        dup_check = await self.check_duplicate_source(
            user_id=user_id,
            url=rss_url,
            source_type="twitter",
            name=f"@{username}"
        )

        if dup_check["is_duplicate"]:
            existing = dup_check["existing_source"]
            source_location = "预设信息源" if existing.get("is_preset") else "自定义信息源"
            return {
                "success": False,
                "message": f"@{username} 已在{source_location}中，无需重复添加"
            }

        # 5. 添加源（使用新的ID生成策略）
        sources_config = await self.get_user_sources(user_id)

        custom_id = self._generate_source_id("twitter")
        new_source = {
            "id": custom_id,
            "name": f"@{username}",
            "type": "twitter",
            "category": "自定义",
            "url": rss_url,
            "enabled": True,
            "is_preset": False,
            "added_at": datetime.now().isoformat(),  # 添加时间戳
            "metadata": validation_result.get("metadata", {})
        }

        sources_config["custom_sources"].append(new_source)

        # 6. 原子保存（使用锁机制）
        save_success = await self.save_user_sources(user_id, sources_config)

        if not save_success:
            return {
                "success": False,
                "message": "保存失败，请稍后重试"
            }

        logger.info(f"用户 {user_id} 添加自定义 Twitter: @{username}")

        response = {
            "success": True,
            "message": f"✅ 已添加 @{username}",
            "source": new_source
        }

        # 7. 如果有警告信息，附加到响应
        if "warning" in validation_result.get("metadata", {}):
            response["warning"] = validation_result["metadata"]["warning"]

        return response
    
    async def add_custom_website(self, user_id: int, website_url: str) -> Dict:
        """
        添加自定义网站 RSS（增强版）

        新流程：
        1. 输入清理和基本验证
        2. 深度验证RSS源（使用RSSValidator）
        3. 重复检测（使用check_duplicate_source）
        4. 生成唯一ID（使用_generate_source_id）
        5. 添加源元数据（added_at时间戳、验证元数据）
        6. 原子保存（使用文件锁）
        7. 返回结果（包括警告信息）

        Returns:
            {
                "success": bool,
                "message": str,
                "source": Dict or None,
                "warning": str or None,
                "error_code": str or None
            }
        """
        # 1. 输入清理和验证
        url = website_url.strip()

        if not url:
            return {"success": False, "message": "网站 URL 不能为空"}

        # 如果 URL 不包含协议，添加 https://
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # 2. 深度验证RSS源
        validation_result = await self.rss_validator.deep_verify_rss(url, source_type="website")

        if not validation_result["valid"]:
            return {
                "success": False,
                "message": validation_result["error_message"],
                "error_code": validation_result["error_code"]
            }

        # 3. 重复检测（增强版）
        dup_check = await self.check_duplicate_source(
            user_id=user_id,
            url=url,
            source_type="website"
        )

        if dup_check["is_duplicate"]:
            existing = dup_check["existing_source"]
            source_location = "预设信息源" if existing.get("is_preset") else "自定义信息源"
            return {
                "success": False,
                "message": f"该 RSS 源已在{source_location}中，无需重复添加"
            }

        # 4. 提取网站名称（从 URL 或 RSS metadata）
        from urllib.parse import urlparse
        parsed = urlparse(url)
        site_name = (
            validation_result.get("metadata", {}).get("feed_title") or
            parsed.netloc.replace("www.", "") or
            "自定义网站"
        )

        # 5. 添加源（使用新的ID生成策略）
        sources_config = await self.get_user_sources(user_id)

        custom_id = self._generate_source_id("website")
        new_source = {
            "id": custom_id,
            "name": site_name,
            "type": "website",
            "category": "自定义",
            "url": url,
            "enabled": True,
            "is_preset": False,
            "added_at": datetime.now().isoformat(),  # 添加时间戳
            "metadata": validation_result.get("metadata", {})
        }

        sources_config["custom_sources"].append(new_source)

        # 6. 原子保存（使用锁机制）
        save_success = await self.save_user_sources(user_id, sources_config)

        if not save_success:
            return {
                "success": False,
                "message": "保存失败，请稍后重试"
            }

        logger.info(f"用户 {user_id} 添加自定义网站: {url}")

        response = {
            "success": True,
            "message": f"✅ 已添加 {site_name}",
            "source": new_source
        }

        # 7. 如果有警告信息，附加到响应
        if "warning" in validation_result.get("metadata", {}):
            response["warning"] = validation_result["metadata"]["warning"]

        return response
    
    async def remove_custom_source(self, user_id: int, source_id: str) -> bool:
        """删除自定义信息源（只能删除自定义的，不能删除预设的）"""
        sources_config = await self.get_user_sources(user_id)
        
        # 从自定义源中查找并删除
        original_count = len(sources_config["custom_sources"])
        sources_config["custom_sources"] = [
            s for s in sources_config["custom_sources"]
            if s["id"] != source_id
        ]
        
        if len(sources_config["custom_sources"]) < original_count:
            await self.save_user_sources(user_id, sources_config)
            logger.info(f"用户 {user_id} 删除自定义信息源: {source_id}")
            return True
        
        return False
    
    async def get_enabled_sources_for_crawl(self, user_id: int) -> List[Dict]:
        """获取用户启用的信息源（用于抓取）"""
        sources_config = await self.get_user_sources(user_id)
        
        enabled_sources = []
        
        # 预设源
        for source in sources_config["preset_sources"]:
            if source.get("enabled", True):
                enabled_sources.append({
                    "type": "rss",
                    "name": source["name"],
                    "category": source.get("category", ""),
                    "url": source["url"],
                    "source_type": source.get("type", "rss"),
                    "enabled": True
                })
        
        # 自定义源
        for source in sources_config["custom_sources"]:
            if source.get("enabled", True):
                enabled_sources.append({
                    "type": "rss",
                    "name": source["name"],
                    "category": source.get("category", "自定义"),
                    "url": source["url"],
                    "source_type": source.get("type", "rss"),
                    "enabled": True
                })
        
        return enabled_sources
