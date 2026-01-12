"""
用户鉴权管理模块
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, Optional, List, Set
from enum import Enum
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)


class UserRole(str, Enum):
    """用户角色"""
    USER = "user"           # 普通用户
    ADMIN = "admin"         # 管理员
    SUPER_ADMIN = "super_admin"  # 超级管理员


class UserStatus(str, Enum):
    """用户状态"""
    ACTIVE = "active"       # 激活
    INACTIVE = "inactive"   # 未激活
    BANNED = "banned"       # 封禁
    SUSPENDED = "suspended"  # 暂停


class AuthManager:
    """用户鉴权管理器"""
    
    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR)
        self.auth_file = self.data_dir / "auth.json"
        self._auth_cache = None
        self._lock = asyncio.Lock()
        
        # 从环境变量加载管理员列表
        self._load_admin_from_env()
    
    def _load_admin_from_env(self):
        """从环境变量加载管理员 Telegram ID"""
        import os
        admin_ids_str = os.getenv("ADMIN_TELEGRAM_IDS", "")
        if admin_ids_str:
            try:
                admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
                self._env_admins = set(admin_ids)
                logger.info(f"从环境变量加载 {len(self._env_admins)} 个管理员")
            except ValueError:
                logger.warning("环境变量 ADMIN_TELEGRAM_IDS 格式错误，忽略")
                self._env_admins = set()
        else:
            self._env_admins = set()
    
    async def _load_auth_data(self) -> Dict:
        """加载鉴权数据"""
        if self._auth_cache is None:
            if self.auth_file.exists():
                try:
                    with open(self.auth_file, 'r', encoding='utf-8') as f:
                        self._auth_cache = json.load(f)
                except Exception as e:
                    logger.error(f"加载鉴权数据失败: {e}")
                    self._auth_cache = self._get_default_auth_data()
            else:
                self._auth_cache = self._get_default_auth_data()
        return self._auth_cache
    
    def _get_default_auth_data(self) -> Dict:
        """获取默认鉴权数据"""
        return {
            "users": {},  # user_id -> {role, status, permissions}
            "whitelist": [],  # 白名单用户 ID 列表
            "blacklist": [],  # 黑名单用户 ID 列表
            "admin_ids": list(self._env_admins)  # 管理员 ID 列表
        }
    
    async def _save_auth_data(self, auth_data: Dict):
        """保存鉴权数据"""
        async with self._lock:
            self.auth_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.auth_file, 'w', encoding='utf-8') as f:
                json.dump(auth_data, f, ensure_ascii=False, indent=2)
            self._auth_cache = auth_data
    
    async def check_user_access(self, user_id: int) -> bool:
        """
        检查用户是否有访问权限
        
        Returns:
            True: 允许访问
            False: 拒绝访问
        """
        auth_data = await self._load_auth_data()
        
        # 检查黑名单
        if str(user_id) in auth_data.get("blacklist", []):
            logger.warning(f"用户 {user_id} 在黑名单中，拒绝访问")
            return False
        
        # 检查白名单（如果启用白名单模式）
        whitelist = auth_data.get("whitelist", [])
        if whitelist:  # 如果白名单不为空，则只允许白名单用户
            if str(user_id) not in whitelist:
                logger.info(f"用户 {user_id} 不在白名单中，拒绝访问")
                return False
        
        # 检查用户状态
        user_auth = auth_data.get("users", {}).get(str(user_id), {})
        status = user_auth.get("status", UserStatus.ACTIVE.value)
        
        if status == UserStatus.BANNED.value:
            logger.warning(f"用户 {user_id} 已被封禁，拒绝访问")
            return False
        
        if status == UserStatus.SUSPENDED.value:
            logger.info(f"用户 {user_id} 已被暂停，拒绝访问")
            return False
        
        return True
    
    async def check_user_role(self, user_id: int, required_role: UserRole) -> bool:
        """检查用户角色是否满足要求"""
        auth_data = await self._load_auth_data()
        
        # 检查环境变量中的管理员
        if user_id in self._env_admins:
            if required_role == UserRole.ADMIN or required_role == UserRole.SUPER_ADMIN:
                return True
        
        # 检查配置文件中的管理员
        if user_id in auth_data.get("admin_ids", []):
            if required_role == UserRole.ADMIN or required_role == UserRole.SUPER_ADMIN:
                return True
        
        # 检查用户角色
        user_auth = auth_data.get("users", {}).get(str(user_id), {})
        user_role = user_auth.get("role", UserRole.USER.value)
        
        if required_role == UserRole.USER:
            return True
        
        if required_role == UserRole.ADMIN:
            return user_role in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]
        
        if required_role == UserRole.SUPER_ADMIN:
            return user_role == UserRole.SUPER_ADMIN.value
        
        return False
    
    async def is_admin(self, user_id: int) -> bool:
        """检查用户是否是管理员"""
        return await self.check_user_role(user_id, UserRole.ADMIN)
    
    async def get_user_role(self, user_id: int) -> UserRole:
        """获取用户角色"""
        auth_data = await self._load_auth_data()
        
        # 检查环境变量中的管理员
        if user_id in self._env_admins:
            return UserRole.SUPER_ADMIN
        
        # 检查配置文件中的管理员
        if user_id in auth_data.get("admin_ids", []):
            return UserRole.ADMIN
        
        # 检查用户角色
        user_auth = auth_data.get("users", {}).get(str(user_id), {})
        role_str = user_auth.get("role", UserRole.USER.value)
        
        try:
            return UserRole(role_str)
        except ValueError:
            return UserRole.USER
    
    async def get_user_status(self, user_id: int) -> UserStatus:
        """获取用户状态"""
        auth_data = await self._load_auth_data()
        user_auth = auth_data.get("users", {}).get(str(user_id), {})
        status_str = user_auth.get("status", UserStatus.ACTIVE.value)
        
        try:
            return UserStatus(status_str)
        except ValueError:
            return UserStatus.ACTIVE
    
    async def set_user_role(self, user_id: int, role: UserRole, operator_id: int) -> bool:
        """设置用户角色（需要管理员权限）"""
        if not await self.is_admin(operator_id):
            logger.warning(f"用户 {operator_id} 尝试设置角色但无权限")
            return False
        
        auth_data = await self._load_auth_data()
        
        if "users" not in auth_data:
            auth_data["users"] = {}
        
        if str(user_id) not in auth_data["users"]:
            auth_data["users"][str(user_id)] = {}
        
        auth_data["users"][str(user_id)]["role"] = role.value
        await self._save_auth_data(auth_data)
        
        logger.info(f"管理员 {operator_id} 设置用户 {user_id} 角色为 {role.value}")
        return True
    
    async def set_user_status(self, user_id: int, status: UserStatus, operator_id: int) -> bool:
        """设置用户状态（需要管理员权限）"""
        if not await self.is_admin(operator_id):
            logger.warning(f"用户 {operator_id} 尝试设置状态但无权限")
            return False
        
        auth_data = await self._load_auth_data()
        
        if "users" not in auth_data:
            auth_data["users"] = {}
        
        if str(user_id) not in auth_data["users"]:
            auth_data["users"][str(user_id)] = {}
        
        auth_data["users"][str(user_id)]["status"] = status.value
        await self._save_auth_data(auth_data)
        
        logger.info(f"管理员 {operator_id} 设置用户 {user_id} 状态为 {status.value}")
        return True
    
    async def add_to_whitelist(self, user_id: int, operator_id: int) -> bool:
        """添加用户到白名单（需要管理员权限）"""
        if not await self.is_admin(operator_id):
            return False
        
        auth_data = await self._load_auth_data()
        
        if "whitelist" not in auth_data:
            auth_data["whitelist"] = []
        
        user_id_str = str(user_id)
        if user_id_str not in auth_data["whitelist"]:
            auth_data["whitelist"].append(user_id_str)
            await self._save_auth_data(auth_data)
            logger.info(f"管理员 {operator_id} 将用户 {user_id} 添加到白名单")
            return True
        
        return False
    
    async def remove_from_whitelist(self, user_id: int, operator_id: int) -> bool:
        """从白名单移除用户（需要管理员权限）"""
        if not await self.is_admin(operator_id):
            return False
        
        auth_data = await self._load_auth_data()
        
        if "whitelist" not in auth_data:
            return False
        
        user_id_str = str(user_id)
        if user_id_str in auth_data["whitelist"]:
            auth_data["whitelist"].remove(user_id_str)
            await self._save_auth_data(auth_data)
            logger.info(f"管理员 {operator_id} 将用户 {user_id} 从白名单移除")
            return True
        
        return False
    
    async def add_to_blacklist(self, user_id: int, operator_id: int) -> bool:
        """添加用户到黑名单（需要管理员权限）"""
        if not await self.is_admin(operator_id):
            return False
        
        auth_data = await self._load_auth_data()
        
        if "blacklist" not in auth_data:
            auth_data["blacklist"] = []
        
        user_id_str = str(user_id)
        if user_id_str not in auth_data["blacklist"]:
            auth_data["blacklist"].append(user_id_str)
            await self._save_auth_data(auth_data)
            logger.info(f"管理员 {operator_id} 将用户 {user_id} 添加到黑名单")
            return True
        
        return False
    
    async def remove_from_blacklist(self, user_id: int, operator_id: int) -> bool:
        """从黑名单移除用户（需要管理员权限）"""
        if not await self.is_admin(operator_id):
            return False
        
        auth_data = await self._load_auth_data()
        
        if "blacklist" not in auth_data:
            return False
        
        user_id_str = str(user_id)
        if user_id_str in auth_data["blacklist"]:
            auth_data["blacklist"].remove(user_id_str)
            await self._save_auth_data(auth_data)
            logger.info(f"管理员 {operator_id} 将用户 {user_id} 从黑名单移除")
            return True
        
        return False
    
    async def get_whitelist(self) -> List[int]:
        """获取白名单列表（需要管理员权限）"""
        auth_data = await self._load_auth_data()
        return [int(uid) for uid in auth_data.get("whitelist", [])]
    
    async def get_blacklist(self) -> List[int]:
        """获取黑名单列表（需要管理员权限）"""
        auth_data = await self._load_auth_data()
        return [int(uid) for uid in auth_data.get("blacklist", [])]
    
    async def get_all_admins(self) -> List[int]:
        """获取所有管理员 ID"""
        auth_data = await self._load_auth_data()
        admin_ids = set(auth_data.get("admin_ids", []))
        admin_ids.update(self._env_admins)
        return list(admin_ids)
