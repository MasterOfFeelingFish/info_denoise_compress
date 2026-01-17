"""
Telegram Bot 主模块 - 带详细步骤日志记录
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from utils.logger import setup_logger, get_daily_logger, log_user_step, log_user_click, log_user_command, log_user_error

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import BadRequest

from core.custom_processes.web3digest.core.user_manager import UserManager
from core.custom_processes.web3digest.core.profile_manager import ProfileManager
from core.custom_processes.web3digest.core.conversation_manager import ConversationManager
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.utils.i18n import get_user_language, translate

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

        # 记录用户点击步骤 - /start命令开始
        log_user_command(user_id, "/start", [])
        log_user_step(user_id, "开始登录流程", {"user_name": user_name, "user_id": user_id})

        # 鉴权检查
        log_user_step(user_id, "开始鉴权检查", {"user_id": user_id})
        if not await self.auth_manager.check_user_access(user_id):
            log_user_step(user_id, "访问被拒绝", {"user_id": user_id})
            lang = get_user_language(update)
            await update.message.reply_text(
                translate("auth.access_denied", lang) + "\n\n" +
                translate("auth.contact_admin", lang)
            )
            logger.warning(f"用户 {user_id} 访问被拒绝")
            return
        log_user_step(user_id, "鉴权检查通过", {"user_id": user_id})

        logger.info(f"用户 {user_name} ({user_id}) 开始使用 Bot")
        log_user_step(user_id, "鉴权通过,开始Bot使用流程", {"user_name": user_name, "user_id": user_id})

        # 检查是否是新用户
        is_new_user = await self.user_manager.register_user(user_id, user_name)

        # 检查是否有画像
        has_profile = await self.profile_manager.get_profile(user_id) is not None

        if is_new_user or not has_profile:
            # 新用户或没有画像，开始偏好收集对话
            if not has_profile and not is_new_user:
                log_user_step(user_id, "老用户但无画像,重新开始偏好收集", {"user_id": user_id})
            else:
                log_user_step(user_id, "新用户检测,开始偏好收集对话", {"user_id": user_id})
            await self.conversation_manager.start_preference_conversation(update, context)
        else:
            # 老用户且有画像，显示主菜单
            log_user_step(user_id, "老用户检测,显示主菜单", {"user_id": user_id})
            await self.show_main_menu(update, context)
        log_user_step(user_id, "start命令完成", {"user_id": user_id, "is_new": is_new_user})

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        lang = get_user_language(update)
        help_text = f"""
{translate("commands.help.title", lang)}

{translate("commands.help.main_commands", lang)}
{translate("commands.help.cmd_start", lang)}
{translate("commands.help.cmd_profile", lang)}
{translate("commands.help.cmd_sources", lang)}
{translate("commands.help.cmd_feedback", lang)}
{translate("commands.help.cmd_test", lang)}

{translate("commands.help.features", lang)}
{translate("commands.help.feature_1", lang)}
{translate("commands.help.feature_2", lang)}
{translate("commands.help.feature_3", lang)}
{translate("commands.help.feature_4", lang)}

{translate("commands.help.feedback_ways", lang)}
{translate("commands.help.feedback_1", lang)}
{translate("commands.help.feedback_2", lang)}
{translate("commands.help.feedback_3", lang)}

{translate("commands.help.contact_admin", lang)}
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /profile 命令"""
        user_id = update.effective_user.id

        # 判断是命令还是回调
        is_callback = update.callback_query is not None
        query = update.callback_query if is_callback else None
        lang = get_user_language(update)

        # 发送"正在加载"提示
        if is_callback:
            await query.answer()  # 响应回调，避免超时
            # 先编辑消息显示加载状态
            try:
                await query.edit_message_text(translate("profile.loading", lang))
            except Exception as e:
                logger.warning(f"编辑消息失败，尝试发送新消息: {e}")
                # 如果编辑失败，发送新消息
                try:
                    loading_msg = await query.message.reply_text(translate("profile.loading", lang))
                except:
                    loading_msg = None
            else:
                loading_msg = None
        else:
            loading_msg = await update.message.reply_text(translate("profile.loading", lang))

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
                        profile += f"\n\n{translate('profile.stats_title', lang)}\n"
                        profile += translate('profile.total_feedbacks', lang, count=feedback_count) + "\n"
                        profile += translate('profile.positive_count', lang, count=stats.get('positive_count', 0)) + "\n"
                        profile += translate('profile.negative_count', lang, count=stats.get('negative_count', 0)) + "\n"
                        if stats.get("last_feedback_time"):
                            from datetime import datetime
                            last_time = datetime.fromisoformat(stats["last_feedback_time"]).strftime("%Y-%m-%d %H:%M")
                            profile += translate('profile.last_feedback', lang, time=last_time)

                # 准备键盘
                keyboard = [
                    [InlineKeyboardButton(translate("profile.edit_button", lang), callback_data="profile_edit")],
                    [InlineKeyboardButton(translate("profile.back_button", lang), callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # 合并消息，一次性发送（更快）
                full_text = f"{translate('profile.title', lang)}\n\n{profile}\n\n{translate('profile.select_action', lang)}"

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
                        await query.edit_message_text(translate("profile.no_profile", lang))
                    except:
                        await query.message.reply_text(translate("profile.no_profile", lang))
                await self.conversation_manager.start_preference_conversation(update, context)
        except Exception as e:
            log_user_error(user_id, "test_flow_failed", str(e))
            logger.error(f"测试流程失败: {e}", exc_info=True)
            error_text = translate("profile.load_failed", lang)
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
        lang = get_user_language(update)

        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            if update.message:
                await update.message.reply_text(translate("auth.no_access_permission", lang) + translate("auth.contact_admin", lang))
            elif update.callback_query:
                await update.callback_query.answer(translate("auth.no_access_permission", lang), show_alert=True)
            return

        # 显示设置菜单
        keyboard = [
            [InlineKeyboardButton(translate("settings.edit_profile", lang), callback_data="settings_profile")],
            [InlineKeyboardButton(translate("settings.manage_sources", lang), callback_data="settings_sources")],
            [InlineKeyboardButton(translate("settings.push_time", lang), callback_data="settings_push_time")],
            [InlineKeyboardButton(translate("settings.stats", lang), callback_data="settings_stats")],
            [InlineKeyboardButton(translate("settings.back", lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_text = f"{translate('settings.menu_title', lang)}\n\n{translate('settings.select_item', lang)}"

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
        lang = get_user_language(update)

        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            await update.message.reply_text(translate("auth.no_access_permission", lang))
            return

        await self._show_sources_menu(update, context, user_id)

    async def _show_sources_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
        """显示信息源管理菜单(增强版-带迁移检查和帮助)"""
        if user_id is None:
            user_id = update.effective_user.id
        
        lang = get_user_language(update)

        # 检查是否有新源需要迁移
        from core.custom_processes.web3digest.core.source_migration_manager import SourceMigrationManager
        migration_manager = SourceMigrationManager()
        migration_info = await migration_manager.check_and_notify(user_id)

        sources_config = await self.source_manager.get_user_sources(user_id)

        # 统计
        preset_count = len(sources_config["preset_sources"])
        preset_enabled = sum(1 for s in sources_config["preset_sources"] if s.get("enabled", True))
        custom_count = len(sources_config["custom_sources"])
        custom_enabled = sum(1 for s in sources_config["custom_sources"] if s.get("enabled", True))

        # 构建菜单文本
        menu_text = translate("sources.menu_title", lang) + "\n"

        # 如果有新源可用,显示提示
        if migration_info["has_new_sources"]:
            menu_text += f"\n{translate('sources.new_sources_found', lang, count=migration_info['count'])}\n"
            menu_text += f"{translate('sources.click_to_migrate', lang)}\n\n"

        menu_text += f"{translate('sources.preset_enabled', lang, enabled=preset_enabled, total=preset_count)}\n"
        menu_text += f"{translate('sources.custom_enabled', lang, enabled=custom_enabled, total=custom_count)}\n\n"
        menu_text += f"{translate('sources.tips', lang)}\n"
        menu_text += f"{translate('sources.tip_1', lang)}\n"
        menu_text += f"{translate('sources.tip_2', lang)}\n"
        menu_text += f"{translate('sources.tip_3', lang)}\n\n"
        menu_text += translate("sources.select_action", lang)

        keyboard = [
            [InlineKeyboardButton(translate("sources.view_preset", lang), callback_data="sources_view_preset")],
            [InlineKeyboardButton(translate("sources.add_twitter", lang), callback_data="sources_add_twitter")],
            [InlineKeyboardButton(translate("sources.add_website", lang), callback_data="sources_add_website")],
            [InlineKeyboardButton(translate("sources.my_custom", lang), callback_data="sources_view_custom")],
        ]

        # 如果有新源,添加迁移按钮
        if migration_info["has_new_sources"]:
            keyboard.append([InlineKeyboardButton(translate("sources.migrate_new", lang, count=migration_info['count']), callback_data="sources_migrate")])

        # 添加帮助按钮
        keyboard.append([InlineKeyboardButton(translate("sources.help_rss", lang), callback_data="sources_help")])
        keyboard.append([InlineKeyboardButton(translate("sources.back_menu", lang), callback_data="main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def _show_sources_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示信息源添加帮助文档"""
        lang = get_user_language(update)
        help_text = f"""{translate("sources_help.title", lang)}

━━━━━━━━━━━━━━━
{translate("sources_help.twitter_section", lang)}

{translate("sources_help.twitter_step1", lang)}
• {translate("sources_help.twitter_step1_1", lang)}
• {translate("sources_help.twitter_step1_2", lang)}

{translate("sources_help.twitter_step2", lang)}
• {translate("sources_help.twitter_step2_1", lang)}
• {translate("sources_help.twitter_step2_2", lang)}
• {translate("sources_help.twitter_step2_3", lang)}

━━━━━━━━━━━━━━━
{translate("sources_help.website_section", lang)}

{translate("sources_help.website_method1", lang)}
```
{translate("sources_help.website_examples", lang)}
```

{translate("sources_help.website_method2", lang)}
• {translate("sources_help.website_method2_1", lang)}
• {translate("sources_help.website_method2_2", lang)}
• {translate("sources_help.website_method2_3", lang)}

{translate("sources_help.website_step", lang)}
• {translate("sources_help.website_step_1", lang)}
• {translate("sources_help.website_step_2", lang)}
• {translate("sources_help.website_step_3", lang)}

━━━━━━━━━━━━━━━
{translate("sources_help.faq_section", lang)}

{translate("sources_help.faq_q1", lang)}
{translate("sources_help.faq_a1", lang)}

{translate("sources_help.faq_q2", lang)}
{translate("sources_help.faq_a2", lang)}

{translate("sources_help.faq_q3", lang)}
{translate("sources_help.faq_a3", lang)}

{translate("sources_help.faq_q4", lang)}
{translate("sources_help.faq_a4", lang)}
  {translate("sources_help.faq_a4_1", lang)}
  {translate("sources_help.faq_a4_2", lang)}
  {translate("sources_help.faq_a4_3", lang)}

━━━━━━━━━━━━━━━
{translate("sources_help.hint", lang)}"""

        keyboard = [[InlineKeyboardButton(translate("sources_help.back", lang), callback_data="sources_manage")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.edit_message_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def _show_push_time_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """显示推送时间设置界面"""
        lang = get_user_language(update)
        # 获取当前推送时间
        current_time = await self.profile_manager.get_push_time(user_id)

        # 预设时间选项
        preset_times = [
            ["07:00", "08:00", "09:00"],
            ["10:00", "12:00", "14:00"],
            ["16:00", "18:00", "20:00"],
            ["22:00", translate("push_time.custom_button", lang)]
        ]

        keyboard = []
        for row in preset_times:
            button_row = []
            for time_str in row:
                if time_str == translate("push_time.custom_button", lang):
                    button_row.append(InlineKeyboardButton(translate("push_time.custom_button", lang), callback_data="push_time_custom"))
                else:
                    # 标记当前选择的时间
                    prefix = "✅ " if time_str == current_time else ""
                    button_row.append(InlineKeyboardButton(f"{prefix}{time_str}", callback_data=f"push_time_{time_str}"))
            keyboard.append(button_row)

        keyboard.append([InlineKeyboardButton(translate("push_time.back_settings", lang), callback_data="settings_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_text = f"""{translate('push_time.title', lang)}

{translate('push_time.current_time', lang, time=current_time)}

{translate('push_time.select_time', lang)}

{translate('push_time.hint', lang)}
{translate('push_time.hint_1', lang)}
{translate('push_time.hint_2', lang)}
{translate('push_time.hint_3', lang)}
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
        lang = get_user_language(update)
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(translate("stats.calculating", lang))
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

        stats_text = f"""{translate('stats.title', lang)}

{translate('stats.digests', lang, count=total_digests)}
{translate('stats.feedbacks', lang, count=total_feedbacks)}
{translate('stats.time_saved', lang, hours=round(total_time_saved, 1))}
{translate('stats.sources', lang, enabled=enabled_sources, total=total_sources)}

{translate('stats.hint', lang)}
"""

        keyboard = [
            [InlineKeyboardButton(translate("stats.back_settings", lang), callback_data="settings_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def cmd_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /feedback 命令 - 主动反馈"""
        user_id = update.effective_user.id
        lang = get_user_language(update)

        # 鉴权检查
        if not await self.auth_manager.check_user_access(user_id):
            await update.message.reply_text(translate("auth.no_access_permission", lang))
            return

        keyboard = [
            [
                InlineKeyboardButton(translate("feedback.positive", lang), callback_data="feedback_positive_manual"),
                InlineKeyboardButton(translate("feedback.negative", lang), callback_data="feedback_negative_manual")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            translate("feedback.select_rating", lang),
            reply_markup=reply_markup
        )

    async def _generate_personalized_feedback_message(self, user_id: int, feedback_type: str, lang: str = 'zh') -> str:
        """
        生成个性化的反馈确认消息（Phase 2优化）

        Args:
            user_id: 用户ID
            feedback_type: "positive" 或 "negative"
            lang: 语言代码（默认 'zh'）

        Returns:
            个性化的确认消息
        """
        try:
            # 获取用户画像
            profile = await self.profile_manager.get_structured_profile(user_id)
            if not profile:
                # 如果没有画像，返回通用消息
                if feedback_type == "positive":
                    return translate("feedback.positive_thanks_generic", lang)
                else:
                    return translate("feedback.negative_recorded", lang)

            # 提取用户兴趣
            interests = profile.get("interests", [])
            preferences = profile.get("preferences", {})
            content_types = preferences.get("content_types", [])

            # 构建兴趣描述
            interest_desc = ""
            if interests:
                interest_desc = "、".join(interests[:2]) if lang == 'zh' else ", ".join(interests[:2])  # 最多显示2个
            elif content_types:
                interest_desc = "、".join(content_types[:2]) if lang == 'zh' else ", ".join(content_types[:2])

            # 生成个性化消息
            if feedback_type == "positive":
                if interest_desc:
                    # 注意：这里硬编码了消息格式，因为包含动态内容
                    # 如果后续需要更复杂的多语言，可以改为使用模板
                    if lang == 'zh':
                        return f"✅ 感谢反馈！我们会继续为您推荐 {interest_desc} 等相关内容"
                    else:
                        return f"✅ Thank you for the feedback! We will continue recommending {interest_desc} and related content"
                else:
                    return translate("feedback.positive_thanks_generic", lang)
            else:  # negative
                if interest_desc:
                    if lang == 'zh':
                        return f"📝 已记录！我们将优化 {interest_desc} 相关内容的推荐"
                    else:
                        return f"📝 Recorded! We will optimize recommendations for {interest_desc} and related content"
                else:
                    return translate("feedback.negative_recorded", lang)

        except Exception as e:
            logger.error(f"生成个性化反馈消息失败: {e}")
            # 失败时返回通用消息
            if feedback_type == "positive":
                return translate("feedback.positive_thanks_generic", lang)
            else:
                return translate("feedback.negative_recorded", lang)

    async def handle_manual_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, feedback_type: str):
        """处理手动反馈"""
        user_id = update.effective_user.id
        query = update.callback_query
        
        try:
            # 保存反馈
            from core.custom_processes.web3digest.core.feedback_manager import FeedbackManager
            feedback_manager = FeedbackManager()
            
            feedback_data = {
                "user_id": user_id,
                "overall": feedback_type,
                "reason_selected": [],
                "reason_text": "手动反馈",
                "timestamp": datetime.now().isoformat()
            }
            
            success = await feedback_manager.save_feedback(user_id, feedback_data)
            
            if success:
                # 更新用户画像
                from core.custom_processes.web3digest.core.feedback_analyzer import FeedbackAnalyzer
                feedback_analyzer = FeedbackAnalyzer()
                await feedback_analyzer.update_profile_with_feedback(user_id, feedback_data)
                
                # 显示感谢消息
                lang = get_user_language(update)
                if feedback_type == "positive":
                    await query.edit_message_text(translate("feedback.positive_thanks", lang))
                else:
                    # 询问具体原因
                    keyboard = [
                        [InlineKeyboardButton(translate("feedback.not_interested", lang), callback_data="feedback_reason_内容不感兴趣")],
                        [InlineKeyboardButton(translate("feedback.miss_important", lang), callback_data="feedback_reason_漏掉重要信息")],
                        [InlineKeyboardButton(translate("feedback.too_much", lang), callback_data="feedback_reason_信息太多/太杂")],
                        [InlineKeyboardButton(translate("feedback.too_little", lang), callback_data="feedback_reason_信息太少")],
                        [InlineKeyboardButton(translate("feedback.skip", lang), callback_data="feedback_reason_skip")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(translate("feedback.reason_required", lang), reply_markup=reply_markup)
            else:
                lang = get_user_language(update)
                await query.answer(translate("feedback.save_failed", lang), show_alert=True)
                
        except Exception as e:
            logger.error(f"处理手动反馈失败: {e}", exc_info=True)
            lang = get_user_language(update)
            await query.answer(translate("feedback.process_failed", lang), show_alert=True)
    
    async def handle_feedback_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理反馈回调（Phase 2优化：添加个性化确认消息）"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data

        if data.startswith("feedback_positive"):
            # 正面反馈
            await self.feedback_manager.save_feedback(user_id, "positive")

            # 生成个性化确认消息
            lang = get_user_language(update)
            message = await self._generate_personalized_feedback_message(user_id, "positive", lang)
            try:
                await query.answer(message, show_alert=False)
            except BadRequest as e:
                # 处理查询超时或无效的情况
                if "Query is too old" in str(e) or "query id is invalid" in str(e):
                    logger.warning(f"Callback query timeout for user {user_id}: {e}")
                else:
                    logger.error(f"BadRequest in handle_feedback_callback (positive): {e}")

            # 发送一条新消息，让用户看到AI在学习
            try:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=f"{message}\n\n{translate('feedback.ai_learning', lang)}"
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
            lang = get_user_language(update)
            try:
                message = await self._generate_personalized_feedback_message(user_id, "negative", lang)
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
            lang = get_user_language(update)
            reason_msg = await self._show_feedback_reasons_optional(query, user_id, lang)
            if reason_msg:
                self._active_feedback_reasons[user_id] = reason_msg.message_id

    async def _show_feedback_reasons(self, query):
        """显示反馈原因选择（旧方法，保留兼容）"""
        await self._show_feedback_reasons_new(query, query.from_user.id)

    async def _show_feedback_reasons_new(self, query, user_id: int):
        """显示反馈原因选择（发送新消息）- 已废弃，保留兼容"""
        # 默认使用中文（已废弃的函数，保持兼容性）
        await self._show_feedback_reasons_optional(query, user_id, 'zh')

    async def _show_feedback_reasons_optional(self, query, user_id: int, lang: str = 'zh'):
        """显示可选的反馈原因选择（不强制）"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton(translate("feedback.not_interested", lang), callback_data="feedback_reason_内容不感兴趣")],
            [InlineKeyboardButton(translate("feedback.miss_important", lang), callback_data="feedback_reason_漏掉重要信息")],
            [InlineKeyboardButton(translate("feedback.too_much", lang), callback_data="feedback_reason_信息太多/太杂")],
            [InlineKeyboardButton(translate("feedback.too_little", lang), callback_data="feedback_reason_信息太少")],
            [InlineKeyboardButton(translate("feedback.skip", lang), callback_data="feedback_reason_skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 发送新消息（可选，用户可以选择跳过）
        msg = await self.application.bot.send_message(
            chat_id=user_id,
            text=translate("feedback.reason_optional", lang),
            reply_markup=reply_markup
        )
        return msg

    async def _show_item_feedback_reasons(self, user_id: int, item_id: str, source: str, lang: str = 'zh'):
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

        # 使用英文代码代替中文，避免 callback_data 编码问题
        keyboard = [
            [InlineKeyboardButton(translate("feedback.not_interested", lang), callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_not_interested")],
            [InlineKeyboardButton(translate("feedback.miss_important", lang), callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_miss_important")],
            [InlineKeyboardButton(translate("feedback.too_much", lang), callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_too_much")],
            [InlineKeyboardButton(translate("feedback.too_little", lang), callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_too_little")],
            [InlineKeyboardButton(translate("feedback.skip", lang), callback_data=f"item_feedback_reason_{safe_item_id}_{safe_source}_skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 发送新消息（可选，用户可以选择跳过）
        msg = await self.application.bot.send_message(
            chat_id=user_id,
            text=translate("feedback.reason_optional", lang),
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
        lang = get_user_language(update)
        try:
            await query.edit_message_text(translate("feedback.processing", lang))
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
                    f"{translate('feedback.saved', lang)}\n\n"
                    f"{translate('feedback.supplement', lang)}"
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
            lang = get_user_language(update)
            try:
                await query.edit_message_text(
                    f"{translate('feedback.saved_with_reason', lang, reason=reason)}\n\n"
                    f"{translate('feedback.supplement', lang)}"
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
        lang = get_user_language(update)
        try:
            await query.edit_message_text(translate("feedback.processing", lang))
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
        reason_code = parts[2]

        # 映射英文代码到中文原因
        reason_map = {
            "not_interested": "内容不感兴趣",
            "miss_important": "漏掉重要信息",
            "too_much": "信息太多/太杂",
            "too_little": "信息太少"
        }
        reason = reason_map.get(reason_code, reason_code)

        if reason_code == "skip":
            # 跳过，直接保存反馈（不带原因）
            await self.feedback_manager.add_item_feedback(user_id, item_id, source, "dislike")
            # 编辑消息显示确认
            lang = get_user_language(update)
            try:
                await query.edit_message_text(
                    f"{translate('feedback.item_saved', lang)}\n\n"
                    f"{translate('feedback.item_reduce', lang)}\n\n"
                    f"{translate('feedback.item_supplement', lang)}"
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
            lang = get_user_language(update)
            try:
                await query.edit_message_text(
                    f"{translate('feedback.item_recorded', lang, reason=reason)}\n\n"
                    f"{translate('feedback.item_thanks', lang)}\n\n"
                    f"{translate('feedback.item_supplement', lang)}"
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

        # 记录按钮点击步骤
        log_user_step(user_id, f"处理单条信息反馈: {data[:50]}", {"action_type": "item_feedback"})

        # 解析多种格式：
        # - item_like_{item_id}_{source}
        # - item_dislike_{item_id}_{source}
        # - item_feedback_{rating}_{item_id}_{source}（旧格式）

        log_user_step(user_id, f"处理单条信息反馈: {data[:50]}", {"action_type": "item_feedback"})
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
            lang = get_user_language(update)
            try:
                await query.answer(translate("feedback.item_liked", lang), show_alert=False)
            except BadRequest as e:
                # 处理查询超时或无效的情况
                if "Query is too old" in str(e) or "query id is invalid" in str(e):
                    logger.warning(f"Callback query timeout for user {user_id}: {e}")
                else:
                    logger.error(f"BadRequest in handle_item_feedback: {e}")
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
            lang = get_user_language(update)
            await self._show_item_feedback_reasons(user_id, item_id, source, lang)

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
        lang = get_user_language(update) if not is_callback else 'zh'  # 回调时使用默认语言
        if not await self.auth_manager.check_user_access(user_id):
            if is_callback:
                await context.bot.send_message(chat.id, translate("test.no_access", lang))
            else:
                await update.message.reply_text(translate("test.no_access", lang))
            return

        # 简化测试流程 - 无论是否有画像都允许测试
        profile = await self.profile_manager.get_profile(user_id)
        if not profile and not is_callback:
            # 命令行式执行，提示设置偏好
            await update.message.reply_text(translate("test.no_profile", lang))
            return

        # 发送测试提示 - 按钮点击可以直接执行
        if is_callback:
            await context.bot.send_message(chat.id, translate("test.starting", lang))
            status_msg = await context.bot.send_message(chat.id, translate("test.crawling", lang))
        else:
            lang = get_user_language(update)
            status_msg = await update.message.reply_text(f"{translate('test.testing', lang)}\n\n{translate('test.step_1', lang)}")

        try:
            log_user_step(user_id, "开始测试简报流程", {"action": "test_digest", "has_profile": profile is not None})

            from core.custom_processes.web3digest.core.scheduler import DigestScheduler
            scheduler = DigestScheduler(self)

            # 直接使用调度器生成简报
            result = await scheduler.trigger_manual_digest_with_status(user_id, status_msg)

            if not result["success"]:
                # 失败消息已在 trigger_manual_digest_with_status 中处理
                pass

        except Exception as e:
            log_user_error(user_id, "test_flow_failed", str(e))
            logger.error(f"测试流程失败: {e}", exc_info=True)
            try:
                lang = get_user_language(update) if hasattr(update, 'effective_user') else 'zh'
                await status_msg.edit_text(translate("test.error", lang, error=str(e)))
            except:
                pass

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示主菜单 - 带步骤日志"""
        user_id = update.effective_user.id
        lang = get_user_language(update)
        log_user_step(user_id, "显示主菜单", {"update_type": "message" if update.message else "callback"})
        await self._send_main_menu(user_id, lang)

    async def show_main_menu_by_id(self, user_id: int, lang: str = 'zh'):
        """通过用户ID显示主菜单"""
        log_user_step(user_id, "显示主菜单", {"trigger": "after_test"})
        await self._send_main_menu(user_id, lang)

    async def _send_main_menu(self, user_id: int, lang: str = 'zh'):
        """发送主菜单消息"""
        keyboard = [
            [InlineKeyboardButton(translate("main_menu.edit_profile", lang), callback_data="settings_profile")],
            [InlineKeyboardButton(translate("main_menu.manage_sources", lang), callback_data="settings_sources")],
            [InlineKeyboardButton(translate("main_menu.push_time", lang), callback_data="settings_push_time")],
            [InlineKeyboardButton(translate("main_menu.view_stats", lang), callback_data="settings_stats")],
            [InlineKeyboardButton(translate("main_menu.test_digest", lang), callback_data="test_digest")],
            [InlineKeyboardButton(translate("main_menu.back", lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_text = f"""
{translate("main_menu.welcome", lang)}

{translate("main_menu.select_action", lang)}
        """

        try:
            log_user_step(user_id, "发送主菜单消息", {"method": "direct"})
            await self.application.bot.send_message(
                chat_id=user_id,
                text=welcome_text,
                reply_markup=reply_markup
            )
            log_user_step(user_id, "主菜单显示完成", {"method": "direct"})
        except Exception as e:
            log_user_error(user_id, "show_main_menu_failed", str(e))
            logger.error(f"显示主菜单失败: {e}")

    # 消息处理器
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息（用于对话式偏好收集和信息源添加）"""
        user_id = update.effective_user.id

        # 鉴权检查（除了对话中的消息，因为对话开始前已经检查过）
        lang = get_user_language(update)
        if user_id not in self._adding_source_state:
            if not await self.auth_manager.check_user_access(user_id):
                await update.message.reply_text(translate("auth.no_access_permission", lang))
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
                        f"{translate('push_time.format_error', lang)}\n\n"
                        f"{translate('push_time.format_error_desc', lang)}\n"
                        f"{translate('push_time.format_examples', lang)}\n"
                        f"{translate('push_time.format_range', lang)}"
                    )
                    return

                # 更新推送时间
                success = await self.profile_manager.update_push_time(user_id, time_str)
                if success:
                    del self._custom_push_time_state[user_id]
                    await update.message.reply_text(
                        f"{translate('push_time.time_saved', lang, time=time_str)}\n\n"
                        f"{translate('push_time.time_saved_desc', lang)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await update.message.reply_text(translate("push_time.set_failed", lang))
            except ValueError:
                await update.message.reply_text(
                    f"{translate('push_time.format_error', lang)}\n\n"
                    f"{translate('push_time.format_error_desc', lang)}\n"
                    f"{translate('push_time.format_examples', lang)}"
                )
        else:
            # 不在对话中，提示使用命令
            await update.message.reply_text(translate("messages.use_start", lang))

    # 回调处理器
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮点击"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data

        # 记录所有按钮点击
        log_user_click(user_id, data, query.message.text if query.message else "")

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
        elif data == "setup_preferences":
            # 设置偏好（来自 run_bot.py）
            await self.conversation_manager.start_preference_conversation(update, context)
        elif data == "view_sources":
            # 查看信息源（来自 run_bot.py）
            user_id = update.effective_user.id
            await self._show_sources_menu(update, context, user_id)
        elif data.startswith("conv_"):
            # 对话相关回调
            await self.conversation_manager.handle_callback(update, context)
        elif data.startswith("domain_"):
            # 领域选择回调（对话中的快速选择）
            await self.conversation_manager.handle_callback(update, context)
        elif data == "test_digest":
            # 测试简报回调
            log_user_step(user_id, "开始测试简报流程", {"callback_data": data})
            await self.cmd_test(update, context)
            log_user_step(user_id, "测试简报流程完成", {"callback_data": data})
        elif data.startswith("feedback_reason_"):
            # 反馈原因选择 (必须在 feedback_ 之前判断，因为 feedback_reason_ 也以 feedback_ 开头)
            await self.handle_feedback_reason(update, context)
        elif data.startswith("feedback_"):
            # 反馈相关回调
            await self.handle_feedback_callback(update, context)
        elif data == "feedback_positive_manual":
            # 手动正面反馈
            await self.handle_manual_feedback(update, context, "positive")
        elif data == "feedback_negative_manual":
            # 手动负面反馈
            await self.handle_manual_feedback(update, context, "negative")
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
                lang = get_user_language(update)
                success = await self.source_manager.remove_custom_source(update.effective_user.id, source_id)
                if success:
                    await query.edit_message_text(translate("source_actions.deleted", lang))
                    from core.custom_processes.web3digest.bot.source_handlers import show_custom_sources
                    await show_custom_sources(self, update, context)
                else:
                    lang = get_user_language(update)
                    try:
                        await query.answer(translate("source_actions.delete_failed", lang), show_alert=True)
                    except BadRequest as e:
                        if "Query is too old" in str(e) or "query id is invalid" in str(e):
                            logger.warning(f"Callback query timeout for user {update.effective_user.id}: {e}")
                        else:
                            logger.error(f"BadRequest in source_delete_confirm: {e}")
            else:
                from core.custom_processes.web3digest.bot.source_handlers import handle_delete_source
                await handle_delete_source(self, update, context)
        elif data == "sources_migrate":
            # 迁移新增的预设信息源
            user_id = update.effective_user.id
            from core.custom_processes.web3digest.core.source_migration_manager import SourceMigrationManager
            migration_manager = SourceMigrationManager()

            # 显示处理中提示
            lang = get_user_language(update)
            await query.edit_message_text(translate("migration.migrating", lang))

            # 执行迁移
            result = await migration_manager.migrate_user_sources(user_id)

            if result["migrated"] > 0:
                # 构建迁移成功消息
                new_sources_text = "\n".join([f"• {name}" for name in result["new_sources"]])
                success_text = f"""{translate('migration.success_title', lang)}

{translate('migration.success_desc', lang, count=result['migrated'])}

{new_sources_text}

💡 您可以在"查看预设信息源"中管理这些源"""

                await query.edit_message_text(success_text, parse_mode=ParseMode.MARKDOWN)
                await asyncio.sleep(2)
            else:
                await query.edit_message_text(translate("migration.no_new", lang))
                await asyncio.sleep(1)

            # 返回源管理菜单
            await self._show_sources_menu(update, context, user_id)

        elif data == "sources_help":
            # 显示信息源帮助文档
            await self._show_sources_help(update, context)

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
                lang = get_user_language(update)
                await query.edit_message_text(
                    f"{translate('push_time.custom_title', lang)}\n\n"
                    f"{translate('push_time.custom_input', lang)}\n"
                    f"{translate('push_time.custom_examples', lang)}\n\n"
                    f"{translate('push_time.custom_hint', lang)}",
                    parse_mode=ParseMode.MARKDOWN
                )
                # 标记用户正在输入自定义时间
                self._custom_push_time_state = getattr(self, '_custom_push_time_state', {})
                self._custom_push_time_state[user_id] = True
            else:
                # 选择预设时间
                success = await self.profile_manager.update_push_time(user_id, time_str)
                lang = get_user_language(update)
                if success:
                    try:
                        await query.answer(translate("push_time.time_set", lang, time=time_str), show_alert=False)
                    except BadRequest as e:
                        if "Query is too old" in str(e) or "query id is invalid" in str(e):
                            logger.warning(f"Callback query timeout for user {user_id}: {e}")
                        else:
                            logger.error(f"BadRequest in push_time_settings: {e}")
                    await self._show_push_time_settings(update, context, user_id)
                else:
                    try:
                        await query.answer(translate("push_time.set_failed", lang), show_alert=True)
                    except BadRequest as e:
                        if "Query is too old" in str(e) or "query id is invalid" in str(e):
                            logger.warning(f"Callback query timeout for user {user_id}: {e}")
                        else:
                            logger.error(f"BadRequest in push_time_settings (failed): {e}")
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
            lang = get_user_language(update)
            try:
                await query.edit_message_text(translate("common.function_developing", lang))
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    # 消息内容相同，忽略错误
                    pass
                else:
                    logger.error(f"编辑消息失败: {e}")
                    # 尝试回答回调
                    try:
                        await query.answer(translate("common.function_developing", lang), show_alert=True)
                    except:
                        pass

    # 管理员命令
    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /admin 命令 - 管理员功能"""
        user_id = update.effective_user.id

        # 检查管理员权限
        lang = get_user_language(update)
        if not await self.auth_manager.is_admin(user_id):
            await update.message.reply_text(translate("admin.admin_no_permission", lang))
            logger.warning(f"用户 {user_id} 尝试访问管理员功能但无权限")
            return

        # 显示管理员菜单
        keyboard = [
            [InlineKeyboardButton(translate("admin.user_management", lang), callback_data="admin_users")],
            [InlineKeyboardButton(translate("admin.whitelist", lang), callback_data="admin_whitelist")],
            [InlineKeyboardButton(translate("admin.blacklist", lang), callback_data="admin_blacklist")],
            [InlineKeyboardButton(translate("admin.system_stats", lang), callback_data="admin_stats")],
            [InlineKeyboardButton(translate("admin.back_menu", lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_text = f"""{translate('admin.title', lang)}

{translate('admin.select_function', lang)}"""

        await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理管理员回调"""
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data

        # 检查管理员权限
        lang = get_user_language(update)
        if not await self.auth_manager.is_admin(user_id):
            try:
                await query.answer(translate("admin.no_permission", lang), show_alert=True)
            except BadRequest as e:
                if "Query is too old" in str(e) or "query id is invalid" in str(e):
                    logger.warning(f"Callback query timeout for user {user_id}: {e}")
                else:
                    logger.error(f"BadRequest in admin_callback (permission): {e}")
            return

        try:
            await query.answer()
        except BadRequest as e:
            if "Query is too old" in str(e) or "query id is invalid" in str(e):
                logger.warning(f"Callback query timeout for admin user {user_id}: {e}")
            else:
                logger.error(f"BadRequest in admin_callback: {e}")

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
        lang = get_user_language(update)

        users = await self.user_manager.get_all_users()

        text = f"{translate('admin.user_mgmt_title', lang)}\n\n{translate('admin.total_users', lang, count=len(users))}\n\n"

        # 显示前10个用户
        for i, user in enumerate(users[:10], 1):
            user_id = int(user.get("id", 0))
            status = await self.auth_manager.get_user_status(user_id)
            role = await self.auth_manager.get_user_role(user_id)

            status_icon = {
                UserStatus.ACTIVE: translate("admin.status_active", lang),
                UserStatus.INACTIVE: translate("admin.status_inactive", lang),
                UserStatus.BANNED: translate("admin.status_banned", lang),
                UserStatus.SUSPENDED: translate("admin.status_suspended", lang)
            }.get(status, "❓")

            text += f"{i}. {user.get('name', 'Unknown')} ({user_id})\n"
            text += f"   {translate('admin.role', lang)}: {role.value} | {translate('admin.status', lang)}: {status_icon} {status.value}\n\n"

        if len(users) > 10:
            text += translate("admin.more_users", lang, count=len(users) - 10)

        keyboard = [
            [InlineKeyboardButton(translate("admin.back_admin", lang), callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def _show_whitelist_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示白名单管理界面"""
        lang = get_user_language(update)
        whitelist = await self.auth_manager.get_whitelist()

        text = f"{translate('admin.whitelist_title', lang)}\n\n{translate('admin.whitelist_count', lang, count=len(whitelist))}\n\n"

        if whitelist:
            for user_id in whitelist[:10]:
                user = await self.user_manager.get_user(user_id)
                name = user.get("name", "Unknown") if user else "Unknown"
                text += f"• {name} ({user_id})\n"
        else:
            text += translate("admin.whitelist_empty", lang)

        keyboard = [
            [InlineKeyboardButton(translate("admin.add_user", lang), callback_data="admin_wl_add")],
            [InlineKeyboardButton(translate("admin.remove_user", lang), callback_data="admin_wl_remove")],
            [InlineKeyboardButton(translate("admin.back_admin", lang), callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def _show_blacklist_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示黑名单管理界面"""
        lang = get_user_language(update)
        blacklist = await self.auth_manager.get_blacklist()

        text = f"{translate('admin.blacklist_title', lang)}\n\n{translate('admin.blacklist_count', lang, count=len(blacklist))}\n\n"

        if blacklist:
            for user_id in blacklist[:10]:
                user = await self.user_manager.get_user(user_id)
                name = user.get("name", "Unknown") if user else "Unknown"
                text += f"• {name} ({user_id})\n"
        else:
            text += translate("admin.blacklist_empty", lang)

        keyboard = [
            [InlineKeyboardButton(translate("admin.add_user", lang), callback_data="admin_bl_add")],
            [InlineKeyboardButton(translate("admin.remove_user", lang), callback_data="admin_bl_remove")],
            [InlineKeyboardButton(translate("admin.back_admin", lang), callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def _show_system_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示系统统计"""
        lang = get_user_language(update)
        users = await self.user_manager.get_all_users()
        active_users = await self.user_manager.get_active_users()
        admins = await self.auth_manager.get_all_admins()
        whitelist = await self.auth_manager.get_whitelist()
        blacklist = await self.auth_manager.get_blacklist()

        text = f"""{translate('admin.system_stats_title', lang)}

{translate('admin.user_stats', lang)}
• {translate('admin.total_users_stat', lang, count=len(users))}
• {translate('admin.active_users', lang, count=len(active_users))}
• {translate('admin.admin_count', lang, count=len(admins))}

{translate('admin.auth_stats', lang)}
• {translate('admin.whitelist_stat', lang, count=len(whitelist))}
• {translate('admin.blacklist_stat', lang, count=len(blacklist))}
"""

        keyboard = [
            [InlineKeyboardButton(translate("admin.back_admin", lang), callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def _handle_user_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理用户操作"""
        # TODO: 实现用户操作（封禁、解封、设置角色等）
        lang = get_user_language(update)
        await update.callback_query.answer(translate("common.function_developing", lang), show_alert=True)

    async def _handle_whitelist_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理白名单操作"""
        # TODO: 实现白名单添加/移除
        lang = get_user_language(update)
        await update.callback_query.answer(translate("common.function_developing", lang), show_alert=True)

    async def _handle_blacklist_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理黑名单操作"""
        # TODO: 实现黑名单添加/移除
        lang = get_user_language(update)
        await update.callback_query.answer(translate("common.function_developing", lang), show_alert=True)
