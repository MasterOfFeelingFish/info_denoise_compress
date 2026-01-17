"""
信息源管理相关的 Bot 处理方法
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)


async def show_preset_sources(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示预设信息源列表"""
    user_id = update.effective_user.id
    sources_config = await bot.source_manager.get_user_sources(user_id)
    
    preset_sources = sources_config["preset_sources"]
    
    # 按分类分组
    by_category = {}
    for source in preset_sources:
        category = source.get("category", "其他")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(source)
    
    # 生成文本
    text_parts = ["📋 **预设信息源列表**\n"]
    
    for category, sources in by_category.items():
        text_parts.append(f"\n**{category}** ({len(sources)} 个)")
        for source in sources[:10]:  # 每类最多显示10个
            status = "✅" if source.get("enabled", True) else "❌"
            text_parts.append(f"{status} {source['name']}")
        if len(sources) > 10:
            text_parts.append(f"... 还有 {len(sources) - 10} 个")
    
    text = "\n".join(text_parts)
    
    # 生成按钮（分页显示，每页10个）
    keyboard = []
    page_size = 10
    total_pages = (len(preset_sources) + page_size - 1) // page_size
    current_page = 0  # 简化：只显示第一页
    
    for i in range(min(page_size, len(preset_sources))):
        source = preset_sources[i]
        status_icon = "✅" if source.get("enabled", True) else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {source['name']}",
                callback_data=f"source_toggle_{source['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="sources_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text[:4000],  # Telegram 消息长度限制
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


async def show_custom_sources(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示自定义信息源列表"""
    user_id = update.effective_user.id
    sources_config = await bot.source_manager.get_user_sources(user_id)
    
    custom_sources = sources_config["custom_sources"]
    
    if not custom_sources:
        text = "📝 **我的自定义信息源**\n\n暂无自定义信息源。\n\n点击下方按钮添加："
        keyboard = [
            [InlineKeyboardButton("➕ 添加 Twitter 账号", callback_data="sources_add_twitter")],
            [InlineKeyboardButton("➕ 添加网站 RSS", callback_data="sources_add_website")],
            [InlineKeyboardButton("🔙 返回", callback_data="sources_back")]
        ]
    else:
        text = "📝 **我的自定义信息源**\n\n"
        for source in custom_sources:
            status = "✅" if source.get("enabled", True) else "❌"
            text += f"{status} {source['name']}\n"
        
        keyboard = []
        for source in custom_sources:
            status_icon = "✅" if source.get("enabled", True) else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} {source['name']}",
                    callback_data=f"source_toggle_{source['id']}"
                ),
                InlineKeyboardButton("🗑️", callback_data=f"source_delete_{source['id']}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="sources_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


async def start_add_twitter(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始添加 Twitter 账号流程"""
    user_id = update.effective_user.id
    
    # 设置状态
    bot._adding_source_state[user_id] = {"type": "twitter", "step": "waiting"}
    
    text = """➕ **添加 Twitter 账号**

请输入 Twitter 用户名（带或不带 @ 都可以）：

示例：
• VitalikButerin
• @VitalikButerin

输入 /cancel 取消"""
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def start_add_website(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始添加网站 RSS 流程"""
    user_id = update.effective_user.id
    
    # 设置状态
    bot._adding_source_state[user_id] = {"type": "website", "step": "waiting"}
    
    text = """➕ **添加网站 RSS**

请输入 RSS 源的 URL：

示例：
• https://www.theblock.co/rss.xml
• https://foresightnews.pro/feed

输入 /cancel 取消"""
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_add_source_input(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户输入的信息源（增强版）"""
    user_id = update.effective_user.id
    input_text = update.message.text.strip()

    if input_text.lower() == "/cancel":
        del bot._adding_source_state[user_id]
        await update.message.reply_text("❌ 已取消添加信息源")
        return

    state = bot._adding_source_state.get(user_id)
    if not state:
        return

    source_type = state["type"]

    # 显示处理中
    processing_msg = await update.message.reply_text("⏳ 正在验证信息源（检查可用性和内容质量）...")

    try:
        if source_type == "twitter":
            result = await bot.source_manager.add_custom_twitter(user_id, input_text)
        elif source_type == "website":
            result = await bot.source_manager.add_custom_website(user_id, input_text)
        else:
            result = {"success": False, "message": "未知的信息源类型"}

        # 清除状态
        del bot._adding_source_state[user_id]

        # 显示结果（增强版）
        if result["success"]:
            success_text = f"{result['message']}\n\n✅ 信息源已添加并启用，将在下次抓取时生效。"

            # 如果有警告信息，附加显示
            if result.get("warning"):
                success_text += f"\n\n⚠️ {result['warning']}"

            await processing_msg.edit_text(success_text)
        else:
            # 构建详细的错误消息
            error_text = f"❌ 添加失败\n\n{result['message']}"

            # 根据错误码提供更多上下文
            error_code = result.get("error_code")
            if error_code == "TIMEOUT":
                error_text += "\n\n💡 提示：该源响应较慢，请检查URL或稍后重试。"
            elif error_code == "HTTP_ERROR":
                error_text += "\n\n💡 提示：请检查URL是否正确，确保可以访问。"
            elif error_code == "EMPTY_FEED":
                error_text += "\n\n💡 提示：该RSS源当前没有任何内容，可能URL不正确。"
            elif error_code == "LOW_QUALITY_FEED":
                error_text += "\n\n💡 提示：该源缺少有效内容，请确认是否为有效的RSS源。"
            elif error_code == "STALE_FEED":
                error_text += "\n\n💡 提示：该源长时间未更新，可能已废弃。"
            elif error_code == "PARSE_ERROR":
                error_text += "\n\n💡 提示：RSS格式解析失败，请确认URL是否正确。"
            elif error_code == "INVALID_USERNAME":
                error_text += "\n\n💡 提示：Twitter用户名只能包含字母、数字和下划线。"

            await processing_msg.edit_text(error_text)

    except Exception as e:
        logger.error(f"添加信息源失败: {e}", exc_info=True)
        del bot._adding_source_state[user_id]
        await processing_msg.edit_text(f"❌ 添加失败：{str(e)}")


async def handle_toggle_source(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """切换信息源启用/禁用状态"""
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    # 提取 source_id
    source_id = data.replace("source_toggle_", "")
    
    success = await bot.source_manager.toggle_source(user_id, source_id)
    
    if success:
        # 获取更新后的状态
        sources_config = await bot.source_manager.get_user_sources(user_id)
        
        # 查找该源
        all_sources = sources_config["preset_sources"] + sources_config["custom_sources"]
        source = next((s for s in all_sources if s["id"] == source_id), None)
        
        if source:
            status = "已启用" if source.get("enabled", True) else "已禁用"
            await query.answer(f"✅ {source['name']} {status}", show_alert=False)
            
            # 刷新当前页面
            if source.get("is_preset"):
                await show_preset_sources(bot, update, context)
            else:
                await show_custom_sources(bot, update, context)
    else:
        await query.answer("❌ 操作失败", show_alert=True)


async def handle_delete_source(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除自定义信息源"""
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    # 提取 source_id
    source_id = data.replace("source_delete_", "")
    
    # 获取源信息（用于确认）
    sources_config = await bot.source_manager.get_user_sources(user_id)
    source = next((s for s in sources_config["custom_sources"] if s["id"] == source_id), None)
    
    if not source:
        await query.answer("❌ 未找到该信息源", show_alert=True)
        return
    
    # 确认删除
    keyboard = [
        [
            InlineKeyboardButton("✅ 确认删除", callback_data=f"source_delete_confirm_{source_id}"),
            InlineKeyboardButton("❌ 取消", callback_data="sources_view_custom")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🗑️ **确认删除**\n\n"
        f"确定要删除信息源：{source['name']} 吗？\n\n"
        f"删除后该源将不再被抓取。",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
