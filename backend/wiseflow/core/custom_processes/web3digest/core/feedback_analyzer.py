"""
反馈分析器 - 分析用户反馈并更新画像
"""
from typing import List, Dict
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
