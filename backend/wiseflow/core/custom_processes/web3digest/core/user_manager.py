"""
用户管理模块
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)


class UserManager:
    """用户管理器"""
    
    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR)
        self.users_file = self.data_dir / "users.json"
        self._users_cache = None
        self._lock = asyncio.Lock()
    
    async def register_user(self, telegram_id: int, name: str) -> bool:
        """注册用户，返回是否是新用户"""
        async with self._lock:
            users = await self._load_users()
            
            user_id = str(telegram_id)
            
            if user_id in users:
                # 更新最后活跃时间
                users[user_id]["last_active"] = datetime.now().isoformat()
                await self._save_users(users)
                return False
            else:
                # 新用户
                users[user_id] = {
                    "id": user_id,
                    "telegram_id": telegram_id,
                    "name": name,
                    "created": datetime.now().isoformat(),
                    "last_active": datetime.now().isoformat(),
                    "status": "active"
                }
                await self._save_users(users)
                logger.info(f"新用户注册: {name} ({telegram_id})")
                return True
    
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """获取用户信息"""
        users = await self._load_users()
        return users.get(str(telegram_id))
    
    async def update_last_active(self, telegram_id: int):
        """更新用户最后活跃时间"""
        async with self._lock:
            users = await self._load_users()
            user_id = str(telegram_id)
            
            if user_id in users:
                users[user_id]["last_active"] = datetime.now().isoformat()
                await self._save_users(users)
    
    async def get_all_users(self) -> List[Dict]:
        """获取所有用户"""
        users = await self._load_users()
        return list(users.values())
    
    async def get_active_users(self) -> List[Dict]:
        """获取活跃用户"""
        users = await self._load_users()
        return [user for user in users.values() if user.get("status") == "active"]
    
    async def _load_users(self) -> Dict:
        """加载用户数据"""
        if self._users_cache is None:
            if self.users_file.exists():
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    self._users_cache = json.load(f)
            else:
                self._users_cache = {}
        return self._users_cache
    
    async def _save_users(self, users: Dict):
        """保存用户数据"""
        # 确保目录存在
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存到文件
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        
        # 更新缓存
        self._users_cache = users
