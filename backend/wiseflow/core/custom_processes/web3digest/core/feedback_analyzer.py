"""
反馈分析器 - 分析用户反馈并更新画像
"""
from typing import List, Dict
from datetime import datetime
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.feedback_manager import FeedbackManager
from core.custom_processes.web3digest.core.llm_client import LLMClient
from core.custom_processes.web3digest.core.profile_manager import ProfileManager

logger = setup_logger(__name__)


class FeedbackAnalyzer:
    """反馈分析器"""
    
    def __init__(self):
        self.feedback_manager = FeedbackManager()
        self.llm_client = LLMClient()
        self.profile_manager = ProfileManager()
        self.threshold = settings.FEEDBACK_UPDATE_THRESHOLD
    
    async def analyze_user_feedback(self, user_id: int) -> bool:
        """
        分析用户反馈并更新画像
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功更新画像
        """
        try:
            # 获取用户反馈历史
            feedbacks = await self.feedback_manager.get_user_feedbacks(user_id)
            
            if len(feedbacks) < self.threshold:
                logger.debug(f"用户 {user_id} 反馈数量 ({len(feedbacks)}) 未达到阈值 ({self.threshold})")
                return False
            
            # 获取当前画像
            current_profile = await self.profile_manager.get_profile(user_id)
            if not current_profile:
                logger.warning(f"用户 {user_id} 没有画像，无法更新")
                return False
            
            # 调用 LLM 分析反馈
            logger.info(f"开始分析用户 {user_id} 的反馈（共 {len(feedbacks)} 条）")
            ai_understanding = await self.llm_client.analyze_feedback(current_profile, feedbacks)
            
            if not ai_understanding or len(ai_understanding.strip()) < 10:
                logger.warning(f"用户 {user_id} 反馈分析结果为空或过短")
                return False
            
            # 更新画像
            await self.profile_manager.update_ai_understanding(user_id, ai_understanding)
            
            logger.info(f"✅ 用户 {user_id} 画像已更新")
            return True
            
        except Exception as e:
            logger.error(f"分析用户反馈失败 {user_id}: {e}", exc_info=True)
            return False
    
    async def check_and_analyze_all_users(self):
        """检查所有用户，对达到阈值的用户进行分析"""
        from core.custom_processes.web3digest.core.user_manager import UserManager
        
        user_manager = UserManager()
        users = await user_manager.get_active_users()
        
        analyzed_count = 0
        for user in users:
            user_id = int(user["id"])
            feedback_count = await self.feedback_manager.get_feedback_count(user_id)
            
            if feedback_count >= self.threshold:
                success = await self.analyze_user_feedback(user_id)
                if success:
                    analyzed_count += 1
        
        logger.info(f"反馈分析任务完成，共分析 {analyzed_count} 个用户的反馈")
        return analyzed_count
    
    async def analyze_if_threshold_reached(self, user_id: int) -> bool:
        """
        检查反馈数量，如果达到阈值则立即分析
        
        用于用户提交反馈后立即触发分析
        """
        feedback_count = await self.feedback_manager.get_feedback_count(user_id)
        
        if feedback_count >= self.threshold:
            logger.info(f"用户 {user_id} 反馈达到阈值 ({feedback_count} >= {self.threshold})，触发分析")
            return await self.analyze_user_feedback(user_id)
        
        return False
    
    async def update_profile_with_feedback(self, user_id: int, feedback_record: Dict) -> bool:
        """
        实时更新用户画像（基于单条反馈）- 使用结构化数据
        
        每次反馈都立即更新画像，不需要等待阈值
        """
        try:
            # 获取结构化画像数据
            structured_data = await self.profile_manager.get_structured_profile(user_id)
            if not structured_data:
                logger.warning(f"用户 {user_id} 没有结构化画像，无法更新")
                return False
            
            # 构建结构化反馈记录
            feedback_entry = {
                "timestamp": datetime.now().isoformat(),
                "overall": feedback_record.get("overall", ""),
                "reason_selected": feedback_record.get("reason_selected", []),
                "reason_text": feedback_record.get("reason_text", ""),
                "item_id": feedback_record.get("item_id"),
                "source": feedback_record.get("source")
            }
            
            # 更新反馈历史（结构化）
            feedback_history = structured_data.get("feedback_history", [])
            feedback_history.append(feedback_entry)
            # 只保留最近50条反馈，避免数据过大
            if len(feedback_history) > 50:
                feedback_history = feedback_history[-50:]
            
            # 更新统计
            stats = structured_data.get("stats", {})
            stats["total_feedbacks"] = stats.get("total_feedbacks", 0) + 1
            if feedback_entry["overall"] == "positive":
                stats["positive_count"] = stats.get("positive_count", 0) + 1
            elif feedback_entry["overall"] == "negative":
                stats["negative_count"] = stats.get("negative_count", 0) + 1
            stats["last_feedback_time"] = feedback_entry["timestamp"]
            
            # 根据反馈更新偏好（结构化数据，供AI使用）
            preferences = structured_data.get("preferences", {})
            
            if feedback_entry["overall"] == "negative" and feedback_entry["reason_selected"]:
                # 更新不感兴趣的内容列表
                dislikes = preferences.get("dislikes", [])
                for reason in feedback_entry["reason_selected"]:
                    if reason not in dislikes:
                        dislikes.append(reason)
                preferences["dislikes"] = dislikes
            
            if feedback_entry["overall"] == "positive":
                # 正面反馈：可以提取用户喜欢的内容
                likes = preferences.get("likes", [])
                if feedback_entry.get("source"):
                    if feedback_entry["source"] not in likes:
                        likes.append(feedback_entry["source"])
                preferences["likes"] = likes
            
            # 保存结构化数据
            await self.profile_manager.update_structured_profile(user_id, {
                "feedback_history": feedback_history,
                "stats": stats,
                "preferences": preferences
            })
            
            # 同时更新文本格式（用于显示）
            await self._update_text_profile_with_feedback(user_id, feedback_entry)
            
            logger.info(f"✅ 用户 {user_id} 画像已实时更新（结构化数据）")
            
            # 如果反馈数量达到阈值，触发深度分析
            feedback_count = await self.feedback_manager.get_feedback_count(user_id)
            if feedback_count >= self.threshold and feedback_count % self.threshold == 0:
                logger.info(f"用户 {user_id} 反馈达到阈值倍数，触发深度分析")
                await self.analyze_user_feedback(user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"实时更新画像失败 {user_id}: {e}", exc_info=True)
            return False
    
    async def _update_text_profile_with_feedback(self, user_id: int, feedback_entry: Dict):
        """更新文本格式的画像（用于显示）"""
        current_profile = await self.profile_manager.get_profile(user_id) or ""
        
        # 生成反馈摘要
        overall = feedback_entry.get("overall", "")
        reason_selected = feedback_entry.get("reason_selected", [])
        reason_text = feedback_entry.get("reason_text", "")
        
        feedback_summary = ""
        if overall == "positive":
            feedback_summary = "✅ 用户表示满意"
        elif overall == "negative":
            if reason_selected:
                feedback_summary = f"❌ 用户反馈：{', '.join(reason_selected)}"
            else:
                feedback_summary = "❌ 用户表示需要改进"
        
        if reason_text:
            feedback_summary += f"\n   说明：{reason_text[:100]}"
        
        # 获取现有的 AI 学习理解部分
        if "【AI 学习理解】" in current_profile:
            parts = current_profile.split("【AI 学习理解】")
            base_profile = parts[0].rstrip()
            existing_understanding = parts[1] if len(parts) > 1 else ""
        else:
            base_profile = current_profile.rstrip()
            existing_understanding = ""
        
        # 添加新的反馈记录
        timestamp = datetime.fromisoformat(feedback_entry["timestamp"]).strftime("%Y-%m-%d %H:%M")
        
        if existing_understanding:
            updated_understanding = existing_understanding.rstrip()
            updated_understanding += f"\n\n[{timestamp}] {feedback_summary}"
        else:
            updated_understanding = f"[{timestamp}] {feedback_summary}"
        
        # 更新画像文本
        updated_profile = base_profile
        updated_profile += f"\n\n【AI 学习理解】\n{updated_understanding}\n"
        updated_profile += f"\n【最后更新】\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # 保存文本格式
        profile_file = self.profile_manager.profiles_dir / f"{user_id}.txt"
        self.profile_manager.profiles_dir.mkdir(parents=True, exist_ok=True)
        
        if HAS_AIOFILES:
            async with aiofiles.open(profile_file, 'w', encoding='utf-8') as f:
                await f.write(updated_profile)
        else:
            with open(profile_file, 'w', encoding='utf-8') as f:
                f.write(updated_profile)