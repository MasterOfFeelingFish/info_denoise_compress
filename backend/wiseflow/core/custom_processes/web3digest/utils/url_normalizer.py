"""
URL规范化工具 - 用于重复源检测
"""
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from typing import Optional


class URLNormalizer:
    """URL规范化工具类"""

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        规范化URL以进行重复检测

        步骤：
        1. 统一协议为https
        2. 移除www前缀
        3. 移除末尾斜杠（保留根路径/）
        4. 移除片段标识符（#fragment）
        5. 排序查询参数
        6. 域名转小写

        Args:
            url: 原始URL

        Returns:
            规范化后的URL

        Examples:
            >>> URLNormalizer.normalize_url("http://www.example.com/")
            'https://example.com'
            >>> URLNormalizer.normalize_url("https://example.com/path/")
            'https://example.com/path'
        """
        if not url or not url.strip():
            return ""

        url = url.strip()

        # 如果URL不包含协议，添加https://
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'

        try:
            parsed = urlparse(url)

            # 统一协议为https
            scheme = 'https'

            # 移除www前缀并转小写
            netloc = parsed.netloc.lower()
            if netloc.startswith('www.'):
                netloc = netloc[4:]

            # 规范化路径（移除末尾斜杠，但保留根路径/）
            path = parsed.path.rstrip('/') or '/'

            # 排序查询参数
            query = parsed.query
            if query:
                params = parse_qs(query, keep_blank_values=True)
                sorted_params = sorted(params.items())
                query = urlencode(sorted_params, doseq=True)

            # 忽略fragment
            normalized = urlunparse((scheme, netloc, path, parsed.params, query, ''))

            return normalized

        except Exception:
            # 如果解析失败，返回原URL
            return url

    @staticmethod
    def extract_twitter_username(url: str) -> Optional[str]:
        """
        从RSS.app URL中提取Twitter用户名

        RSS.app URL格式：
        - v1.1格式（用户名）：https://rss.app/feeds/v1.1/VitalikButerin.xml
        - Hash格式（16位字母数字）：https://rss.app/feeds/zXJZGK1tpoNrKUV1.xml

        Args:
            url: RSS.app URL

        Returns:
            Twitter用户名（如果是v1.1格式），否则返回None

        Examples:
            >>> URLNormalizer.extract_twitter_username("https://rss.app/feeds/v1.1/VitalikButerin.xml")
            'VitalikButerin'
            >>> URLNormalizer.extract_twitter_username("https://rss.app/feeds/zXJZGK1tpoNrKUV1.xml")
            None
        """
        if not url:
            return None

        try:
            parsed = urlparse(url)

            # 检查是否是rss.app域名
            if 'rss.app' not in parsed.netloc.lower():
                return None

            # 解析路径
            path_parts = parsed.path.strip('/').split('/')
            if not path_parts:
                return None

            # 获取文件名（最后一部分）
            filename = path_parts[-1]

            # 移除.xml后缀
            if filename.endswith('.xml'):
                username = filename[:-4]
            else:
                username = filename

            # v1.1格式 - 路径中包含v1.1
            if 'v1.1' in url:
                return username

            # Hash格式检测（16位字母数字）
            if len(username) == 16 and username.isalnum():
                return None  # 这是hash，不是用户名

            # 其他情况返回用户名
            return username

        except Exception:
            return None
