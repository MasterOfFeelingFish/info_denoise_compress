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
    
    def __init__(self, bot=None):
        self.profile_manager = ProfileManager()
        self.llm_client = LLMClient()
        self._conversations: Dict[int, Dict] = {}  # user_id -> conversation_state
        self.bot = bot  # 保存 bot 引用，用于显示主菜单
    
    async def start_preference_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """开始偏好收集对话"""
        user_id = update.effective_user.id
        
        # 判断是回调还是命令
        is_callback = update.callback_query is not None
        query = update.callback_query if is_callback else None
        
        # 如果是回调，先响应并编辑消息
        if is_callback:
            await query.answer("开始设置偏好...")
            try:
                await query.edit_message_text("⏳ 正在开始偏好设置...")
            except:
                pass
        
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
        
        # 判断是回调还是命令
        is_callback = update.callback_query is not None
        if is_callback:
            query = update.callback_query
            # 回调：编辑消息或发送新消息
            try:
                await query.edit_message_text(text, parse_mode="Markdown")
            except:
                # 如果编辑失败，发送新消息
                await query.message.reply_text(text, parse_mode="Markdown")
        else:
            # 命令：直接回复
            await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _handle_stage1_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """处理第一轮回复"""
        user_id = update.effective_user.id
        
        # 发送"正在处理"提示
        processing_msg = await update.message.reply_text("⏳ 正在分析您的偏好...")
        
        try:
            # 使用 LLM 提取关注领域
            interests = await self._extract_interests(response)
            
            # 保存数据
            self._conversations[user_id]["data"]["interests_response"] = response
            self._conversations[user_id]["data"]["interests"] = interests
            
            # 删除处理提示
            try:
                await processing_msg.delete()
            except:
                pass
            
            # 发送第二轮问题
            await self._send_stage2_question(update, context)
        except Exception as e:
            logger.error(f"处理第一步回复失败: {e}")
            try:
                await processing_msg.edit_text("❌ 处理失败，请重试")
            except:
                pass
    
    async def _send_stage2_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """发送第二轮问题 - 使用 AI 根据第一步回答生成问题"""
        user_id = update.effective_user.id
        
        # 获取第一步的回答和提取的兴趣
        interests_response = self._conversations[user_id]["data"].get("interests_response", "")
        interests = self._conversations[user_id]["data"].get("interests", [])
        
        # 发送"正在生成问题"提示
        generating_msg = await update.message.reply_text("⏳ 正在为您生成个性化问题...")
        
        try:
            # 使用 AI 生成第二步问题
            question_text = await self._generate_stage2_question(interests_response, interests)
            
            # 删除生成提示
            try:
                await generating_msg.delete()
            except:
                pass
            
            # 发送 AI 生成的问题（先尝试 Markdown，失败则用纯文本）
            try:
                if update.message:
                    await update.message.reply_text(question_text, parse_mode="Markdown")
                elif update.callback_query:
                    await update.callback_query.message.reply_text(question_text, parse_mode="Markdown")
            except Exception as parse_error:
                # Markdown 解析失败，使用纯文本模式
                logger.warning(f"Markdown 解析失败，使用纯文本模式: {parse_error}")
                if update.message:
                    await update.message.reply_text(question_text)
                elif update.callback_query:
                    await update.callback_query.message.reply_text(question_text)
        except Exception as e:
            logger.error(f"生成第二步问题失败: {e}")
            # 失败时使用默认问题
            try:
                await generating_msg.delete()
            except:
                pass
            
            interests_str = ', '.join(interests[:3]) if interests else 'Web3'
            default_text = f"""
📊 **第二步：您更关注哪些类型的信息？**

基于您提到的 {interests_str}，请告诉我：

1. **内容类型**：比如技术进展、市场分析、融资动态、项目公告等
2. **信息来源**：比如您常看哪些 KOL 或项目方（@VitalikButerin、@arbitrum 等）
3. **特殊偏好**：比如链上数据大户操作、空投信息、技术深度分析等

示例：
"我主要看链上数据，特别是大户动向，还关注空投信息"
            """
            
            if update.message:
                await update.message.reply_text(default_text, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.message.reply_text(default_text, parse_mode="Markdown")
    
    async def _handle_stage2_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """处理第二轮回复"""
        user_id = update.effective_user.id
        
        # 发送"正在处理"提示
        processing_msg = await update.message.reply_text("⏳ 正在分析您的偏好...")
        
        try:
            # 使用 LLM 提取偏好
            preferences = await self._extract_preferences(response)
            
            # 保存数据
            self._conversations[user_id]["data"]["preferences_response"] = response
            self._conversations[user_id]["data"]["preferences"] = preferences
            
            # 删除处理提示
            try:
                await processing_msg.delete()
            except:
                pass
            
            # 发送第三轮问题
            await self._send_stage3_question(update, context)
        except Exception as e:
            logger.error(f"处理第二步回复失败: {e}")
            try:
                await processing_msg.edit_text("❌ 处理失败，请重试")
            except:
                pass
    
    async def _send_stage3_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """发送第三轮问题 - 使用 AI 根据第二步回答生成问题"""
        user_id = update.effective_user.id
        
        # 获取前两步的回答和数据
        interests_response = self._conversations[user_id]["data"].get("interests_response", "")
        interests = self._conversations[user_id]["data"].get("interests", [])
        preferences_response = self._conversations[user_id]["data"].get("preferences_response", "")
        preferences = self._conversations[user_id]["data"].get("preferences", {})
        
        # 发送"正在生成问题"提示
        generating_msg = await update.message.reply_text("⏳ 正在为您生成个性化问题...")
        
        try:
            # 使用 AI 生成第三步问题
            question_text = await self._generate_stage3_question(
                interests_response, interests,
                preferences_response, preferences
            )
            
            # 删除生成提示
            try:
                await generating_msg.delete()
            except:
                pass
            
            # 发送 AI 生成的问题（先尝试 Markdown，失败则用纯文本）
            try:
                if update.message:
                    await update.message.reply_text(question_text, parse_mode="Markdown")
                elif update.callback_query:
                    await update.callback_query.message.reply_text(question_text, parse_mode="Markdown")
            except Exception as parse_error:
                # Markdown 解析失败，使用纯文本模式
                logger.warning(f"Markdown 解析失败，使用纯文本模式: {parse_error}")
                if update.message:
                    await update.message.reply_text(question_text)
                elif update.callback_query:
                    await update.callback_query.message.reply_text(question_text)
        except Exception as e:
            logger.error(f"生成第三步问题失败: {e}")
            # 失败时使用默认问题
            try:
                await generating_msg.delete()
            except:
                pass
            
            default_text = """
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
            
            if update.message:
                await update.message.reply_text(default_text, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.message.reply_text(default_text, parse_mode="Markdown")
    
    async def _handle_stage3_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """处理第三轮回复"""
        user_id = update.effective_user.id
        
        # 发送"正在处理"提示
        processing_msg = await update.message.reply_text("⏳ 正在生成您的偏好设置...")
        
        try:
            # 提取信息量偏好和其他要求
            volume_prefs = await self._extract_volume_preferences(response)
            
            # 保存数据
            self._conversations[user_id]["data"]["volume_response"] = response
            self._conversations[user_id]["data"]["volume_preferences"] = volume_prefs
            
            # 删除处理提示
            try:
                await processing_msg.delete()
            except:
                pass
            
            # 生成确认信息
            await self._send_confirmation(update, context)
        except Exception as e:
            logger.error(f"处理第三步回复失败: {e}")
            try:
                await processing_msg.edit_text("❌ 处理失败，请重试")
            except:
                pass
    
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
        try:
            await update.callback_query.edit_message_text(
                "✅ 偏好设置成功！\n\n"
                "我将根据您的偏好为您筛选每日 Web3 信息。\n"
                "使用 /profile 可以随时查看和修改偏好。\n\n"
                "期待为您提供有价值的信息！",
                parse_mode="Markdown"
            )
        except:
            # 如果编辑失败，发送新消息
            await update.callback_query.message.reply_text(
                "✅ 偏好设置成功！\n\n"
                "我将根据您的偏好为您筛选每日 Web3 信息。\n"
                "使用 /profile 可以随时查看和修改偏好。\n\n"
                "期待为您提供有价值的信息！",
                parse_mode="Markdown"
            )
        
        logger.info(f"用户 {user_id} 完成偏好设置")
        
        # 延迟一下，然后显示主菜单
        import asyncio
        await asyncio.sleep(1.5)
        
        # 显示主菜单
        if self.bot:
            # 使用 callback_query 的 message 来显示主菜单
            # 创建一个新的 update 对象，使用 message 而不是 callback_query
            from telegram import Message
            # 直接发送主菜单消息
            keyboard = [
                [InlineKeyboardButton("📝 修改偏好画像", callback_data="settings_profile")],
                [InlineKeyboardButton("📡 管理信息源", callback_data="settings_sources")],
                [InlineKeyboardButton("⏰ 推送时间设置", callback_data="settings_push_time")],
                [InlineKeyboardButton("📊 查看使用统计", callback_data="settings_stats")],
                [InlineKeyboardButton("🧪 测试简报", callback_data="test_digest")],
                [InlineKeyboardButton("🔙 返回", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_text = """
🎉 欢迎回来！我是您的 Web3 信息助手。

请选择您要的操作：
            """
            
            await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def _edit_preferences(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """重新设置偏好"""
        user_id = update.effective_user.id
        
        # 清除当前对话
        del self._conversations[user_id]
        
        # 重新开始
        await self.start_preference_conversation(update, context)
    
    # LLM 辅助方法
    async def _generate_stage2_question(self, interests_response: str, interests: list) -> str:
        """使用 AI 根据第一步回答生成第二步问题"""
        interests_str = ', '.join(interests) if interests else 'Web3相关领域'
        
        prompt = f"""你是 Web3 信息偏好收集助手。用户已经回答了第一步问题，现在需要生成第二步问题。

## 用户第一步回答
{interests_response}

## 提取的关注领域
{interests_str}

## 任务
请根据用户的回答，生成一个个性化、自然、友好的第二步问题。问题应该：
1. 针对用户提到的具体领域（{interests_str}）进行深入询问
2. 询问用户更关注哪些类型的信息（内容类型、信息来源、特殊偏好等）
3. 语气友好、自然，像朋友聊天一样
4. 可以给出1-2个具体的示例，帮助用户理解
5. 使用 Markdown 格式，标题用 **加粗**

## 重要提示
- 确保 Markdown 格式正确，所有 **加粗** 标签必须成对出现
- 避免使用特殊字符（如 @、#、_、*、[、]、(、)）在 Markdown 标签内部
- 如果使用 @ 符号，确保不在 **加粗** 标签内
- 示例中的特殊字符要用反斜杠转义或避免使用

## 输出格式
直接输出问题文本，不要包含其他说明。使用 Markdown 格式，例如：

📊 **第二步：您更关注哪些类型的信息？**

基于您提到的 [具体领域]，请告诉我：
...
"""
        
        try:
            response = await self.llm_client.complete(prompt, max_tokens=300, temperature=0.7)
            return response.strip()
        except Exception as e:
            logger.warning(f"生成第二步问题失败: {e}")
            # 返回默认问题
            return f"""
📊 **第二步：您更关注哪些类型的信息？**

基于您提到的 {interests_str}，请告诉我：

1. **内容类型**：比如技术进展、市场分析、融资动态、项目公告等
2. **信息来源**：比如您常看哪些 KOL 或项目方（@VitalikButerin、@arbitrum 等）
3. **特殊偏好**：比如链上数据大户操作、空投信息、技术深度分析等

示例：
"我主要看链上数据，特别是大户动向，还关注空投信息"
            """
    
    async def _generate_stage3_question(self, interests_response: str, interests: list,
                                        preferences_response: str, preferences: dict) -> str:
        """使用 AI 根据第二步回答生成第三步问题"""
        interests_str = ', '.join(interests) if interests else 'Web3相关领域'
        content_types = ', '.join(preferences.get("content_types", [])) if preferences.get("content_types") else "未明确"
        sources = ', '.join(preferences.get("sources", [])) if preferences.get("sources") else "未明确"
        
        prompt = f"""你是 Web3 信息偏好收集助手。用户已经完成了前两步，现在需要生成第三步（最后一步）问题。

## 用户第一步回答（关注领域）
{interests_response}
关注领域：{interests_str}

## 用户第二步回答（内容偏好）
{preferences_response}
内容类型偏好：{content_types}
信息来源偏好：{sources}

## 任务
请根据用户前两步的回答，生成一个个性化、自然、友好的第三步问题。问题应该：
1. 总结前两步收集的信息（简要提及）
2. 询问信息量偏好（每天希望看到多少条信息）
3. 询问补充说明（特殊需求、不感兴趣的内容等）
4. 语气友好、自然，像朋友聊天一样
5. 可以给出1-2个具体的示例
6. 使用 Markdown 格式，标题用 **加粗**

## 重要提示
- 确保 Markdown 格式正确，所有 **加粗** 标签必须成对出现
- 避免使用特殊字符（如 @、#、_、*、[、]、(、)）在 Markdown 标签内部
- 如果使用 @ 符号，确保不在 **加粗** 标签内
- 示例中的特殊字符要用反斜杠转义或避免使用

## 输出格式
直接输出问题文本，不要包含其他说明。使用 Markdown 格式，例如：

⚖️ **最后一步：信息量和补充说明**

基于您提到的 [总结]，请告诉我：
...
"""
        
        try:
            response = await self.llm_client.complete(prompt, max_tokens=300, temperature=0.7)
            return response.strip()
        except Exception as e:
            logger.warning(f"生成第三步问题失败: {e}")
            # 返回默认问题
            return """
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
            # 优化：减少 max_tokens，降低 temperature，加快响应
            response = await self.llm_client.complete(prompt, max_tokens=200, temperature=0.1)
            # 解析响应
            import ast
            return ast.literal_eval(response.strip())
        except Exception as e:
            logger.warning(f"提取关注领域失败: {e}")
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
            # 优化：减少 max_tokens，降低 temperature，加快响应
            response = await self.llm_client.complete(prompt, max_tokens=300, temperature=0.1)
            import json
            return json.loads(response.strip())
        except Exception as e:
            logger.warning(f"提取内容偏好失败: {e}")
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
            # 优化：减少 max_tokens，降低 temperature，加快响应
            response = await self.llm_client.complete(prompt, max_tokens=150, temperature=0.1)
            import json
            return json.loads(response.strip())
        except Exception as e:
            logger.warning(f"提取信息量偏好失败: {e}")
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
