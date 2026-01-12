"""
对话管理模块 - 处理 3 轮对话式偏好收集
"""
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.profile_manager import ProfileManager
from core.custom_processes.web3digest.core.llm_client import LLMClient

logger = setup_logger(__name__)


class ConversationManager:
    """对话管理器"""
    
    def __init__(self):
        self.profile_manager = ProfileManager()
        self.llm_client = LLMClient()
        self._conversations: Dict[int, Dict] = {}  # user_id -> conversation_state
    
    async def start_preference_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """开始偏好收集对话"""
        user_id = update.effective_user.id
        
        # 初始化对话状态
        self._conversations[user_id] = {
            "stage": 1,  # 当前轮次
            "start_time": datetime.now(),
            "data": {}  # 收集的数据
        }
        
        # 发送第一轮问题
        await self._send_stage1_question(update, context)
    
    async def is_in_conversation(self, user_id: int) -> bool:
        """检查用户是否在对话中"""
        return user_id in self._conversations
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理用户回复"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        if user_id not in self._conversations:
            return
        
        conversation = self._conversations[user_id]
        stage = conversation["stage"]
        
        # 根据当前轮次处理
        if stage == 1:
            await self._handle_stage1_response(update, context, message_text)
            conversation["stage"] = 2
        elif stage == 2:
            await self._handle_stage2_response(update, context, message_text)
            conversation["stage"] = 3
        elif stage == 3:
            await self._handle_stage3_response(update, context, message_text)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮点击"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        if user_id not in self._conversations:
            return
        
        # 处理确认按钮
        if data == "conv_confirm":
            await self._confirm_preferences(update, context)
        elif data == "conv_edit":
            await self._edit_preferences(update, context)
        elif data.startswith("conv_select_"):
            # 处理选择类问题
            selected = data.split("_", 2)[2]
            await self._handle_selection(update, context, selected)
    
    async def _handle_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, selected: str):
        """处理选择类问题（占位）"""
        pass
    
    async def _send_stage1_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """发送第一轮问题 - 关注领域"""
        text = """
🎯 **第一步：告诉我您关注哪些 Web3 领域？**

请用自然语言描述，例如：
• "我主要玩 DeFi 和 Layer2"
• "我比较关注比特币生态和 NFT"
• "我是开发者，关注技术进展"

您可以说得具体一些，这样我能更好地为您筛选信息。
        """
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _handle_stage1_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """处理第一轮回复"""
        user_id = update.effective_user.id
        
        # 使用 LLM 提取关注领域
        interests = await self._extract_interests(response)
        
        # 保存数据
        self._conversations[user_id]["data"]["interests_response"] = response
        self._conversations[user_id]["data"]["interests"] = interests
        
        # 发送第二轮问题
        await self._send_stage2_question(update, context)
    
    async def _send_stage2_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """发送第二轮问题 - 具体内容和信息源"""
        user_id = update.effective_user.id
        interests = self._conversations[user_id]["data"].get("interests", [])
        
        text = f"""
📊 **第二步：您更关注哪些类型的信息？**

基于您提到的 {', '.join(interests[:3]) if interests else 'Web3'}，请告诉我：

1. **内容类型**：比如技术进展、市场分析、融资动态、项目公告等
2. **信息来源**：比如您常看哪些 KOL 或项目方（@VitalikButerin、@arbitrum 等）
3. **特殊偏好**：比如链上数据大户操作、空投信息、技术深度分析等

示例：
"我主要看链上数据，特别是大户动向，还关注空投信息"
        """
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _handle_stage2_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """处理第二轮回复"""
        user_id = update.effective_user.id
        
        # 使用 LLM 提取偏好
        preferences = await self._extract_preferences(response)
        
        # 保存数据
        self._conversations[user_id]["data"]["preferences_response"] = response
        self._conversations[user_id]["data"]["preferences"] = preferences
        
        # 发送第三轮问题
        await self._send_stage3_question(update, context)
    
    async def _send_stage3_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """发送第三轮问题 - 信息量和补充"""
        text = """
⚖️ **最后一步：信息量和补充说明**

1. **信息量偏好**：您希望每天看到多少条信息？
   • 精简版（5-10 条）
   • 标准版（10-20 条）
   • 丰富版（20-30 条）

2. **补充说明**：还有什么特殊需求吗？比如：
   • "我不喜欢看价格预测"
   • "主要关注中文内容"
   • "对 Meme 币不感兴趣"

请告诉我您的偏好。
        """
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _handle_stage3_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """处理第三轮回复"""
        user_id = update.effective_user.id
        
        # 提取信息量偏好和其他要求
        volume_prefs = await self._extract_volume_preferences(response)
        
        # 保存数据
        self._conversations[user_id]["data"]["volume_response"] = response
        self._conversations[user_id]["data"]["volume_preferences"] = volume_prefs
        
        # 生成确认信息
        await self._send_confirmation(update, context)
    
    async def _send_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """发送确认信息"""
        user_id = update.effective_user.id
        data = self._conversations[user_id]["data"]
        
        # 生成总结
        summary = await self._generate_preference_summary(data)
        
        text = f"""
✅ **请确认您的偏好设置**

{summary}

如果确认无误，我将为您生成个性化简报。如需修改，可以重新设置。

**注意**：您随时可以使用 /profile 命令查看和更新偏好。
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ 确认设置", callback_data="conv_confirm")],
            [InlineKeyboardButton("✏️ 重新设置", callback_data="conv_edit")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    
    async def _confirm_preferences(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """确认偏好设置"""
        user_id = update.effective_user.id
        
        # 获取收集的数据
        data = self._conversations[user_id]["data"]
        
        # 整理成结构化数据
        profile_data = {
            "interests": data.get("interests", []),
            "preferences": {
                **data.get("preferences", {}),
                **data.get("volume_preferences", {})
            }
        }
        
        # 保存画像
        await self.profile_manager.create_profile(user_id, profile_data)
        
        # 清除对话状态
        del self._conversations[user_id]
        
        # 发送确认消息
        await update.callback_query.edit_message_text(
            "✅ 偏好设置成功！\n\n"
            "我将根据您的偏好为您筛选每日 Web3 信息。\n"
            "使用 /profile 可以随时查看和修改偏好。\n\n"
            "期待为您提供有价值的信息！",
            parse_mode="Markdown"
        )
        
        logger.info(f"用户 {user_id} 完成偏好设置")
    
    async def _edit_preferences(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """重新设置偏好"""
        user_id = update.effective_user.id
        
        # 清除当前对话
        del self._conversations[user_id]
        
        # 重新开始
        await self.start_preference_conversation(update, context)
    
    # LLM 辅助方法
    async def _extract_interests(self, text: str) -> list:
        """使用 LLM 提取关注领域"""
        prompt = f"""
从以下文本中提取用户关注的 Web3 领域，返回列表格式：

文本：{text}

请提取以下类型的关键词：
- 技术领域：DeFi, Layer2, NFT, GameFi, AI+Crypto, Meme币等
- 公链：以太坊, Solana, BSC, Arbitrum, Optimism等
- 方向：技术进展, 市场分析, 融资动态, 链上数据等

只返回关键词列表，如：["DeFi", "Layer2", "以太坊"]
"""
        
        try:
            response = await self.llm_client.complete(prompt)
            # 解析响应
            import ast
            return ast.literal_eval(response.strip())
        except:
            # 失败时返回空列表
            return []
    
    async def _extract_preferences(self, text: str) -> dict:
        """使用 LLM 提取内容偏好"""
        prompt = f"""
从以下文本中提取用户的内容偏好，返回JSON格式：

文本：{text}

提取以下信息：
- content_types: 内容类型列表
- sources: 关注的信息源（去掉@符号）
- likes: 喜欢的内容
- dislikes: 不喜欢的内容

返回格式：
{{
    "content_types": ["技术进展", "链上数据"],
    "sources": ["VitalikButerin", "lookonchain"],
    "likes": ["大户动向", "空投信息"],
    "dislikes": ["价格预测"]
}}
"""
        
        try:
            response = await self.llm_client.complete(prompt)
            import json
            return json.loads(response.strip())
        except:
            return {}
    
    async def _extract_volume_preferences(self, text: str) -> dict:
        """提取信息量偏好"""
        prompt = f"""
从以下文本中提取用户的信息量偏好：

文本：{text}

返回JSON格式：
{{
    "info_volume": "精简版(5-10条)" 或 "标准版(10-20条)" 或 "丰富版(20-30条)",
    "additional_notes": ["不喜欢价格预测", "主要关注中文内容"]
}}
"""
        
        try:
            response = await self.llm_client.complete(prompt)
            import json
            return json.loads(response.strip())
        except:
            return {"info_volume": "标准版(10-20条)", "additional_notes": []}
    
    async def _generate_preference_summary(self, data: dict) -> str:
        """生成偏好总结"""
        interests = data.get("interests", [])
        prefs = data.get("preferences", {})
        volume = data.get("volume_preferences", {})
        
        summary = f"**关注领域**：{', '.join(interests) if interests else '未设置'}\n\n"
        
        if prefs.get("content_types"):
            summary += f"**内容类型**：{', '.join(prefs['content_types'])}\n\n"
        
        if prefs.get("sources"):
            sources = [f"@{s}" for s in prefs["sources"]]
            summary += f"**关注信息源**：{', '.join(sources)}\n\n"
        
        if volume.get("info_volume"):
            summary += f"**信息量**：{volume['info_volume']}\n\n"
        
        if volume.get("additional_notes"):
            summary += f"**其他要求**：{', '.join(volume['additional_notes'])}\n\n"
        
        return summary
