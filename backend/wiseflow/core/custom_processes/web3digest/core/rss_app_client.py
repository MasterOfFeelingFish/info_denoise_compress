"""
RSS.app 客户端 - 将 Twitter 账号转换为 RSS 源
"""
import httpx
import feedparser
import re
from datetime import datetime
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
        
        # 1. 优先使用已配置的真实 RSS.app 订阅链接
        if hasattr(DefaultRSSSources, 'RSSAPP_FEEDS'):
            for feed in DefaultRSSSources.RSSAPP_FEEDS:
                sources.append({
                    "type": "rss",
                    "name": feed["name"],
                    "category": feed["category"],
                    "url": feed["url"],
                    "source_type": "twitter",
                    "enabled": feed.get("enabled", True)
                })
        
        # 2. 其他 Twitter 账号（如果有 RSS.app Token 可以自动生成）
        # 这些账号需要用户手动在 RSS.app 创建订阅
        # for account in DefaultRSSSources.TWITTER_ACCOUNTS:
        #     username = account["name"]
        #     rss_url = self.get_twitter_rss_url(username)
        #     sources.append({...})
        
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


class RSSValidator:
    """RSS源深度验证器"""

    def __init__(self):
        self.timeout_twitter = 3  # Twitter源超时3秒
        self.timeout_website = 5  # 网站RSS超时5秒

    async def deep_verify_rss(self, url: str, source_type: str = "website") -> Dict:
        """
        深度验证RSS源

        五层验证：
        1. 网络可达性（HTTP 200-299，重定向跟踪，超时控制）
        2. Content-Type检查（xml/rss/atom）
        3. RSS解析验证（使用feedparser，区分严重错误和轻微警告）
        4. 内容质量（检查是否有效条目，标题和正文完整性）
        5. 时效性验证（最后更新时间，拒绝超过1年未更新的源）

        Args:
            url: RSS URL
            source_type: 源类型（"twitter" 或 "website"）

        Returns:
            {
                "valid": bool,
                "error_code": str,
                "error_message": str,
                "metadata": {...}
            }
        """
        timeout = self.timeout_twitter if source_type == "twitter" else self.timeout_website

        try:
            # Level 1: 网络可达性验证
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                try:
                    response = await client.get(url)
                except httpx.TimeoutException:
                    return self._error_result("TIMEOUT", "访问超时，该源可能响应较慢或不可用")
                except httpx.ConnectError:
                    return self._error_result("HTTP_ERROR", "无法连接到服务器，请检查URL是否正确")
                except httpx.HTTPStatusError as e:
                    return self._error_result("HTTP_ERROR", f"HTTP错误: {e.response.status_code}")
                except Exception as e:
                    return self._error_result("HTTP_ERROR", f"网络错误: {str(e)}")

                if response.status_code != 200:
                    return self._error_result("HTTP_ERROR", f"HTTP错误 {response.status_code}")

                content = response.content
                content_type = response.headers.get("content-type", "").lower()

            # Level 2: Content-Type检查（宽松）
            valid_types = ["xml", "rss", "atom"]
            if not any(t in content_type for t in valid_types):
                logger.warning(f"Unexpected Content-Type: {content_type} for {url}")

            # Level 3: 解析验证
            try:
                parsed = feedparser.parse(content)
            except Exception as e:
                return self._error_result("PARSE_ERROR", f"RSS解析失败: {str(e)}")

            if parsed.bozo:
                exception = parsed.bozo_exception
                # 区分严重错误和轻微问题
                if isinstance(exception, (feedparser.CharacterEncodingOverride, feedparser.NonXMLContentType)):
                    logger.debug(f"Minor parsing issue for {url}: {exception}")
                else:
                    return self._error_result("PARSE_ERROR", f"RSS格式错误: {type(exception).__name__}")

            # Level 4: 内容质量验证
            if not parsed.entries or len(parsed.entries) == 0:
                return self._error_result("EMPTY_FEED", "该RSS源当前没有任何内容，请确认URL是否正确")

            valid_entries = self._count_valid_entries(parsed.entries)
            if valid_entries == 0:
                return self._error_result("LOW_QUALITY_FEED", "该RSS源的内容质量不符合要求（缺少标题或正文）")

            # Level 5: 时效性验证
            metadata = {
                "feed_title": parsed.feed.get('title', ''),
                "entry_count": len(parsed.entries),
                "valid_entry_count": valid_entries
            }

            last_updated = self._get_last_updated(parsed)
            if last_updated:
                days_old = (datetime.now() - last_updated).days
                metadata["days_since_update"] = days_old

                if days_old > 365:
                    return self._error_result("STALE_FEED", f"该RSS源已{days_old}天未更新，可能已废弃")
                elif days_old > 90:
                    metadata["warning"] = f"该源已{days_old}天未更新"

            return {
                "valid": True,
                "error_code": None,
                "error_message": None,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"Verification failed for {url}: {e}", exc_info=True)
            return self._error_result("UNKNOWN_ERROR", f"验证失败: {str(e)}")

    async def verify_twitter_rss(self, username: str) -> Dict:
        """
        验证Twitter RSS源（RSS.app）

        特殊逻辑：
        1. 检查用户名格式（字母数字下划线，不超过15字符）
        2. 生成RSS.app URL
        3. 验证RSS可访问性
        4. 检查是否真的是Twitter内容（检查entry链接是否指向twitter.com/x.com）

        Args:
            username: Twitter用户名（不含@）

        Returns:
            验证结果字典
        """
        # 验证用户名格式
        username = username.lstrip('@').strip()
        if not re.match(r'^[A-Za-z0-9_]{1,15}$', username):
            return {
                "valid": False,
                "error_code": "INVALID_USERNAME",
                "error_message": "Twitter用户名格式不正确（仅支持字母、数字、下划线，不超过15字符）",
                "metadata": {}
            }

        # 生成URL并验证
        rss_url = f"https://rss.app/feeds/v1.1/{username}.xml"
        result = await self.deep_verify_rss(rss_url, source_type="twitter")

        if result["valid"]:
            # 额外检查：确保内容来自Twitter
            try:
                async with httpx.AsyncClient(timeout=self.timeout_twitter) as client:
                    response = await client.get(rss_url)
                    parsed = feedparser.parse(response.content)

                    if parsed.entries:
                        first_link = parsed.entries[0].get('link', '')
                        if not ('twitter.com' in first_link or 'x.com' in first_link):
                            result["metadata"]["warning"] = "警告：该RSS源可能不是真实的Twitter订阅"
            except Exception:
                pass  # 如果检查失败，忽略（主要验证已通过）

        return result

    def _count_valid_entries(self, entries: list) -> int:
        """统计有效条目数（有标题和内容）"""
        valid = 0
        for entry in entries[:10]:  # 只检查前10条
            has_title = bool(entry.get('title', '').strip())

            # 获取内容（可能在summary、description或content字段）
            content = (
                entry.get('summary', '') or
                entry.get('description', '') or
                (entry.get('content', [{}])[0].get('value', '') if entry.get('content') else '')
            )
            has_content = len(content.strip()) > 30  # 至少30个字符

            if has_title and has_content:
                valid += 1

        return valid

    def _get_last_updated(self, parsed) -> Optional[datetime]:
        """获取最后更新时间"""
        # 尝试feed级别的更新时间
        if parsed.feed.get('updated_parsed'):
            try:
                return datetime(*parsed.feed.updated_parsed[:6])
            except Exception:
                pass

        # 尝试第一个entry的发布时间
        if parsed.entries:
            entry = parsed.entries[0]
            if entry.get('published_parsed'):
                try:
                    return datetime(*entry.published_parsed[:6])
                except Exception:
                    pass
            if entry.get('updated_parsed'):
                try:
                    return datetime(*entry.updated_parsed[:6])
                except Exception:
                    pass

        return None

    def _error_result(self, code: str, message: str) -> Dict:
        """构造错误结果"""
        return {
            "valid": False,
            "error_code": code,
            "error_message": message,
            "metadata": {}
        }
