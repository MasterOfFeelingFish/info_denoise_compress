"""
Rate Limiter Service

防止用户高频交互导致服务器资源耗尽。
使用内存缓存记录每个用户的交互频率。
"""
import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from config import RATE_LIMIT_PER_MINUTE, ADMIN_TELEGRAM_IDS

logger = logging.getLogger(__name__)

# 冷却时间固定为 60 秒
COOLDOWN_SECONDS = 60


class RateLimiter:
    """用户交互频率限制器"""
    
    def __init__(self):
        # user_id -> list of timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)
        # user_id -> cooldown end time
        self._cooldowns: Dict[str, float] = {}
    
    def _cleanup_old_requests(self, user_id: str, now: float) -> None:
        """清理超过 1 分钟的旧请求记录"""
        one_minute_ago = now - 60
        self._requests[user_id] = [
            t for t in self._requests[user_id] if t > one_minute_ago
        ]
    
    def is_rate_limited(self, user_id: str) -> tuple[bool, Optional[str]]:
        """
        检查用户是否被限制。
        
        Returns:
            (is_limited, reason) - 如果被限制，返回 (True, 原因)
        """
        # 频率限制禁用
        if RATE_LIMIT_PER_MINUTE <= 0:
            return False, None
        
        # 管理员不受限制
        if user_id in ADMIN_TELEGRAM_IDS:
            return False, None
        
        now = time.time()
        
        # 检查是否在冷却期
        if user_id in self._cooldowns:
            if now < self._cooldowns[user_id]:
                remaining = int(self._cooldowns[user_id] - now)
                return True, f"请等待 {remaining} 秒后再试"
            else:
                del self._cooldowns[user_id]
        
        # 清理旧记录
        self._cleanup_old_requests(user_id, now)
        
        # 检查每分钟限制
        recent_count = len(self._requests[user_id])
        if recent_count >= RATE_LIMIT_PER_MINUTE:
            self._cooldowns[user_id] = now + COOLDOWN_SECONDS
            logger.warning(f"Rate limit triggered for user {user_id}: {recent_count}/min")
            return True, f"操作过于频繁，请等待 {COOLDOWN_SECONDS} 秒"
        
        return False, None
    
    def record_request(self, user_id: str) -> None:
        """记录一次用户请求"""
        if RATE_LIMIT_PER_MINUTE > 0 and user_id not in ADMIN_TELEGRAM_IDS:
            self._requests[user_id].append(time.time())


# 全局单例
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """获取全局频率限制器实例"""
    return _rate_limiter
