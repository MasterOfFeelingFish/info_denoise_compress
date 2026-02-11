"""
Admin Handlers for Whitelist Management.
Provides both command handlers and callback button handlers.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from utils.json_storage import (
    get_whitelist, add_to_whitelist, remove_from_whitelist, get_users,
    get_whitelist_enabled, set_whitelist_enabled, get_events_summary,
    get_feedback_reason_stats, get_user_language
)
from locales.ui_strings import get_ui_locale
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Conversation states for admin flows
WAITING_FOR_USER_ID = 100
WAITING_FOR_BULK_SOURCES = 101


def is_admin(user_id: int) -> bool:
    """Check if user is admin. Supports multiple admins from env variable."""
    from config import ADMIN_TELEGRAM_IDS
    return str(user_id) in ADMIN_TELEGRAM_IDS


def get_user_info(telegram_id: int) -> dict:
    """Get user info from users.json by telegram_id."""
    users = get_users()
    for user in users:
        if str(user.get("telegram_id")) == str(telegram_id):
            return user
    return None


# ============ Button-based Admin Panel ============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel with buttons (callback handler)."""
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    # Get language - admin might have different language
    lang = get_user_language(str(user_id))
    ui = get_ui_locale(lang)

    if not is_admin(user_id):
        if query:
            await query.answer(ui["admin_no_permission"], show_alert=True)
        return

    # Get current whitelist status
    wl_enabled = get_whitelist_enabled()
    wl_status = ui["admin_whitelist_on"] if wl_enabled else ui["admin_whitelist_off"]
    toggle_text = ui["admin_toggle_off"] if wl_enabled else ui["admin_toggle_on"]
    toggle_emoji = "🔴" if wl_enabled else "🟢"

    keyboard = [
        [InlineKeyboardButton(ui["admin_data_analysis"], callback_data="admin_analytics")],
        [InlineKeyboardButton("📡 信息源健康", callback_data="admin_source_health")],
        [InlineKeyboardButton("📢 群组管理", callback_data="admin_group_manage")],
        [InlineKeyboardButton("🎫 生成兑换码", callback_data="admin_gen_code")],
        [InlineKeyboardButton(f"{toggle_emoji} {toggle_text}", callback_data="admin_wl_toggle")],
        [InlineKeyboardButton(ui["admin_view_whitelist"], callback_data="admin_wl_list")],
        [
            InlineKeyboardButton(ui["admin_add_user"], callback_data="admin_wl_add"),
            InlineKeyboardButton(ui["admin_remove_user"], callback_data="admin_wl_del"),
        ],
        [InlineKeyboardButton(ui["back_to_main"], callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    whitelist = get_whitelist()
    users = get_users()
    text = (
        f"<b>{ui['admin_title']}</b>\n"
        f"{ui['divider']}\n\n"
        f"{ui['admin_users_count'].format(count=len(users))}\n"
        f"{ui['admin_whitelist_status'].format(status=wl_status)}\n"
        f"{ui['admin_whitelist_count'].format(count=len(whitelist))}\n\n"
        f"{ui['admin_choose_action']}"
    )

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def admin_wl_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle whitelist enabled/disabled."""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    # Toggle the status
    current = get_whitelist_enabled()
    new_status = not current
    set_whitelist_enabled(new_status)
    
    status_text = "开启" if new_status else "关闭"
    await query.answer(f"✅ 白名单已{status_text}", show_alert=True)
    logger.info(f"Admin {query.from_user.id} toggled whitelist to {new_status}")
    
    # Refresh the panel
    await admin_panel(update, context)


async def admin_wl_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show whitelist with user details (callback handler)."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    whitelist = get_whitelist()

    if not whitelist:
        text = "📋 <b>白名单为空</b>\n\n暂无授权用户。"
    else:
        text = f"📋 <b>白名单用户 ({len(whitelist)} 人)</b>\n"
        text += f"{'─' * 24}\n\n"

        for uid in whitelist:
            user_info = get_user_info(uid)
            if user_info:
                username = user_info.get("username") or "无"
                first_name = user_info.get("first_name") or "未知"
                created = user_info.get("created", "")[:10] if user_info.get("created") else "未知"
                text += f"• <b>{first_name}</b>\n"
                text += f"  ID: <code>{uid}</code>\n"
                text += f"  用户名: @{username}\n"
                text += f"  注册: {created}\n\n"
            else:
                text += f"• ID: <code>{uid}</code> (未注册)\n\n"

    keyboard = [[InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def admin_wl_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt admin to enter user ID to add."""
    from utils.conv_manager import activate_conv
    activate_conv(context, "admin")

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    keyboard = [[InlineKeyboardButton("取消", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "➕ <b>添加用户到白名单</b>\n\n"
        "请发送要添加的用户 Telegram ID（纯数字）：",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    context.user_data["admin_action"] = "add"
    return WAITING_FOR_USER_ID


async def admin_wl_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt admin to enter user ID to remove."""
    from utils.conv_manager import activate_conv
    activate_conv(context, "admin")

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    keyboard = [[InlineKeyboardButton("取消", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "➖ <b>从白名单删除用户</b>\n\n"
        "请发送要删除的用户 Telegram ID（纯数字）：",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    context.user_data["admin_action"] = "del"
    return WAITING_FOR_USER_ID


async def handle_user_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ID input for add/delete operations."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    action = context.user_data.get("admin_action")

    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字 ID。")
        return WAITING_FOR_USER_ID

    keyboard = [[InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if action == "add":
        if add_to_whitelist(target_id):
            user_info = get_user_info(target_id)
            if user_info:
                name = user_info.get("first_name") or "用户"
                await update.message.reply_text(
                    f"✅ 已添加 <b>{name}</b> (<code>{target_id}</code>) 到白名单。",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    f"✅ 已添加 <code>{target_id}</code> 到白名单。\n（该用户尚未注册）",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            logger.info(f"Admin added {target_id} to whitelist")
        else:
            await update.message.reply_text("❌ 添加失败，请检查日志。", reply_markup=reply_markup)

    elif action == "del":
        if remove_from_whitelist(target_id):
            await update.message.reply_text(
                f"🗑️ 已从白名单移除 <code>{target_id}</code>。",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            logger.info(f"Admin removed {target_id} from whitelist")
        else:
            await update.message.reply_text("⚠️ 该用户不在白名单中。", reply_markup=reply_markup)

    context.user_data.pop("admin_action", None)
    return ConversationHandler.END


async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel admin action and return to panel."""
    context.user_data.pop("admin_action", None)
    await admin_panel(update, context)
    return ConversationHandler.END


# ============ Legacy Command Handlers (kept for compatibility) ============

async def wl_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List whitelisted users (command version)."""
    if not is_admin(update.effective_user.id):
        return

    whitelist = get_whitelist()
    if not whitelist:
        await update.message.reply_text("📋 白名单为空。")
        return

    text = f"📋 <b>白名单用户 ({len(whitelist)} 人)</b>\n\n"
    for uid in whitelist:
        user_info = get_user_info(uid)
        if user_info:
            name = user_info.get("first_name") or "未知"
            username = user_info.get("username") or "无"
            text += f"• {name} | @{username} | <code>{uid}</code>\n"
        else:
            text += f"• <code>{uid}</code> (未注册)\n"

    await update.message.reply_text(text, parse_mode='HTML')


async def wl_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add user to whitelist (command version)."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法: /wl_add <用户ID>")
        return

    try:
        target_id = int(context.args[0])
        if add_to_whitelist(target_id):
            await update.message.reply_text(f"✅ 已添加 <code>{target_id}</code> 到白名单。", parse_mode='HTML')
            logger.info(f"Admin added {target_id} to whitelist")
        else:
            await update.message.reply_text("❌ 添加失败。")
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字。")


async def wl_del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove user from whitelist (command version)."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法: /wl_del <用户ID>")
        return

    try:
        target_id = int(context.args[0])
        if remove_from_whitelist(target_id):
            await update.message.reply_text(f"🗑️ 已移除 <code>{target_id}</code>。", parse_mode='HTML')
            logger.info(f"Admin removed {target_id} from whitelist")
        else:
            await update.message.reply_text("⚠️ 用户不在白名单中。")
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字。")


# ============ Analytics (数据分析) ============

async def admin_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show analytics dashboard."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return
    
    keyboard = [
        [
            InlineKeyboardButton("今日", callback_data="analytics_1"),
            InlineKeyboardButton("7天", callback_data="analytics_7"),
            InlineKeyboardButton("30天", callback_data="analytics_30"),
        ],
        [InlineKeyboardButton("« 返回控制台", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📊 <b>数据分析</b>\n"
        f"{'─' * 24}\n\n"
        "选择统计周期：",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def show_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show analytics for selected period."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return
    
    # 解析天数
    days = int(query.data.replace("analytics_", ""))
    period_name = {1: "今日", 7: "近7天", 30: "近30天"}.get(days, f"近{days}天")
    
    # 获取汇总数据
    summary = get_events_summary(days)
    users = get_users()
    
    # 构建报表文本
    lines = []
    lines.append(f"📊 <b>数据分析 - {period_name}</b>")
    lines.append(f"{'─' * 24}")
    lines.append("")
    
    # 概览
    lines.append("<b>📈 概览</b>")
    lines.append(f"• 总事件数: {summary['total_events']}")
    lines.append(f"  <i>统计周期内所有用户操作的总次数</i>")
    lines.append(f"• 活跃用户: {summary['active_users']}/{len(users)}")
    lines.append(f"  <i>有过任意操作的注册用户 / 总注册用户</i>")
    if summary['active_users'] > 0:
        avg = summary['total_events'] / summary['active_users']
        lines.append(f"• 人均事件: {avg:.1f}")
        lines.append(f"  <i>平均每个活跃用户的操作次数</i>")
        # 计算活跃率
        if len(users) > 0:
            active_rate = summary['active_users'] / len(users) * 100
            lines.append(f"• 活跃率: {active_rate:.0f}%")
            lines.append(f"  <i>活跃用户占总用户的比例</i>")
    lines.append("")
    
    # 事件分布
    if summary['event_counts']:
        lines.append("<b>📋 事件分布</b>")
        lines.append("<i>各类用户操作的次数统计</i>")
        # 事件名称和说明
        event_info = {
            "session_start": ("会话", "用户每天首次发送/start"),
            "item_click": ("查看原文", "用户点击查看原文按钮"),
            "feedback_positive": ("👍正面", "简报整体反馈有帮助"),
            "feedback_negative": ("👎负面", "简报整体反馈没帮助"),
            "item_like": ("单条👍", "对单条内容点赞"),
            "item_dislike": ("单条👎", "对单条内容不感兴趣"),
            "settings_changed": ("设置变更", "用户修改了设置"),
            "source_added": ("添加源", "用户添加了信息源"),
            "source_removed": ("删除源", "用户删除了信息源"),
        }
        for event_type, count in sorted(summary['event_counts'].items(), key=lambda x: -x[1]):
            info = event_info.get(event_type, (event_type, ""))
            lines.append(f"• {info[0]}: {count}")
        lines.append("")
    
    # 反馈分析
    positive = summary['event_counts'].get('feedback_positive', 0)
    negative = summary['event_counts'].get('feedback_negative', 0)
    item_click = summary['event_counts'].get('item_click', 0)
    item_dislike = summary['event_counts'].get('item_dislike', 0)
    
    total_feedback = positive + negative
    total_item = item_click + item_dislike
    
    if total_feedback > 0 or total_item > 0:
        lines.append("<b>💬 反馈分析</b>")
        if total_feedback > 0:
            rate = positive / total_feedback * 100
            lines.append(f"• 整体满意度: {rate:.0f}% ({positive}👍/{negative}👎)")
            lines.append(f"  <i>简报末尾\"有帮助\"的占比</i>")
        
        # 负面反馈原因分布
        if negative > 0:
            reason_stats = get_feedback_reason_stats(days)
            if reason_stats:
                lines.append("• 负面反馈原因:")
                for reason, count in sorted(reason_stats.items(), key=lambda x: -x[1]):
                    lines.append(f"  - {reason}: {count}次")
        
        if total_item > 0:
            # 点击查看原文视为正向信号
            rate = item_click / total_item * 100
            lines.append(f"• 内容吸引力: {rate:.0f}% ({item_click}点击/{item_dislike}不感兴趣)")
            lines.append(f"  <i>用户主动查看原文的占比</i>")
        lines.append("")
    
    # 活跃用户 Top 5
    if summary['top_users']:
        lines.append("<b>🏆 活跃用户 Top 5</b>")
        lines.append("<i>按操作次数排名</i>")
        user_map = {str(u.get("telegram_id")): u for u in users}
        for i, (uid, count) in enumerate(summary['top_users'][:5], 1):
            user_info = user_map.get(uid, {})
            name = user_info.get("first_name", "未知")
            lines.append(f"{i}. {name}: {count}次")
        lines.append("")
    
    # 不活跃预警
    inactive_count = 0
    for user in users:
        last_active = user.get("last_active") or user.get("created")
        if last_active:
            try:
                last_time = datetime.fromisoformat(last_active.replace("Z", "+00:00").replace("+00:00", ""))
                days_inactive = (datetime.now() - last_time).days
                if days_inactive >= 3:
                    inactive_count += 1
            except:
                pass
    
    if inactive_count > 0:
        lines.append(f"⚠️ <b>{inactive_count} 位用户超过3天未活跃</b>")
        lines.append(f"  <i>超过3天没有任何操作的用户</i>")
    else:
        lines.append("✅ 所有用户近3天内都有活动")
    
    keyboard = [
        [
            InlineKeyboardButton("今日", callback_data="analytics_1"),
            InlineKeyboardButton("7天", callback_data="analytics_7"),
            InlineKeyboardButton("30天", callback_data="analytics_30"),
        ],
        [InlineKeyboardButton("📋 详细报表", callback_data="analytics_detail")],
        [InlineKeyboardButton("« 返回控制台", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def show_analytics_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed analytics with actionable insights."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return
    
    summary = get_events_summary(7)
    users = get_users()
    
    lines = []
    lines.append("📋 <b>详细报表 & 运营建议</b>")
    lines.append(f"{'─' * 24}")
    lines.append("")
    
    # 计算关键指标
    positive = summary['event_counts'].get('feedback_positive', 0)
    negative = summary['event_counts'].get('feedback_negative', 0)
    item_like = summary['event_counts'].get('item_like', 0)
    item_dislike = summary['event_counts'].get('item_dislike', 0)
    source_added = summary['event_counts'].get('source_added', 0)
    source_removed = summary['event_counts'].get('source_removed', 0)
    settings_changed = summary['event_counts'].get('settings_changed', 0)
    
    total_feedback = positive + negative
    total_item = item_like + item_dislike
    
    # 运营建议
    lines.append("<b>💡 运营洞察</b>")
    lines.append("")
    
    # 1. 满意度分析
    if total_feedback > 0:
        rate = positive / total_feedback * 100
        if rate >= 80:
            lines.append(f"✅ 整体满意度 {rate:.0f}%，表现优秀")
        elif rate >= 60:
            lines.append(f"⚠️ 整体满意度 {rate:.0f}%，需关注负面反馈原因")
        else:
            lines.append(f"❌ 整体满意度仅 {rate:.0f}%，建议：")
            lines.append("  • 检查内容筛选质量")
            lines.append("  • 分析负面反馈具体原因")
    else:
        lines.append("📭 暂无整体反馈数据")
    lines.append("")
    
    # 2. 内容质量分析
    if total_item > 0:
        rate = item_like / total_item * 100
        if rate >= 70:
            lines.append(f"✅ 内容点赞率 {rate:.0f}%，筛选算法有效")
        else:
            lines.append(f"⚠️ 内容点赞率 {rate:.0f}%，建议：")
            lines.append("  • 优化 prompt 筛选逻辑")
            lines.append("  • 收集用户 dislike 原因")
    lines.append("")
    
    # 3. 信息源变化
    if source_added or source_removed:
        lines.append("<b>📡 信息源变化</b>")
        lines.append(f"• 新增: {source_added}  删除: {source_removed}")
        if source_removed > source_added:
            lines.append("⚠️ 删除多于新增，需关注信息源质量")
        lines.append("")
    
    # 4. 设置变更
    if settings_changed > 0:
        lines.append(f"<b>⚙️ 偏好设置</b>")
        lines.append(f"• {settings_changed} 次偏好变更")
        lines.append("提示: 频繁变更可能说明初始匹配不准")
        lines.append("")
    
    # 5. 用户活跃度建议
    inactive_users = []
    for user in users:
        last_active = user.get("last_active") or user.get("created")
        if last_active:
            try:
                last_time = datetime.fromisoformat(last_active.replace("Z", "+00:00").replace("+00:00", ""))
                days_inactive = (datetime.now() - last_time).days
                if days_inactive >= 3:
                    inactive_users.append({
                        "name": user.get("first_name", "未知"),
                        "username": user.get("username"),
                        "days": days_inactive,
                    })
            except:
                pass
    
    if inactive_users:
        inactive_users.sort(key=lambda x: -x["days"])
        lines.append(f"<b>⚠️ 流失预警 ({len(inactive_users)}人)</b>")
        for u in inactive_users[:5]:
            username = f"@{u['username']}" if u['username'] else ""
            lines.append(f"• {u['name']} {username} - {u['days']}天未活跃")
        if len(inactive_users) > 5:
            lines.append(f"  ... 还有 {len(inactive_users)-5} 人")
        lines.append("")
        lines.append("建议: 主动联系了解原因，或推送召回消息")
    
    keyboard = [
        [InlineKeyboardButton("« 返回分析", callback_data="admin_analytics")],
        [InlineKeyboardButton("« 返回控制台", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


# ============ T4: Source Health Dashboard ============

async def source_health_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show source health dashboard for admins."""
    query = update.callback_query
    await query.answer()
    
    from config import FEATURE_SOURCE_HEALTH
    if not FEATURE_SOURCE_HEALTH:
        await query.edit_message_text(
            "⚠️ 信息源健康监控功能未启用。\n\n"
            "设置 FEATURE_SOURCE_HEALTH=true 启用。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« 返回", callback_data="admin_panel")]
            ])
        )
        return
    
    from services.source_health_monitor import get_health_summary
    
    summary = get_health_summary()
    
    # Format dashboard
    status_line = (
        f"✅ 正常: {summary['ok']}  "
        f"⚠️ 降级: {summary['degraded']}  "
        f"❌ 失败: {summary['failed']}"
    )
    
    lines = [
        "📡 信息源健康看板",
        "─" * 24,
        "",
        status_line,
        f"总计: {summary['total']} 个源",
        "",
    ]
    
    # Show source details (max 15)
    for src in summary["sources"][:15]:
        status_emoji = {
            "ok": "✅", "repaired": "🔧", "degraded": "⚠️",
            "warning": "⚠️", "failed": "❌", "permanently_failed": "💀",
        }.get(src["status"], "❓")
        
        name = src["name"][:20]
        lines.append(f"{status_emoji} {name} ({src['success_rate']})")
    
    if summary["total"] > 15:
        lines.append(f"\n... 还有 {summary['total'] - 15} 个源")
    
    keyboard = [
        [InlineKeyboardButton("🔄 刷新", callback_data="admin_source_health")],
        [InlineKeyboardButton("➕ 批量添加", callback_data="admin_bulk_add_sources")],
        [InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")],
    ]
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_bulk_add_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show bulk add sources prompt. Returns WAITING_FOR_BULK_SOURCES state."""
    from utils.conv_manager import activate_conv
    activate_conv(context, "admin")

    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ 批量添加信息源\n"
        "─" * 24 + "\n\n"
        "请发送信息源列表，每行一个，格式：\n"
        "名称|URL\n\n"
        "示例：\n"
        "CoinDesk|https://www.coindesk.com/arc/outboundfeeds/rss/\n"
        "The Block|https://www.theblock.co/rss.xml\n\n"
        "发送 /cancel 取消",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« 返回", callback_data="admin_source_health")]
        ])
    )
    return WAITING_FOR_BULK_SOURCES


async def handle_bulk_sources_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process bulk source addition input. Called within admin ConversationHandler."""
    text = update.message.text.strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    added = []
    failed = []
    
    for line in lines:
        if "|" not in line:
            failed.append(f"{line[:30]} (格式错误)")
            continue
        
        parts = line.split("|", 1)
        name = parts[0].strip()
        url = parts[1].strip()
        
        if not url.startswith("http"):
            failed.append(f"{name} (URL无效)")
            continue
        
        # Add to default sources config and persist
        try:
            from services.rss_fetcher import add_source
            if add_source("websites", name, url):
                added.append(f"✅ {name}")
            else:
                failed.append(f"{name} (保存失败)")
        except Exception as e:
            failed.append(f"{name} ({str(e)[:30]})")
    
    result = f"📊 批量添加结果\n{'─' * 24}\n\n"
    if added:
        result += f"成功: {len(added)} 个\n" + "\n".join(added) + "\n\n"
    if failed:
        result += f"失败: {len(failed)} 个\n" + "\n".join(failed) + "\n"
    
    keyboard = [
        [InlineKeyboardButton("📡 查看看板", callback_data="admin_source_health")],
        [InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")],
    ]
    
    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


# ============ Group Management Dashboard (B2) ============

async def admin_group_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group management dashboard for admin."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("No permission", show_alert=True)
        return
    
    from config import FEATURE_GROUP_CHAT
    if not FEATURE_GROUP_CHAT:
        await query.edit_message_text(
            "⚠️ 群聊功能未启用。\n\n设置 FEATURE_GROUP_CHAT=true 启用。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« 返回", callback_data="admin_panel")]
            ])
        )
        return
    
    from handlers.group import get_all_group_configs
    from config import GROUP_CONFIGS_DIR
    import os
    
    # Get ALL configs (not just enabled ones)
    all_configs = []
    if os.path.exists(GROUP_CONFIGS_DIR):
        for filename in os.listdir(GROUP_CONFIGS_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(GROUP_CONFIGS_DIR, filename)
                try:
                    import json as _json
                    with open(filepath, "r", encoding="utf-8") as f:
                        all_configs.append(_json.load(f))
                except Exception:
                    continue
    
    if not all_configs:
        text = (
            "📢 群组管理\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "暂无已配置的群组。\n\n"
            "在群组中发送 /setup 开始配置。"
        )
        keyboard = [[InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")]]
    else:
        lines = ["📢 群组管理", "━━━━━━━━━━━━━━━━━━━━━", ""]
        keyboard = []
        for cfg in all_configs:
            gid = cfg.get("group_id", "?")
            title = cfg.get("group_title", "Unknown")
            enabled = cfg.get("enabled", True)
            push_hour = cfg.get("push_hour", 9)
            last_push = cfg.get("last_push_date", "从未推送")
            
            status = "✅" if enabled else "❌"
            toggle_label = "禁用" if enabled else "启用"
            
            lines.append(f"{status} {title}")
            lines.append(f"  推送: {push_hour}:00 | 上次: {last_push}")
            lines.append(f"  ID: {gid}")
            lines.append("")
            
            keyboard.append([InlineKeyboardButton(
                f"{'🔴 禁用' if enabled else '🟢 启用'} {title[:15]}",
                callback_data=f"admin_group_toggle_{gid}"
            )])
        
        text = "\n".join(lines)
        keyboard.append([InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_group_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle group enabled/disabled status."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    group_id = query.data.replace("admin_group_toggle_", "")
    
    from handlers.group import load_group_config, save_group_config
    config = load_group_config(group_id)
    if config:
        config["enabled"] = not config.get("enabled", True)
        save_group_config(group_id, config)
        status = "启用" if config["enabled"] else "禁用"
        await query.answer(f"已{status}群组 {config.get('group_title', group_id)}", show_alert=True)
    
    # Refresh dashboard
    await admin_group_manage(update, context)


# ============ Admin Redeem Code Generation (C1) ============

async def admin_gen_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a redemption code from admin panel."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    from handlers.payment import generate_redeem_code
    code = generate_redeem_code(days=30, created_by=str(query.from_user.id))
    
    await query.edit_message_text(
        f"🎫 兑换码已生成\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Code: <code>{code}</code>\n"
        f"⏳ 有效期: 30 天\n\n"
        f"将此码发给付费用户，用户在 Bot 中选择\n"
        f"「🎫 兑换码」输入即可升级 Pro。\n\n"
        f"💡 使用 /gencode [天数] 可自定义有效期",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 再生成一个", callback_data="admin_gen_code")],
            [InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")],
        ])
    )


# ============ Handler Registration ============

def get_admin_handlers():
    """Return all admin-related handlers."""
    # ConversationHandler for add/delete flow
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_wl_add_callback, pattern="^admin_wl_add$"),
            CallbackQueryHandler(admin_wl_del_callback, pattern="^admin_wl_del$"),
            CallbackQueryHandler(admin_bulk_add_sources, pattern="^admin_bulk_add_sources$"),
        ],
        states={
            WAITING_FOR_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_id_input),
            ],
            WAITING_FOR_BULK_SOURCES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_sources_input),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_admin_action, pattern="^admin_panel$"),
            CallbackQueryHandler(source_health_dashboard, pattern="^admin_source_health$"),
        ],
        per_message=False,
    )

    return [
        # Button-based handlers
        CallbackQueryHandler(admin_panel, pattern="^admin_panel$"),
        CallbackQueryHandler(admin_wl_toggle_callback, pattern="^admin_wl_toggle$"),
        CallbackQueryHandler(admin_wl_list_callback, pattern="^admin_wl_list$"),
        # Analytics handlers (数据分析)
        CallbackQueryHandler(admin_analytics, pattern="^admin_analytics$"),
        CallbackQueryHandler(show_analytics, pattern="^analytics_[0-9]+$"),
        CallbackQueryHandler(show_analytics_detail, pattern="^analytics_detail$"),
        # Source health handlers (T4)
        CallbackQueryHandler(source_health_dashboard, pattern="^admin_source_health$"),
        # Group management handler
        CallbackQueryHandler(admin_group_manage, pattern="^admin_group_manage$"),
        CallbackQueryHandler(admin_group_toggle, pattern="^admin_group_toggle_"),
        # Redeem code generation handler
        CallbackQueryHandler(admin_gen_code_callback, pattern="^admin_gen_code$"),
        # Admin ConversationHandler (whitelist add/del + bulk source add)
        admin_conv,
        # Command handlers (legacy, still work)
        CommandHandler("admin", admin_panel),
        CommandHandler("wl_list", wl_list_command),
        CommandHandler("wl_add", wl_add_command),
        CommandHandler("wl_del", wl_del_command),
    ]
