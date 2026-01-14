"""
反馈管理模块
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)


class FeedbackManager:
    """反馈管理器"""

    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR) / "feedback"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # 文件锁字典，每个文件一个锁
        self._file_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_feedback_file(self, feedback_date: date = None) -> Path:
        """获取反馈文件路径"""
        if feedback_date is None:
            feedback_date = date.today()
        return self.data_dir / f"{feedback_date.isoformat()}.json"

    def _get_file_lock(self, file_path: Path) -> asyncio.Lock:
        """获取文件锁（延迟创建）"""
        file_key = str(file_path)
        if file_key not in self._file_locks:
            self._file_locks[file_key] = asyncio.Lock()
        return self._file_locks[file_key]
    
    async def save_feedback(self, user_id: int, overall: str, reason_selected: List[str] = None, 
                           reason_text: str = None, item_feedbacks: List[Dict] = None) -> bool:
        """
        保存用户反馈
        
        Args:
            user_id: 用户ID
            overall: 整体评价 ("positive" 或 "negative")
            reason_selected: 选择的原因列表（负面反馈时）
            reason_text: 原因文本（负面反馈时）
            item_feedbacks: 单条信息的反馈列表
        """
        try:
            feedback_date = date.today()
            feedback_file = self._get_feedback_file(feedback_date)
            
            # 读取现有反馈
            feedbacks_data = {"date": feedback_date.isoformat(), "feedbacks": []}
            if feedback_file.exists():
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks_data = json.load(f)
            
            # 创建新反馈记录
            feedback_record = {
                "user_id": str(user_id),
                "time": datetime.now().strftime("%H:%M"),
                "overall": overall,
                "reason_selected": reason_selected or [],
                "reason_text": reason_text or "",
                "item_feedbacks": item_feedbacks or []
            }
            
            # 添加到列表
            feedbacks_data["feedbacks"].append(feedback_record)
            
            # 保存
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"保存用户 {user_id} 的反馈: {overall}")
            
            # 每次反馈都实时更新画像
            from core.custom_processes.web3digest.core.feedback_analyzer import FeedbackAnalyzer
            analyzer = FeedbackAnalyzer()
            # 实时更新画像（基于单条反馈）
            await analyzer.update_profile_with_feedback(user_id, feedback_record)
            # 如果达到阈值，触发深度分析
            await analyzer.analyze_if_threshold_reached(user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"保存反馈失败: {e}", exc_info=True)
            return False
    
    async def get_user_feedbacks(self, user_id: int, days: int = 30) -> List[Dict]:
        """获取用户的反馈历史"""
        feedbacks = []
        
        try:
            # 读取最近几天的反馈文件
            for i in range(days):
                feedback_date = date.today() - timedelta(days=i)
                feedback_file = self._get_feedback_file(feedback_date)
                
                if not feedback_file.exists():
                    continue
                
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks_data = json.load(f)
                
                # 筛选该用户的反馈
                for fb in feedbacks_data.get("feedbacks", []):
                    if fb.get("user_id") == str(user_id):
                        fb["date"] = feedback_date.isoformat()
                        feedbacks.append(fb)
            
            # 按时间倒序排列
            feedbacks.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
            
        except Exception as e:
            logger.error(f"获取用户反馈失败: {e}", exc_info=True)
        
        return feedbacks
    
    async def get_feedback_count(self, user_id: int) -> int:
        """获取用户的反馈总数"""
        feedbacks = await self.get_user_feedbacks(user_id)
        return len(feedbacks)
    
    async def add_item_feedback(self, user_id: int, item_id: str, source: str, rating: str) -> bool:
        """
        添加单条信息的反馈
        
        Args:
            user_id: 用户ID
            item_id: 信息ID
            source: 信息来源
            rating: 评价 ("like" 或 "dislike")
        """
        try:
            feedback_date = date.today()
            feedback_file = self._get_feedback_file(feedback_date)
            
            # 读取现有反馈
            feedbacks_data = {"date": feedback_date.isoformat(), "feedbacks": []}
            if feedback_file.exists():
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks_data = json.load(f)
            
            # 查找或创建今天的反馈记录
            today_feedback = None
            for fb in feedbacks_data.get("feedbacks", []):
                if fb.get("user_id") == str(user_id) and fb.get("date", feedback_date.isoformat()) == feedback_date.isoformat():
                    today_feedback = fb
                    break
            
            if not today_feedback:
                # 创建新记录
                today_feedback = {
                    "user_id": str(user_id),
                    "time": datetime.now().strftime("%H:%M"),
                    "overall": "",
                    "reason_selected": [],
                    "reason_text": "",
                    "item_feedbacks": []
                }
                feedbacks_data["feedbacks"].append(today_feedback)
            
            # 添加单条反馈
            item_feedback = {
                "item_id": item_id,
                "source": source,
                "rating": rating
            }
            today_feedback["item_feedbacks"].append(item_feedback)
            
            # 保存
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"保存用户 {user_id} 的单条反馈: {item_id} - {rating}")
            
            # 单条反馈也实时更新画像
            from core.custom_processes.web3digest.core.feedback_analyzer import FeedbackAnalyzer
            analyzer = FeedbackAnalyzer()
            # 构建反馈记录格式
            feedback_record = {
                "overall": "positive" if rating == "like" else "negative",
                "reason_selected": [f"单条信息{'喜欢' if rating == 'like' else '不感兴趣'}"],
                "reason_text": f"信息ID: {item_id}, 来源: {source}"
            }
            await analyzer.update_profile_with_feedback(user_id, feedback_record)
            
            return True
            
        except Exception as e:
            logger.error(f"保存单条反馈失败: {e}", exc_info=True)
            return False
