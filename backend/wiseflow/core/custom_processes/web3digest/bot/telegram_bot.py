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
        self.user_manager = UserManager()
        self.profile_manager = ProfileManager()
        self.conversation_manager = ConversationManager()
        from core.custom_processes.web3digest.core.feedback_manager import FeedbackManager
        self.feedback_manager = FeedbackManager()
        from core.custom_processes.web3digest.core.source_manager import SourceManager
        self.source_manager = SourceManager()
        from core.custom_processes.web3digest.core.auth_manager import AuthManager
        self.auth_manager = AuthManager()
        self._adding_source_state = {}  # user_id -> {"type": "twitter"/"website", "step": "waiting"}
        
    async def start(self):
        """启动 Bot"""
        # 创建 Application
        self.application = Application.builder().token(self.token).build()
        
        # 注册命令处理器
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("profile", self.cmd_profile))
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
        
        logger.info("✅ Telegram Bot 已启动")
        
        # 保持运行
        await self.application.updater.running
    
    async def stop(self):
        """停止 Bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
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
        
        # 获取用户画像
        profile = await self.profile_manager.get_profile(user_id)
        
        if profile:
            # 显示当前画像
            await update.message.reply_text(
                f"📝 **您的当前偏好画像：**\n\n{profile}",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # 询问是否要修改
            keyboard = [
                [InlineKeyboardButton("✏️ 修改偏好", callback_data="profile_edit")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("请选择操作：", reply_markup=reply_markup)
        else:
            # 没有画像，开始收集
            await self.conversation_manager.start_preference_conversation(update, context)
    
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
    
    async def handle_feedback_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理反馈回调"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        if data.startswith("feedback_positive"):
            # 正面反馈
            await self.feedback_manager.save_feedback(user_id, "positive")
            await query.edit_message_text("✅ 感谢您的反馈！我们会继续努力为您提供更好的服务。")
            
        elif data.startswith("feedback_negative"):
            # 负面反馈，显示原因选择
            await self._show_feedback_reasons(query)
    
    async def _show_feedback_reasons(self, query):
        """显示反馈原因选择"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [InlineKeyboardButton("内容不感兴趣", callback_data="feedback_reason_内容不感兴趣")],
            [InlineKeyboardButton("漏掉重要信息", callback_data="feedback_reason_漏掉重要信息")],
            [InlineKeyboardButton("信息太多/太杂", callback_data="feedback_reason_信息太多/太杂")],
            [InlineKeyboardButton("信息太少", callback_data="feedback_reason_信息太少")],
            [InlineKeyboardButton("跳过", callback_data="feedback_reason_skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👎 请告诉我们哪里需要改进：",
            reply_markup=reply_markup
        )
    
    async def handle_feedback_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理反馈原因选择"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        if data == "feedback_reason_skip":
            # 跳过，只保存负面反馈
            await self.feedback_manager.save_feedback(user_id, "negative")
            await query.edit_message_text("✅ 感谢您的反馈！我们会持续改进。")
        else:
            # 提取原因
            reason = data.replace("feedback_reason_", "")
            
            # 保存反馈
            await self.feedback_manager.save_feedback(
                user_id, 
                "negative",
                reason_selected=[reason]
            )
            
            # 询问是否要补充说明
            await query.edit_message_text(
                f"✅ 已记录：{reason}\n\n"
                "💬 如需补充说明，请直接发送文字消息。或回复 /start 返回主菜单。"
            )
    
    async def handle_item_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理单条信息反馈"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        # 解析：item_feedback_{rating}_{item_id}_{source}
        parts = data.split("_", 3)
        if len(parts) >= 4:
            rating = parts[2]  # like 或 dislike
            item_id = parts[3] if len(parts) > 3 else ""
            source = parts[4] if len(parts) > 4 else ""
            
            # 保存反馈
            await self.feedback_manager.add_item_feedback(user_id, item_id, source, rating)
            
            if rating == "like":
                await query.answer("⭐ 已标记为有用", show_alert=False)
            else:
                await query.answer("👎 已标记为不感兴趣", show_alert=False)
    
    async def cmd_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /test 命令 - 完整流程测试"""
        user_id = update.effective_user.id
        
        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            await update.message.reply_text("❌ 您没有访问权限")
            return
        
        # 检查用户是否有画像
        profile = await self.profile_manager.get_profile(user_id)
        if not profile:
            await update.message.reply_text("⚠️ 请先使用 /start 完成偏好设置")
            return
        
        # 发送初始提示
        status_msg = await update.message.reply_text("🚀 开始完整流程测试...\n\n步骤 1/4: 正在抓取信息...")
        
        try:
            from core.custom_processes.web3digest.core.scheduler import DigestScheduler
            scheduler = DigestScheduler(self)
            
            # 执行完整流程并更新状态
            result = await scheduler.trigger_manual_digest_with_status(user_id, status_msg)
            
            if result["success"]:
                await status_msg.edit_text("✅ 完整流程测试成功！\n\n简报已发送，请查看。")
            else:
                await status_msg.edit_text(f"❌ 流程测试失败：\n{result['error']}")
                
        except Exception as e:
            logger.error(f"测试流程失败: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ 发生错误：{str(e)}")
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示主菜单"""
        keyboard = [
            [InlineKeyboardButton("📝 查看我的偏好", callback_data="profile_view")],
            [InlineKeyboardButton("📡 管理信息源", callback_data="sources_manage")],
            [InlineKeyboardButton("💬 意见反馈", callback_data="feedback")],
            [InlineKeyboardButton("🧪 测试简报", callback_data="test_digest")]
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
        else:
            # 不在对话中，提示使用命令
            await update.message.reply_text("请使用 /start 开始，或使用 /help 查看帮助")
    
    # 回调处理器
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮点击"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "main_menu":
            await self.show_main_menu(update, context)
        elif data == "profile_edit":
            await self.conversation_manager.start_preference_conversation(update, context)
        elif data == "profile_view":
            await self.cmd_profile(update, context)
        elif data.startswith("conv_"):
            # 对话相关回调
            await self.conversation_manager.handle_callback(update, context)
        elif data == "test_digest":
            # 测试简报回调
            await self.cmd_test(update, context)
        elif data.startswith("feedback_"):
            # 反馈相关回调
            await self.handle_feedback_callback(update, context)
        elif data.startswith("feedback_reason_"):
            # 反馈原因选择
            await self.handle_feedback_reason(update, context)
        elif data.startswith("item_feedback_"):
            # 单条信息反馈
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