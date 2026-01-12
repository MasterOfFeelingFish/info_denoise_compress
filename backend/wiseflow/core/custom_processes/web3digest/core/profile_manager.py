"""
用户画像管理模块
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)


class ProfileManager:
    """用户画像管理器"""
    
    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR)
        self.profiles_dir = self.data_dir / "profiles"
        self._lock = asyncio.Lock()
    
    async def create_profile(self, user_id: int, profile_data: Dict) -> bool:
        """创建用户画像"""
        async with self._lock:
            profile_file = self.profiles_dir / f"{user_id}.txt"
            
            # 生成自然语言画像
            profile_text = await self._generate_profile_text(profile_data)
            
            # 保存到文件
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            with open(profile_file, 'w', encoding='utf-8') as f:
                f.write(profile_text)
            
            logger.info(f"创建用户画像: {user_id}")
            return True
    
    async def get_profile(self, user_id: int) -> Optional[str]:
        """获取用户画像（自然语言文本）"""
        profile_file = self.profiles_dir / f"{user_id}.txt"
        
        if profile_file.exists():
            with open(profile_file, 'r', encoding='utf-8') as f:
                return f.read()
        
        return None
    
    async def update_profile(self, user_id: int, profile_data: Dict) -> bool:
        """更新用户画像"""
        return await self.create_profile(user_id, profile_data)
    
    async def _generate_profile_text(self, profile_data: Dict) -> str:
        """根据结构化数据生成自然语言画像"""
        # 基础信息
        interests = profile_data.get("interests", [])
        projects = profile_data.get("projects", [])
        preferences = profile_data.get("preferences", {})
        
        # 生成画像文本
        profile_text = f"这是一个关注 Web3 领域的用户。\n\n"
        
        # 关注领域
        if interests:
            profile_text += f"【关注领域】\n"
            profile_text += f"• {', '.join(interests)}\n\n"
        
        # 关注项目
        if projects:
            profile_text += f"【关注项目】\n"
            profile_text += f"• {', '.join(projects)}\n\n"
        
        # 内容偏好
        content_types = preferences.get("content_types", [])
        if content_types:
            profile_text += f"【内容偏好】\n"
            for ct in content_types:
                profile_text += f"• {ct}\n"
            profile_text += "\n"
        
        # 信息源偏好
        sources = preferences.get("sources", [])
        if sources:
            profile_text += f"【偏好信息源】\n"
            for source in sources:
                profile_text += f"• {source}\n"
            profile_text += "\n"
        
        # 不喜欢的内容
        dislikes = preferences.get("dislikes", [])
        if dislikes:
            profile_text += f"【不感兴趣的内容】\n"
            for dislike in dislikes:
                profile_text += f"• {dislike}\n"
            profile_text += "\n"
        
        # 其他偏好
        if "info_volume" in preferences:
            profile_text += f"【信息量偏好】\n"
            profile_text += f"• {preferences['info_volume']}\n\n"
        
        profile_text += f"【创建时间】\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return profile_text
    
    async def update_ai_understanding(self, user_id: int, ai_understanding: str):
        """更新 AI 对用户的理解（基于反馈学习）"""
        current_profile = await self.get_profile(user_id) or ""
        
        # 在现有画像后添加 AI 理解部分
        updated_profile = current_profile.rstrip()
        
        # 如果已有 AI 理解部分，先移除
        if "【AI 学习理解】" in updated_profile:
            parts = updated_profile.split("【AI 学习理解】")
            updated_profile = parts[0].rstrip()
        
        # 添加新的 AI 理解
        updated_profile += f"\n\n【AI 学习理解】\n{ai_understanding}\n"
        updated_profile += f"\n【最后更新】\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # 保存更新后的画像
        profile_file = self.profiles_dir / f"{user_id}.txt"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        with open(profile_file, 'w', encoding='utf-8') as f:
            f.write(updated_profile)
        
        logger.info(f"更新 AI 理解: {user_id}")
