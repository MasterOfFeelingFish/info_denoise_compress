"""
用户画像管理模块
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)


class ProfileManager:
    """用户画像管理器"""

    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR)
        self.profiles_dir = self.data_dir / "profiles"
        # 为每个用户创建独立的锁，避免不同用户之间的锁竞争
        self._user_locks: Dict[int, asyncio.Lock] = {}

    def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        """获取用户锁（延迟创建）"""
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def create_profile(self, user_id: int, profile_data: Dict) -> bool:
        """创建用户画像"""
        user_lock = self._get_user_lock(user_id)
        async with user_lock:
            # 保存结构化数据（JSON格式，供AI使用）
            json_file = self.profiles_dir / f"{user_id}.json"
            # 保存文本格式（用于显示）
            txt_file = self.profiles_dir / f"{user_id}.txt"
            
            # 构建完整的结构化数据
            structured_data = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "interests": profile_data.get("interests", []),
                "projects": profile_data.get("projects", []),
                "preferences": profile_data.get("preferences", {}),
                "feedback_history": [],  # 反馈历史（结构化）
                "ai_understanding": "",  # AI学习理解（文本）
                "stats": {
                    "total_feedbacks": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "last_feedback_time": None
                }
            }
            
            # 保存结构化数据
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(structured_data, f, ensure_ascii=False, indent=2)
            
            # 生成并保存自然语言画像（用于显示）
            profile_text = await self._generate_profile_text(profile_data)
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(profile_text)
            
            logger.info(f"创建用户画像: {user_id} (结构化数据已保存)")
            return True
    
    async def get_profile(self, user_id: int) -> Optional[str]:
        """获取用户画像（自然语言文本，用于显示）"""
        user_lock = self._get_user_lock(user_id)
        async with user_lock:
            profile_file = self.profiles_dir / f"{user_id}.txt"

            if profile_file.exists():
                # 使用异步文件读取，避免阻塞
                if HAS_AIOFILES:
                    async with aiofiles.open(profile_file, 'r', encoding='utf-8') as f:
                        return await f.read()
                else:
                    # 如果没有 aiofiles，使用同步读取（在线程池中执行，避免阻塞事件循环）
                    def _read_file():
                        with open(profile_file, 'r', encoding='utf-8') as f:
                            return f.read()

                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, _read_file)

            return None
    
    async def _read_structured_profile_unlocked(self, user_id: int) -> Optional[Dict]:
        """读取结构化画像（内部方法，不加锁）"""
        json_file = self.profiles_dir / f"{user_id}.json"

        if json_file.exists():
            if HAS_AIOFILES:
                async with aiofiles.open(json_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                def _read_file():
                    with open(json_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _read_file)

        return None

    async def get_structured_profile(self, user_id: int) -> Optional[Dict]:
        """获取用户画像（结构化数据，供AI使用）"""
        user_lock = self._get_user_lock(user_id)
        async with user_lock:
            json_file = self.profiles_dir / f"{user_id}.json"

            if json_file.exists():
                return await self._read_structured_profile_unlocked(user_id)
            else:
                # 如果JSON不存在但TXT存在，尝试从TXT创建JSON（迁移）
                txt_file = self.profiles_dir / f"{user_id}.txt"
                if txt_file.exists():
                    logger.info(f"用户 {user_id} 的画像需要迁移到结构化格式")
                    # 在锁内执行迁移，迁移后直接读取（避免递归调用）
                    success = await self._migrate_text_to_structured(user_id)
                    if success:
                        return await self._read_structured_profile_unlocked(user_id)

            return None
    
    async def _migrate_text_to_structured(self, user_id: int) -> bool:
        """从文本格式迁移到结构化格式"""
        try:
            txt_file = self.profiles_dir / f"{user_id}.txt"
            if not txt_file.exists():
                return False
            
            # 读取文本画像
            if HAS_AIOFILES:
                async with aiofiles.open(txt_file, 'r', encoding='utf-8') as f:
                    text_content = await f.read()
            else:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    text_content = f.read()
            
            # 解析文本内容，提取结构化数据
            structured_data = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "interests": [],
                "projects": [],
                "preferences": {},
                "feedback_history": [],
                "ai_understanding": "",
                "stats": {
                    "total_feedbacks": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "last_feedback_time": None
                }
            }
            
            # 简单解析文本内容
            if "【关注领域】" in text_content:
                parts = text_content.split("【关注领域】")
                if len(parts) > 1:
                    interests_line = parts[1].split("\n")[0]
                    interests = [x.strip() for x in interests_line.replace("•", "").split(",") if x.strip()]
                    structured_data["interests"] = interests
            
            if "【AI 学习理解】" in text_content:
                parts = text_content.split("【AI 学习理解】")
                if len(parts) > 1:
                    understanding = parts[1].split("【最后更新】")[0].strip()
                    structured_data["ai_understanding"] = understanding
            
            # 保存结构化数据
            json_file = self.profiles_dir / f"{user_id}.json"
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            
            if HAS_AIOFILES:
                async with aiofiles.open(json_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(structured_data, ensure_ascii=False, indent=2))
            else:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(structured_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"用户 {user_id} 画像已迁移到结构化格式")
            return True
            
        except Exception as e:
            logger.error(f"迁移画像失败 {user_id}: {e}", exc_info=True)
            return False
    
    async def get_push_time(self, user_id: int) -> str:
        """获取用户推送时间设置（默认返回系统设置）"""
        structured_data = await self.get_structured_profile(user_id)
        if structured_data:
            preferences = structured_data.get("preferences", {})
            push_time = preferences.get("push_time")
            if push_time:
                return push_time
        
        # 返回系统默认时间
        from core.custom_processes.web3digest.core.config import settings
        return settings.DAILY_PUSH_TIME
    
    async def update_push_time(self, user_id: int, push_time: str) -> bool:
        """更新用户推送时间设置"""
        # 验证时间格式 (HH:MM)
        try:
            hour, minute = push_time.split(":")
            hour = int(hour)
            minute = int(minute)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return False
        except:
            return False
        
        # 获取现有结构化数据
        structured_data = await self.get_structured_profile(user_id)
        if not structured_data:
            return False
        
        # 更新推送时间
        if "preferences" not in structured_data:
            structured_data["preferences"] = {}
        
        structured_data["preferences"]["push_time"] = push_time
        structured_data["updated_at"] = datetime.now().isoformat()
        
        # 保存
        return await self.update_structured_profile(user_id, {
            "preferences": structured_data["preferences"],
            "updated_at": structured_data["updated_at"]
        })
    
    async def update_structured_profile(self, user_id: int, updates: Dict) -> bool:
        """更新结构化画像数据"""
        user_lock = self._get_user_lock(user_id)
        async with user_lock:
            json_file = self.profiles_dir / f"{user_id}.json"

            # 读取现有数据（使用无锁版本，因为已经在锁内）
            structured_data = await self._read_structured_profile_unlocked(user_id)
            if not structured_data:
                logger.warning(f"用户 {user_id} 没有结构化画像，无法更新")
                return False

            # 更新数据
            structured_data["updated_at"] = datetime.now().isoformat()

            # 合并更新
            if "interests" in updates:
                structured_data["interests"] = updates["interests"]
            if "projects" in updates:
                structured_data["projects"] = updates["projects"]
            if "preferences" in updates:
                structured_data["preferences"].update(updates["preferences"])
            if "feedback_history" in updates:
                structured_data["feedback_history"].extend(updates["feedback_history"])
            if "ai_understanding" in updates:
                structured_data["ai_understanding"] = updates["ai_understanding"]
            if "stats" in updates:
                structured_data["stats"].update(updates["stats"])

            # 保存
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            if HAS_AIOFILES:
                async with aiofiles.open(json_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(structured_data, ensure_ascii=False, indent=2))
            else:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(structured_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"更新用户 {user_id} 的结构化画像")
            return True
    
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
        # 更新结构化数据
        await self.update_structured_profile(user_id, {"ai_understanding": ai_understanding})
        
        # 更新文本格式（用于显示）
        current_profile = await self.get_profile(user_id) or ""
        updated_profile = current_profile.rstrip()
        
        # 如果已有 AI 学习理解部分，先移除
        if "【AI 学习理解】" in updated_profile:
            parts = updated_profile.split("【AI 学习理解】")
            updated_profile = parts[0].rstrip()
        
        # 添加新的 AI 理解
        updated_profile += f"\n\n【AI 学习理解】\n{ai_understanding}\n"
        updated_profile += f"\n【最后更新】\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # 保存更新后的文本画像
        profile_file = self.profiles_dir / f"{user_id}.txt"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        if HAS_AIOFILES:
            async with aiofiles.open(profile_file, 'w', encoding='utf-8') as f:
                await f.write(updated_profile)
        else:
            with open(profile_file, 'w', encoding='utf-8') as f:
                f.write(updated_profile)
        
        logger.info(f"更新 AI 理解: {user_id}")
