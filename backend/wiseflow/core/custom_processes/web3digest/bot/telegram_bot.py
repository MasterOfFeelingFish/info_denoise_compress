"""
Telegram Bot 主模块
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

from core.custom_processes.web3digest.core.user_manager import UserManager
from core.custom_processes.web3digest.core.profile_manager import ProfileManager
from core.custom_processes.web3digest.core.conversation_manager import ConversationManager
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)


class Web3DigestBot:
    """Web3 Daily Digest Telegram Bot"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = None
        self._stop_event: Optional[asyncio.Event] = None
        self.user_manager = UserManager()
        self.profile_manager = ProfileManager()
        self.conversation_manager = ConversationManager(bot=self)
        from core.custom_processes.web3digest.core.feedback_manager import FeedbackManager
        self.feedback_manager = FeedbackManager()
        from core.custom_processes.web3digest.core.source_manager import SourceManager
        self.source_manager = SourceManager()
        from core.custom_processes.web3digest.core.auth_manager import AuthManager
        self.auth_manager = AuthManager()
        self._adding_source_state = {}  # user_id -> {"type": "twitter"/"website", "step": "waiting"}
        self._custom_push_time_state = {}  # user_id -> True (正在输入自定义推送时间)
        self._pending_item_feedback = {}  # user_id -> {"item_id": "...", "source": "...", "message_id": ...}
        self._active_feedback_reasons = {}  # user_id -> message_id (当前显示的反馈原因选择消息ID)
        
    async def start(self):
        """启动 Bot"""
        # 创建 Application
        self.application = Application.builder().token(self.token).build()
        
        # 注册命令处理器
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("profile", self.cmd_profile))
        self.application.add_handler(CommandHandler("settings", self.cmd_settings))  # 设置/修改偏好
        self.application.add_handler(CommandHandler("sources", self.cmd_sources))
        self.application.add_handler(CommandHandler("feedback", self.cmd_feedback))
        self.application.add_handler(CommandHandler("test", self.cmd_test))  # 测试命令
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))  # 管理员命令
        
        # 注册消息处理器（用于对话式偏好收集）
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # 注册回调处理器（用于按钮点击）
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # 启动轮询
        logger.info("Telegram Bot 启动中...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        
        logger.info("Telegram Bot 已启动，等待消息...")
        
        # 保持运行直到收到停止信号
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()
    
    async def stop(self):
        """停止 Bot"""
        # 设置停止事件
        if hasattr(self, '_stop_event'):
            self._stop_event.set()
        
        if self.application:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                logger.warning(f"停止 Bot 时发生错误: {e}")
            logger.info("Telegram Bot 已停止")
    
    # 命令处理器
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name
        
        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            await update.message.reply_text(
                "❌ 抱歉，您没有访问权限。\n\n"
                "如有疑问，请联系管理员。"
            )
            logger.warning(f"用户 {user_id} 访问被拒绝")
            return
        
        logger.info(f"用户 {user_name} ({user_id}) 开始使用 Bot")
        
        # 检查是否是新用户
        is_new_user = await self.user_manager.register_user(user_id, user_name)
        
        if is_new_user:
            # 新用户，开始偏好收集对话
            await self.conversation_manager.start_preference_conversation(update, context)
        else:
            # 老用户，显示主菜单
            await self.show_main_menu(update, context)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        help_text = """
🤖 **Web3 Daily Digest 使用指南**

**主要命令：**
/start - 开始使用或重新设置偏好
/profile - 查看和更新我的偏好
/sources - 管理信息源
/feedback - 主动反馈
/test - 手动触发一次简报（测试用）

**功能特点：**
• 🎯 AI 个性化筛选 - 基于您的偏好精准筛选
• 💬 对话式设置 - 3 轮对话完成偏好收集
• 📊 价值可感知 - 展示为您节省了多少时间
• 🔄 持续学习 - 根据反馈不断优化

**反馈方式：**
• 在简报底部点击 👍/👎
• 对单条信息标记"不感兴趣"或"很有用"
• 使用 /feedback 命令主动反馈

如有问题，请联系管理员。
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /profile 命令"""
        user_id = update.effective_user.id
        
        # 判断是命令还是回调
        is_callback = update.callback_query is not None
        query = update.callback_query if is_callback else None
        
        # 发送"正在加载"提示
        if is_callback:
            await query.answer()  # 响应回调，避免超时
            # 先编辑消息显示加载状态
            try:
                await query.edit_message_text("⏳ 正在加载您的偏好...")
            except Exception as e:
                logger.warning(f"编辑消息失败，尝试发送新消息: {e}")
                # 如果编辑失败，发送新消息
                try:
                    loading_msg = await query.message.reply_text("⏳ 正在加载您的偏好...")
                except:
                    loading_msg = None
            else:
                loading_msg = None
        else:
            loading_msg = await update.message.reply_text("⏳ 正在加载您的偏好...")
        
        try:
            # 获取用户画像
            profile = await self.profile_manager.get_profile(user_id)
            
            if profile:
                # 获取结构化数据，补充显示
                structured_data = await self.profile_manager.get_structured_profile(user_id)
                if structured_data:
                    # 添加结构化数据摘要
                    stats = structured_data.get("stats", {})
                    feedback_count = stats.get("total_feedbacks", 0)
                    if feedback_count > 0:
                        profile += f"\n\n📊 **反馈统计**\n"
                        profile += f"• 总反馈次数: {feedback_count}\n"
                        profile += f"• 正面反馈: {stats.get('positive_count', 0)}次\n"
                        profile += f"• 负面反馈: {stats.get('negative_count', 0)}次\n"
                        if stats.get("last_feedback_time"):
                            from datetime import datetime
                            last_time = datetime.fromisoformat(stats["last_feedback_time"]).strftime("%Y-%m-%d %H:%M")
                            profile += f"• 最后反馈: {last_time}"
                
                # 准备键盘
                keyboard = [
                    [InlineKeyboardButton("✏️ 修改偏好", callback_data="profile_edit")],
                    [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # 合并消息，一次性发送（更快）
                full_text = f"📝 **您的当前偏好画像：**\n\n{profile}\n\n请选择操作："
                
                if is_callback:
                    # 回调：编辑消息
                    try:
                        await query.edit_message_text(
                            full_text,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        logger.warning(f"编辑消息失败，发送新消息: {e}")
                        # 如果编辑失败（比如内容相同），发送新消息
                        await query.message.reply_text(
                            full_text,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup
                        )
                else:
                    # 命令：删除加载提示并发送新消息
                    if loading_msg:
                        try:
                            await loading_msg.delete()
                        except:
                            pass
                    await update.message.reply_text(
                        full_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )
            else:
                # 没有画像，开始收集
                if is_callback:
                    try:
                        await query.edit_message_text("⚠️ 您还没有设置偏好，正在开始设置...")
                    except:
                        await query.message.reply_text("⚠️ 您还没有设置偏好，正在开始设置...")
                await self.conversation_manager.start_preference_conversation(update, context)
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}", exc_info=True)
            error_text = "❌ 加载失败，请稍后重试"
            if is_callback:
                try:
                    await query.edit_message_text(error_text)
                except:
                    try:
                        await query.message.reply_text(error_text)
                    except:
                        pass
            else:
                if loading_msg:
                    try:
                        await loading_msg.edit_text(error_text)
                    except:
                        await update.message.reply_text(error_text)
    
    async def _show_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示设置菜单（供命令和回调使用）"""
        user_id = update.effective_user.id
        
        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            if update.message:
                await update.message.reply_text("❌ 您没有访问权限，请联系管理员")
            elif update.callback_query:
                await update.callback_query.answer("❌ 您没有访问权限", show_alert=True)
            return
        
        # 显示设置菜单
        keyboard = [
            [InlineKeyboardButton("📝 修改偏好画像", callback_data="settings_profile")],
            [InlineKeyboardButton("📰 管理信息源", callback_data="settings_sources")],
            [InlineKeyboardButton("⏰ 推送时间设置", callback_data="settings_push_time")],
            [InlineKeyboardButton("📊 查看使用统计", callback_data="settings_stats")],
            [InlineKeyboardButton("🔙 返回", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        menu_text = "⚙️ **设置中心**\n\n请选择要修改的设置项："
        
        if update.message:
            await update.message.reply_text(
                menu_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                menu_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /settings 命令 - 设置/修改偏好（TC-2.4）"""
        await self._show_settings_menu(update, context)
    
    async def cmd_sources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /sources 命令 - 信息源管理"""
        user_id = update.effective_user.id
        
        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            await update.message.reply_text("❌ 您没有访问权限")
            return
        
        await self._show_sources_menu(update, context, user_id)
    
    async def _show_sources_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
        """显示信息源管理菜单"""
        if user_id is None:
            user_id = update.effective_user.id
        
        sources_config = await self.source_manager.get_user_sources(user_id)
        
        # 统计
        preset_count = len(sources_config["preset_sources"])
        preset_enabled = sum(1 for s in sources_config["preset_sources"] if s.get("enabled", True))
        custom_count = len(sources_config["custom_sources"])
        custom_enabled = sum(1 for s in sources_config["custom_sources"] if s.get("enabled", True))
        
        menu_text = f"""📡 **信息源管理**

**预设信息源**: {preset_enabled}/{preset_count} 已启用
**自定义信息源**: {custom_enabled}/{custom_count} 已启用

请选择操作："""
        
        keyboard = [
            [InlineKeyboardButton("📋 查看预设信息源", callback_data="sources_view_preset")],
            [InlineKeyboardButton("➕ 添加 Twitter 账号", callback_data="sources_add_twitter")],
            [InlineKeyboardButton("➕ 添加网站 RSS", callback_data="sources_add_website")],
            [InlineKeyboardButton("📝 我的自定义源", callback_data="sources_view_custom")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def _show_push_time_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """显示推送时间设置界面"""
        # 获取当前推送时间
        current_time = await self.profile_manager.get_push_time(user_id)
        
        # 预设时间选项
        preset_times = [
            ["07:00", "08:00", "09:00"],
            ["10:00", "12:00", "14:00"],
            ["16:00", "18:00", "20:00"],
            ["22:00", "自定义时间"]
        ]
        
        keyboard = []
        for row in preset_times:
            button_row = []
            for time_str in row:
                if time_str == "自定义时间":
                    button_row.append(InlineKeyboardButton("✏️ 自定义", callback_data="push_time_custom"))
                else:
                    # 标记当前选择的时间
                    prefix = "✅ " if time_str == current_time else ""
                    button_row.append(InlineKeyboardButton(f"{prefix}{time_str}", callback_data=f"push_time_{time_str}"))
            keyboard.append(button_row)
        
        keyboard.append([InlineKeyboardButton("🔙 返回设置", callback_data="settings_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        menu_text = f"""⏰ **推送时间设置**

当前推送时间：**{current_time}**

请选择您希望的每日推送时间：

💡 提示：
• 选择预设时间，或点击"自定义"输入特定时间
• 使用 24 小时制，格式：HH:MM
• 例如：09:00、14:30、20:00
"""
        
        if update.message:
            await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def _show_user_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """显示用户使用统计（实时计算）"""
        import json
        from pathlib import Path
        from datetime import date
        from core.custom_processes.web3digest.core.config import settings
        
        # 显示加载提示
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text("⏳ 正在计算统计数据...")
            except:
                pass
        
        # 统计数据（实时计算）
        total_digests = 0
        total_feedbacks = 0
        total_time_saved = 0.0
        
        try:
            # 1. 实时计算简报数量（包括今日）
            stats_dir = Path(settings.DATA_DIR) / "daily_stats"
            if stats_dir.exists():
                for stats_file in stats_dir.glob("*.json"):
                    try:
                        # 使用异步文件读取，避免阻塞事件循环
                        def _read_stats_file():
                            with open(stats_file, 'r', encoding='utf-8') as f:
                                return json.load(f)

                        loop = asyncio.get_event_loop()
                        daily_stats = await loop.run_in_executor(None, _read_stats_file)
                        user_stats = daily_stats.get("users", {}).get(str(user_id), {})
                        if user_stats:
                            total_digests += 1
                    except Exception:
                        continue
            
            # 2. 实时获取反馈数量（从反馈管理器）
            total_feedbacks = await self.feedback_manager.get_feedback_count(user_id)
            
            # 3. 实时计算累计节省时间（使用 DigestGenerator 的方法，包括今日）
            from core.custom_processes.web3digest.core.digest_generator import DigestGenerator
            digest_generator = DigestGenerator()
            total_time_saved = await digest_generator._get_total_time_saved(user_id, exclude_today=False)
            
        except Exception as e:
            logger.warning(f"读取用户统计失败: {e}", exc_info=True)
        
        # 4. 获取信息源数量（实时）
        sources_config = await self.source_manager.get_user_sources(user_id)
        total_sources = len(sources_config["preset_sources"]) + len(sources_config["custom_sources"])
        enabled_sources = sum(1 for s in sources_config["preset_sources"] if s.get("enabled", True))
        enabled_sources += sum(1 for s in sources_config["custom_sources"] if s.get("enabled", True))
        
        stats_text = f"""📊 **您的使用统计**

📰 已接收简报: {total_digests} 份
💬 反馈次数: {total_feedbacks} 次
⏱️ 累计节省时间: {round(total_time_saved, 1)} 小时
📡 信息源: {enabled_sources}/{total_sources} 已启用

💡 持续使用和反馈，AI 将越来越了解您的偏好！
"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 返回设置", callback_data="settings_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def cmd_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /feedback 命令 - 主动反馈"""
        user_id = update.effective_user.id
        
        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            await update.message.reply_text("❌ 您没有访问权限")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("👍 整体满意", callback_data="feedback_positive_manual"),
                InlineKeyboardButton("👎 需要改进", callback_data="feedback_negative_manual")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💬 请选择您的整体评价：",
            reply_markup=reply_markup
        )
    
    async def _generate_personalized_feedback_message(self, user_id: int, feedback_type: str) -> str:
        """
        生成个性化的反馈确认消息（Phase 2优化）

        Args:
            user_id: 用户ID
            feedback_type: "positive" 或 "negative"

        Returns:
            个性化的确认消息
        """
        try:
            # 获取用户画像
            profile = await self.profile_manager.get_structured_profile(user_id)
            if not profile:
                # 如果没有画像，返回通用消息
                if feedback_type == "positive":
                    return "✅ 感谢反馈！我们会继续为您提供优质内容"
                else:
                    return "📝 已记录，我们将改进内容推荐"

            # 提取用户兴趣
            interests = profile.get("interests", [])
            preferences = profile.get("preferences", {})
            content_types = preferences.get("content_types", [])

            # 构建兴趣描述
            interest_desc = ""
            if interests:
                interest_desc = "、".join(interests[:2])  # 最多显示2个
            elif content_types:
                interest_desc = "、".join(content_types[:2])

            # 生成个性化消息
            if feedback_type == "positive":
                if interest_desc:
                    return f"✅ 感谢反馈！我们会继续为您推荐 {interest_desc} 等相关内容"
                else:
                    return "✅ 感谢反馈！我们会继续为您提供优质内容"
            else:  # negative
                if interest_desc:
                    return f"📝 已记录！我们将优化 {interest_desc} 相关内容的推荐"
                else:
                    return "📝 已记录！我们将改进内容推荐"

        except Exception as e:
            logger.error(f"生成个性化反馈消息失败: {e}")
            # 失败时返回通用消息
            if feedback_type == "positive":
                return "✅ 感谢反馈！"
            else:
                return "📝 已记录！"

    async def handle_feedback_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理反馈回调（Phase 2优化：添加个性化确认消息）"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data

        if data.startswith("feedback_positive"):
            # 正面反馈
            await self.feedback_manager.save_feedback(user_id, "positive")

            # 生成个性化确认消息
            message = await self._generate_personalized_feedback_message(user_id, "positive")
            await query.answer(message, show_alert=False)

            # 发送一条新消息，让用户看到AI在学习
            try:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=f"{message}\n\n💡 AI正在学习您的偏好，未来的推荐会更加精准！"
                )
            except:
                pass

            # 移除反馈按钮，保留简报内容
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except:
                pass

        elif data.startswith("feedback_negative"):
            # 负面反馈：先不保存，等用户选择原因或跳过后再保存
            # 立即响应，避免用户重复点击
            try:
                message = await self._generate_personalized_feedback_message(user_id, "negative")
                await query.answer(message, show_alert=False)
            except:
                pass

            # 立即移除反馈按钮，提升响应速度
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except:
                pass

            # 如果已有反馈原因选择界面，先删除旧的
            if user_id in self._active_feedback_reasons:
                try:
                    old_msg_id = self._active_feedback_reasons[user_id]
                    await self.application.bot.delete_message(chat_id=user_id, message_id=old_msg_id)
                except:
                    pass

            # 发送可选的原因选择（不强制）
            reason_msg = await self._show_feedback_reasons_optional(query, user_id)
            if reason_msg:
                self._active_feedback_reasons[user_id] = reason_msg.message_id
    
    async def _show_feedback_reasons(self, query):
        """显示反馈原因选择（旧方法，保留兼容）"""
        await self._show_feedback_reasons_new(query, query.from_user.id)
    
    async def _show_feedback_reasons_new(self, query, user_id: int):
        """显示反馈原因选择（发送新消息）- 已废弃，保留兼容"""
        await self._show_feedback_reasons_optional(query, user_id)
    
    async def _show_feedback_reasons_optional(self, query, user_id: int):
        """显示可选的反馈原因选择（不强制）"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [InlineKeyboardButton("内容不感兴趣", callback_data="feedback_reason_内容不感兴趣")],
            [InlineKeyboardButton("漏掉重要信息", callback_data="feedback_reason_漏掉重要信息")],
            [InlineKeyboardButton("信息太多/太杂", callback_data="feedback_reason_信息太多/太杂")],
            [InlineKeyboardButton("信息太少", callback_data="feedback_reason_信息太少")],
            [InlineKeyboardButton("💡 跳过，直接保存", callback_data="feedback_reason_skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 发送新消息（可选，用户可以选择跳过）
        msg = await self.application.bot.send_message(
            chat_id=user_id,
            text="💬 可选：告诉我们具体哪里需要改进？\n（可选择跳过直接保存反馈）",
            reply_markup=reply_markup
        )
        return msg
    
    async def _show_item_feedback_reasons(self, user_id: int, item_id: str, source: str):
        """显示单条信息的反馈原因选择"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        # 如果已有反馈原因选择界面，先删除旧的
        if user_id in self._active_feedback_reasons:
            try:
                old_msg_id = self._active_feedback_reasons[user_id]
                await self.application.bot.delete_message(chat_id=user_id, message_id=old_msg_id)
            except:
                pass
        
        # 清理 item_id 和 source 中的特殊字符，避免 callback_data 格式问题
        safe_item_id = item_id.replace("_", "-")[:20]
        safe_source = source.replace("_", "-")[:10]
        
        keyboard = [
            [InlineKeyboardButton("内容不感兴趣", callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_内容不感兴趣")],
            [InlineKeyboardButton("漏掉重要信息", callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_漏掉重要信息")],
            [InlineKeyboardButton("信息太多/太杂", callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_信息太多/太杂")],
            [InlineKeyboardButton("信息太少", callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_信息太少")],
            [InlineKeyboardButton("💡 跳过，直接保存", callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 发送新消息（可选，用户可以选择跳过）
        msg = await self.application.bot.send_message(
            chat_id=user_id,
            text="💬 可选：告诉我们具体哪里需要改进？\n（可选择跳过直接保存反馈）",
            reply_markup=reply_markup
        )
        self._active_feedback_reasons[user_id] = msg.message_id
        return msg
    
    async def handle_feedback_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理反馈原因选择"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        # 立即响应，避免用户重复点击
        try:
            await query.answer()  # 立即响应
        except:
            pass
        
        # 立即更新界面，提升响应速度
        try:
            await query.edit_message_text("⏳ 正在保存反馈...")
        except:
            pass
        
        # 清除活跃的反馈原因选择界面记录
        if user_id in self._active_feedback_reasons:
            del self._active_feedback_reasons[user_id]
        
        if data == "feedback_reason_skip":
            # 跳过，保存基本负面反馈（不带原因）
            await self.feedback_manager.save_feedback(user_id, "negative")
            # 编辑消息显示确认
            try:
                await query.edit_message_text(
                    "✅ 反馈已记录，感谢！\n\n"
                    "💬 如需补充说明，请直接发送文字消息。或回复 /start 返回主菜单。"
                )
            except:
                # 如果编辑失败，删除消息
                try:
                    await query.message.delete()
                except:
                    pass
        else:
            # 提取原因
            reason = data.replace("feedback_reason_", "")
            
            # 保存反馈（带原因）
            await self.feedback_manager.save_feedback(
                user_id, 
                "negative",
                reason_selected=[reason]
            )
            
            # 编辑消息显示确认
            try:
                await query.edit_message_text(
                    f"✅ 已记录：{reason}\n\n"
                    "💬 如需补充说明，请直接发送文字消息。或回复 /start 返回主菜单。"
                )
            except Exception as e:
                logger.warning(f"编辑反馈消息失败: {e}")
                # 如果编辑失败，删除消息
                try:
                    await query.message.delete()
                except:
                    pass
    
    async def handle_item_feedback_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理单条信息反馈原因选择"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        # 立即响应，避免用户重复点击
        try:
            await query.answer()  # 立即响应
        except:
            pass
        
        # 立即更新界面，提升响应速度
        try:
            await query.edit_message_text("⏳ 正在保存反馈...")
        except:
            pass
        
        # 清除活跃的反馈原因选择界面记录
        if user_id in self._active_feedback_reasons:
            del self._active_feedback_reasons[user_id]
        
        # 解析 callback_data: item_feedback_reason_{item_id}_{source}_{reason}
        parts = data.replace("item_feedback_reason_", "").split("_", 2)
        if len(parts) < 3:
            # 格式错误，尝试跳过处理
            try:
                await query.message.delete()
            except:
                pass
            return
        
        # 恢复原始 item_id 和 source（将 - 替换回 _）
        item_id = parts[0].replace("-", "_")
        source = parts[1].replace("-", "_")
        reason = parts[2]
        
        if reason == "skip":
            # 跳过，直接保存反馈（不带原因）
            await self.feedback_manager.add_item_feedback(user_id, item_id, source, "dislike")
            # 编辑消息显示确认
            try:
                await query.edit_message_text(
                    "✅ 反馈已记录，感谢！\n\n"
                    "💬 如需补充说明，请直接发送文字消息。或回复 /start 返回主菜单。"
                )
            except:
                # 如果编辑失败，删除消息
                try:
                    await query.message.delete()
                except:
                    pass
        else:
            # 保存反馈（带原因）
            await self.feedback_manager.add_item_feedback(user_id, item_id, source, "dislike")
            
            # 同时保存整体反馈（带原因），用于画像更新
            await self.feedback_manager.save_feedback(
                user_id,
                "negative",
                reason_selected=[reason]
            )
            
            # 编辑消息显示确认
            try:
                await query.edit_message_text(
                    f"✅ 已记录：{reason}\n\n"
                    "💬 如需补充说明，请直接发送文字消息。或回复 /start 返回主菜单。"
                )
            except Exception as e:
                logger.warning(f"编辑反馈消息失败: {e}")
                # 如果编辑失败，删除消息
                try:
                    await query.message.delete()
                except:
                    pass
    
    async def handle_item_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理单条信息反馈"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        # 先立即响应，避免用户重复点击
        try:
            await query.answer()  # 立即响应，避免超时
        except:
            pass
        
        # 立即移除按钮，提升响应速度
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        
        # 解析多种格式：
        # - item_like_{item_id}_{source}
        # - item_dislike_{item_id}_{source}
        # - item_feedback_{rating}_{item_id}_{source}（旧格式）
        
        if data.startswith("item_like_"):
            rating = "like"
            rest = data.replace("item_like_", "")
            parts = rest.split("_", 1)
            item_id = parts[0] if parts else ""
            source = parts[1] if len(parts) > 1 else ""
        elif data.startswith("item_dislike_"):
            rating = "dislike"
            rest = data.replace("item_dislike_", "")
            parts = rest.split("_", 1)
            item_id = parts[0] if parts else ""
            source = parts[1] if len(parts) > 1 else ""
        else:
            # 旧格式：item_feedback_{rating}_{item_id}_{source}
            parts = data.split("_")
            rating = parts[2] if len(parts) > 2 else ""
            item_id = parts[3] if len(parts) > 3 else ""
            source = parts[4] if len(parts) > 4 else ""
        
        if rating == "like":
            # 正面反馈：直接保存并显示确认
            await self.feedback_manager.add_item_feedback(user_id, item_id, source, rating)
            await query.answer("⭐ 已标记为有用！感谢反馈", show_alert=False)
        else:
            # 负面反馈：先显示原因选择界面，等用户选择后再保存
            # 保存 item_id 和 source，用于后续保存反馈
            if not hasattr(self, '_pending_item_feedback'):
                self._pending_item_feedback = {}
            self._pending_item_feedback[user_id] = {
                "item_id": item_id,
                "source": source,
                "message_id": query.message.message_id
            }
            
            # 显示反馈原因选择界面
            await self._show_item_feedback_reasons(user_id, item_id, source)
    
    async def cmd_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /test 命令 - 完整流程测试（支持命令和按钮点击）"""
        user_id = update.effective_user.id
        
        # 判断是命令还是回调按钮
        is_callback = update.callback_query is not None
        
        # 获取用于回复的消息对象
        if is_callback:
            query = update.callback_query
            await query.answer()  # 响应回调
            chat = query.message.chat
        else:
            chat = update.message.chat
        
        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            if is_callback:
                await context.bot.send_message(chat.id, "❌ 您没有访问权限")
            else:
                await update.message.reply_text("❌ 您没有访问权限")
            return
        
        # 检查用户是否有画像
        profile = await self.profile_manager.get_profile(user_id)
        if not profile:
            if is_callback:
                await context.bot.send_message(chat.id, "⚠️ 请先使用 /start 完成偏好设置")
            else:
                await update.message.reply_text("⚠️ 请先使用 /start 完成偏好设置")
            return
        
        # 发送初始提示
        status_msg = await context.bot.send_message(
            chat.id, 
            "🚀 开始完整流程测试...\n\n📥 步骤 1/4: 正在抓取信息..."
        )
        
        try:
            from core.custom_processes.web3digest.core.scheduler import DigestScheduler
            scheduler = DigestScheduler(self)
            
            # 执行完整流程并更新状态
            result = await scheduler.trigger_manual_digest_with_status(user_id, status_msg)
            
            if not result["success"]:
                # 失败消息已在 trigger_manual_digest_with_status 中处理
                pass
                
        except Exception as e:
            logger.error(f"测试流程失败: {e}", exc_info=True)
            try:
                await status_msg.edit_text(f"❌ 发生错误：{str(e)}")
            except:
                pass
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示主菜单"""
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
        
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
    
    # 消息处理器
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息（用于对话式偏好收集和信息源添加）"""
        user_id = update.effective_user.id
        
        # 鉴权检查（除了对话中的消息，因为对话开始前已经检查过）
        if user_id not in self._adding_source_state:
            if not await self.auth_manager.check_user_access(user_id):
                await update.message.reply_text("❌ 您没有访问权限")
                return
        
        # 检查是否在对话中
        if await self.conversation_manager.is_in_conversation(user_id):
            await self.conversation_manager.handle_message(update, context)
        # 检查是否在添加信息源状态
        elif user_id in self._adding_source_state:
            from core.custom_processes.web3digest.bot.source_handlers import handle_add_source_input
            await handle_add_source_input(self, update, context)
        # 检查是否在输入自定义推送时间
        elif user_id in self._custom_push_time_state:
            time_str = update.message.text.strip()
            # 验证时间格式
            try:
                hour, minute = time_str.split(":")
                hour = int(hour)
                minute = int(minute)
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    await update.message.reply_text(
                        "❌ 时间格式错误！\n\n"
                        "请输入正确的时间格式：HH:MM\n"
                        "例如：09:00、14:30、20:00\n"
                        "时间范围：00:00 - 23:59"
                    )
                    return
                
                # 更新推送时间
                success = await self.profile_manager.update_push_time(user_id, time_str)
                if success:
                    del self._custom_push_time_state[user_id]
                    await update.message.reply_text(
                        f"✅ 推送时间已设置为 **{time_str}**\n\n"
                        "您的每日简报将在该时间推送。",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await update.message.reply_text("❌ 设置失败，请重试")
            except ValueError:
                await update.message.reply_text(
                    "❌ 时间格式错误！\n\n"
                    "请输入正确的时间格式：HH:MM\n"
                    "例如：09:00、14:30、20:00"
                )
        else:
            # 不在对话中，提示使用命令
            await update.message.reply_text("请使用 /start 开始，或使用 /help 查看帮助")
    
    # 回调处理器
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮点击"""
        query = update.callback_query
        data = query.data
        
        # 先响应回调，避免超时
        try:
            await query.answer()
        except:
            pass
        
        if data == "main_menu":
            await self.show_main_menu(update, context)
        elif data == "profile_edit":
            # 修改偏好：开始偏好收集对话
            await self.conversation_manager.start_preference_conversation(update, context)
        elif data == "profile_view":
            await self.cmd_profile(update, context)
        elif data.startswith("conv_"):
            # 对话相关回调
            await self.conversation_manager.handle_callback(update, context)
        elif data == "test_digest":
            # 测试简报回调
            await self.cmd_test(update, context)
        elif data.startswith("feedback_reason_"):
            # 反馈原因选择 (必须在 feedback_ 之前判断，因为 feedback_reason_ 也以 feedback_ 开头)
            await self.handle_feedback_reason(update, context)
        elif data.startswith("feedback_"):
            # 反馈相关回调
            await self.handle_feedback_callback(update, context)
        elif data.startswith("item_feedback_reason_"):
            # 单条信息反馈原因选择（必须在 item_feedback_ 之前判断）
            await self.handle_item_feedback_reason(update, context)
        elif data.startswith("item_like_") or data.startswith("item_dislike_"):
            # 单条信息反馈（like/dislike）
            await self.handle_item_feedback(update, context)
        elif data.startswith("item_feedback_"):
            # 单条信息反馈（旧格式兼容）
            await self.handle_item_feedback(update, context)
        elif data == "sources_manage":
            # 信息源管理菜单
            user_id = update.effective_user.id
            await self._show_sources_menu(update, context, user_id)
        elif data == "sources_view_preset":
            # 查看预设信息源
            from core.custom_processes.web3digest.bot.source_handlers import show_preset_sources
            await show_preset_sources(self, update, context)
        elif data == "sources_view_custom":
            # 查看自定义信息源
            from core.custom_processes.web3digest.bot.source_handlers import show_custom_sources
            await show_custom_sources(self, update, context)
        elif data == "sources_add_twitter":
            # 添加 Twitter 账号
            from core.custom_processes.web3digest.bot.source_handlers import start_add_twitter
            await start_add_twitter(self, update, context)
        elif data == "sources_add_website":
            # 添加网站 RSS
            from core.custom_processes.web3digest.bot.source_handlers import start_add_website
            await start_add_website(self, update, context)
        elif data.startswith("source_toggle_"):
            # 切换信息源启用/禁用
            from core.custom_processes.web3digest.bot.source_handlers import handle_toggle_source
            await handle_toggle_source(self, update, context)
        elif data.startswith("source_delete_"):
            # 删除自定义信息源
            if data.startswith("source_delete_confirm_"):
                # 确认删除
                source_id = data.replace("source_delete_confirm_", "")
                success = await self.source_manager.remove_custom_source(update.effective_user.id, source_id)
                if success:
                    await query.edit_message_text("✅ 信息源已删除")
                    from core.custom_processes.web3digest.bot.source_handlers import show_custom_sources
                    await show_custom_sources(self, update, context)
                else:
                    await query.answer("❌ 删除失败", show_alert=True)
            else:
                from core.custom_processes.web3digest.bot.source_handlers import handle_delete_source
                await handle_delete_source(self, update, context)
        elif data == "sources_back":
            # 返回信息源菜单
            await self._show_sources_menu(update, context)
        # ===== 设置相关回调 =====
        elif data == "settings_menu":
            # 返回设置菜单
            await self._show_settings_menu(update, context)
        elif data == "settings_profile":
            # 修改偏好画像
            await self.conversation_manager.start_preference_conversation(update, context)
        elif data == "settings_sources":
            # 管理信息源
            user_id = update.effective_user.id
            await self._show_sources_menu(update, context, user_id)
        elif data == "settings_push_time":
            # 推送时间设置
            user_id = update.effective_user.id
            await self._show_push_time_settings(update, context, user_id)
        elif data.startswith("push_time_"):
            # 处理推送时间选择
            user_id = update.effective_user.id
            time_str = data.replace("push_time_", "")
            if time_str == "custom":
                # 自定义时间输入
                await query.edit_message_text(
                    "⏰ **自定义推送时间**\n\n"
                    "请输入推送时间，格式：HH:MM\n"
                    "例如：09:00、14:30、20:00\n\n"
                    "💡 提示：使用 24 小时制，范围 00:00 - 23:59",
                    parse_mode=ParseMode.MARKDOWN
                )
                # 标记用户正在输入自定义时间
                self._custom_push_time_state = getattr(self, '_custom_push_time_state', {})
                self._custom_push_time_state[user_id] = True
            else:
                # 选择预设时间
                success = await self.profile_manager.update_push_time(user_id, time_str)
                if success:
                    await query.answer(f"✅ 推送时间已设置为 {time_str}", show_alert=False)
                    await self._show_push_time_settings(update, context, user_id)
                else:
                    await query.answer("❌ 设置失败，请重试", show_alert=True)
        elif data == "settings_stats":
            # 查看使用统计
            user_id = update.effective_user.id
            await self._show_user_stats(update, context, user_id)
        elif data == "admin_menu":
            # 返回管理员菜单
            user_id = update.effective_user.id
            if await self.auth_manager.is_admin(user_id):
                await self.cmd_admin(update, context)
        elif data.startswith("admin_"):
            # 管理员相关回调
            await self.handle_admin_callback(update, context)
        else:
            # 其他回调
            await query.edit_message_text("功能开发中...")
    
    # 管理员命令
    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /admin 命令 - 管理员功能"""
        user_id = update.effective_user.id
        
        # 检查管理员权限
        if not await self.auth_manager.is_admin(user_id):
            await update.message.reply_text("❌ 您没有管理员权限")
            logger.warning(f"用户 {user_id} 尝试访问管理员功能但无权限")
            return
        
        # 显示管理员菜单
        keyboard = [
            [InlineKeyboardButton("👥 用户管理", callback_data="admin_users")],
            [InlineKeyboardButton("✅ 白名单管理", callback_data="admin_whitelist")],
            [InlineKeyboardButton("🚫 黑名单管理", callback_data="admin_blacklist")],
            [InlineKeyboardButton("📊 系统统计", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        menu_text = """🔐 **管理员面板**

请选择要管理的功能："""
        
        await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理管理员回调"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        # 检查管理员权限
        if not await self.auth_manager.is_admin(user_id):
            await query.answer("❌ 您没有管理员权限", show_alert=True)
            return
        
        await query.answer()
        
        if data == "admin_users":
            await self._show_user_management(update, context)
        elif data == "admin_whitelist":
            await self._show_whitelist_management(update, context)
        elif data == "admin_blacklist":
            await self._show_blacklist_management(update, context)
        elif data == "admin_stats":
            await self._show_system_stats(update, context)
        elif data.startswith("admin_user_"):
            # 用户操作
            await self._handle_user_action(update, context)
        elif data.startswith("admin_wl_"):
            # 白名单操作
            await self._handle_whitelist_action(update, context)
        elif data.startswith("admin_bl_"):
            # 黑名单操作
            await self._handle_blacklist_action(update, context)
    
    async def _show_user_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示用户管理界面"""
        from core.custom_processes.web3digest.core.auth_manager import UserStatus
        
        users = await self.user_manager.get_all_users()
        
        text = f"👥 **用户管理**\n\n共 {len(users)} 个用户\n\n"
        
        # 显示前10个用户
        for i, user in enumerate(users[:10], 1):
            user_id = int(user.get("id", 0))
            status = await self.auth_manager.get_user_status(user_id)
            role = await self.auth_manager.get_user_role(user_id)
            
            status_icon = {
                UserStatus.ACTIVE: "✅",
                UserStatus.INACTIVE: "⚪",
                UserStatus.BANNED: "🚫",
                UserStatus.SUSPENDED: "⏸️"
            }.get(status, "❓")
            
            text += f"{i}. {user.get('name', 'Unknown')} ({user_id})\n"
            text += f"   角色: {role.value} | 状态: {status_icon} {status.value}\n\n"
        
        if len(users) > 10:
            text += f"... 还有 {len(users) - 10} 个用户"
        
        keyboard = [
            [InlineKeyboardButton("🔙 返回管理员菜单", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def _show_whitelist_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示白名单管理界面"""
        whitelist = await self.auth_manager.get_whitelist()
        
        text = f"✅ **白名单管理**\n\n当前白名单: {len(whitelist)} 个用户\n\n"
        
        if whitelist:
            for user_id in whitelist[:10]:
                user = await self.user_manager.get_user(user_id)
                name = user.get("name", "Unknown") if user else "Unknown"
                text += f"• {name} ({user_id})\n"
        else:
            text += "白名单为空（所有用户可访问）"
        
        keyboard = [
            [InlineKeyboardButton("➕ 添加用户", callback_data="admin_wl_add")],
            [InlineKeyboardButton("➖ 移除用户", callback_data="admin_wl_remove")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def _show_blacklist_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示黑名单管理界面"""
        blacklist = await self.auth_manager.get_blacklist()
        
        text = f"🚫 **黑名单管理**\n\n当前黑名单: {len(blacklist)} 个用户\n\n"
        
        if blacklist:
            for user_id in blacklist[:10]:
                user = await self.user_manager.get_user(user_id)
                name = user.get("name", "Unknown") if user else "Unknown"
                text += f"• {name} ({user_id})\n"
        else:
            text += "黑名单为空"
        
        keyboard = [
            [InlineKeyboardButton("➕ 添加用户", callback_data="admin_bl_add")],
            [InlineKeyboardButton("➖ 移除用户", callback_data="admin_bl_remove")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def _show_system_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示系统统计"""
        users = await self.user_manager.get_all_users()
        active_users = await self.user_manager.get_active_users()
        admins = await self.auth_manager.get_all_admins()
        whitelist = await self.auth_manager.get_whitelist()
        blacklist = await self.auth_manager.get_blacklist()
        
        text = f"""📊 **系统统计**

👥 **用户统计**
• 总用户数: {len(users)}
• 活跃用户: {len(active_users)}
• 管理员数: {len(admins)}

🔐 **鉴权统计**
• 白名单用户: {len(whitelist)}
• 黑名单用户: {len(blacklist)}
"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 返回管理员菜单", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def _handle_user_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理用户操作"""
        # TODO: 实现用户操作（封禁、解封、设置角色等）
        await update.callback_query.answer("功能开发中...", show_alert=True)
    
    async def _handle_whitelist_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理白名单操作"""
        # TODO: 实现白名单添加/移除
        await update.callback_query.answer("功能开发中...", show_alert=True)
    
    async def _handle_blacklist_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理黑名单操作"""
        # TODO: 实现黑名单添加/移除
        await update.callback_query.answer("功能开发中...", show_alert=True)