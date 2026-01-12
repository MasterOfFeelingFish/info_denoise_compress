"""
用户信息源管理模块
"""
import json
from pathlib import Path
from typing import List, Dict, Optional
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings, DefaultRSSSources
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient

logger = setup_logger(__name__)


class SourceManager:
    """用户信息源管理器"""
    
    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR) / "user_sources"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rss_app_client = RSSAppClient()
    
    def _get_user_sources_file(self, user_id: int) -> Path:
        """获取用户信息源文件路径"""
        return self.data_dir / f"{user_id}.json"
    
    async def get_user_sources(self, user_id: int) -> Dict:
        """
        获取用户的信息源配置
        
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
        
        # Twitter 账号
        for i, account in enumerate(DefaultRSSSources.TWITTER_ACCOUNTS, 1):
            preset_sources.append({
                "id": f"preset_twitter_{i}",
                "name": f"@{account['name']}",
                "type": "twitter",
                "category": account["category"],
                "url": self.rss_app_client.get_twitter_rss_url(account["name"]),
                "enabled": True,
                "is_preset": True
            })
        
        # 网站 RSS
        for i, rss in enumerate(DefaultRSSSources.WEBSITE_RSS, 1):
            preset_sources.append({
                "id": f"preset_website_{i}",
                "name": rss["name"],
                "type": "website",
                "category": rss["category"],
                "url": rss["url"],
                "enabled": True,
                "is_preset": True
            })
        
        return preset_sources
    
    async def save_user_sources(self, user_id: int, sources_config: Dict) -> bool:
        """保存用户信息源配置"""
        try:
            user_file = self._get_user_sources_file(user_id)
            
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(sources_config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"保存用户 {user_id} 的信息源配置")
            return True
        except Exception as e:
            logger.error(f"保存用户信息源配置失败 {user_id}: {e}")
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
    
    async def add_custom_twitter(self, user_id: int, twitter_username: str) -> Dict:
        """
        添加自定义 Twitter 账号
        
        Returns:
            {"success": bool, "message": str, "source": Dict or None}
        """
        # 移除 @ 符号
        username = twitter_username.lstrip('@').strip()
        
        if not username:
            return {"success": False, "message": "Twitter 用户名不能为空"}
        
        # 生成 RSS URL
        rss_url = self.rss_app_client.get_twitter_rss_url(username)
        
        # 验证 RSS URL 是否可访问
        is_valid = await self.rss_app_client.verify_rss_url(rss_url)
        if not is_valid:
            return {
                "success": False,
                "message": f"无法访问 @{username} 的 RSS 源，请确认账号存在或稍后重试"
            }
        
        # 检查是否已存在
        sources_config = await self.get_user_sources(user_id)
        
        # 检查预设源中是否已有
        for source in sources_config["preset_sources"]:
            if source.get("name") == f"@{username}":
                return {
                    "success": False,
                    "message": f"@{username} 已在预设信息源中，无需重复添加"
                }
        
        # 检查自定义源中是否已有
        for source in sources_config["custom_sources"]:
            if source.get("name") == f"@{username}":
                return {
                    "success": False,
                    "message": f"@{username} 已添加，无需重复添加"
                }
        
        # 添加自定义源
        custom_id = f"custom_twitter_{len(sources_config['custom_sources']) + 1}"
        new_source = {
            "id": custom_id,
            "name": f"@{username}",
            "type": "twitter",
            "category": "自定义",
            "url": rss_url,
            "enabled": True,
            "is_preset": False
        }
        
        sources_config["custom_sources"].append(new_source)
        await self.save_user_sources(user_id, sources_config)
        
        logger.info(f"用户 {user_id} 添加自定义 Twitter: @{username}")
        return {
            "success": True,
            "message": f"✅ 已添加 @{username}",
            "source": new_source
        }
    
    async def add_custom_website(self, user_id: int, website_url: str) -> Dict:
        """
        添加自定义网站 RSS
        
        Returns:
            {"success": bool, "message": str, "source": Dict or None}
        """
        url = website_url.strip()
        
        if not url:
            return {"success": False, "message": "网站 URL 不能为空"}
        
        # 如果 URL 不包含协议，添加 https://
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        # 验证 URL 是否可访问
        is_valid = await self.rss_app_client.verify_rss_url(url)
        if not is_valid:
            return {
                "success": False,
                "message": f"无法访问该 RSS 源，请确认 URL 正确且可访问"
            }
        
        # 检查是否已存在
        sources_config = await self.get_user_sources(user_id)
        
        for source in sources_config["preset_sources"] + sources_config["custom_sources"]:
            if source.get("url") == url:
                return {
                    "success": False,
                    "message": "该 RSS 源已添加，无需重复添加"
                }
        
        # 提取网站名称（从 URL）
        from urllib.parse import urlparse
        parsed = urlparse(url)
        site_name = parsed.netloc.replace("www.", "") or "自定义网站"
        
        # 添加自定义源
        custom_id = f"custom_website_{len(sources_config['custom_sources']) + 1}"
        new_source = {
            "id": custom_id,
            "name": site_name,
            "type": "website",
            "category": "自定义",
            "url": url,
            "enabled": True,
            "is_preset": False
        }
        
        sources_config["custom_sources"].append(new_source)
        await self.save_user_sources(user_id, sources_config)
        
        logger.info(f"用户 {user_id} 添加自定义网站: {url}")
        return {
            "success": True,
            "message": f"✅ 已添加 {site_name}",
            "source": new_source
        }
    
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
