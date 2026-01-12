"""
RSS.app 客户端 - 将 Twitter 账号转换为 RSS 源
"""
import httpx
from typing import List, Dict, Optional
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings, DefaultRSSSources

logger = setup_logger(__name__)


class RSSAppClient:
    """RSS.app 客户端"""
    
    def __init__(self):
        self.token = settings.RSS_APP_TOKEN
        self.base_url = "https://api.rss.app/v1"
    
    def get_twitter_rss_url(self, twitter_username: str) -> str:
        """
        获取 Twitter 账号的 RSS URL
        
        RSS.app 的 URL 格式：
        - 免费版：https://rss.app/feeds/v1.1/{username}.xml
        - API 版：https://api.rss.app/v1/feeds/{feed_id}
        
        我们使用简单的 URL 格式，如果用户有 RSS.app 账号，可以配置 token
        """
        # 移除 @ 符号（如果有）
        username = twitter_username.lstrip('@')
        
        # RSS.app 的标准格式
        rss_url = f"https://rss.app/feeds/v1.1/{username}.xml"
        
        return rss_url
    
    def get_all_twitter_rss_sources(self) -> List[Dict]:
        """获取所有 Twitter 账号的 RSS 源配置"""
        sources = []
        
        for account in DefaultRSSSources.TWITTER_ACCOUNTS:
            username = account["name"]
            rss_url = self.get_twitter_rss_url(username)
            
            sources.append({
                "type": "rss",
                "name": f"@{username}",
                "category": account["category"],
                "url": rss_url,
                "source_type": "twitter",
                "enabled": True
            })
        
        return sources
    
    async def verify_rss_url(self, rss_url: str) -> bool:
        """验证 RSS URL 是否可访问"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(rss_url, follow_redirects=True)
                if response.status_code == 200:
                    # 检查内容类型
                    content_type = response.headers.get("content-type", "").lower()
                    if "xml" in content_type or "rss" in content_type or "atom" in content_type:
                        return True
                    # 也接受 text/plain（某些 RSS 服务返回这个）
                    if "text/plain" in content_type:
                        return True
            return False
        except Exception as e:
            logger.debug(f"验证 RSS URL 失败 {rss_url}: {e}")
            return False
    
    async def get_all_rss_sources(self) -> List[Dict]:
        """获取所有 RSS 源（Twitter + 网站）"""
        sources = []
        
        # Twitter RSS 源
        twitter_sources = self.get_all_twitter_rss_sources()
        sources.extend(twitter_sources)
        
        # 网站 RSS 源
        for rss in DefaultRSSSources.WEBSITE_RSS:
            sources.append({
                "type": "rss",
                "name": rss["name"],
                "category": rss["category"],
                "url": rss["url"],
                "source_type": "website",
                "enabled": True
            })
        
        return sources
