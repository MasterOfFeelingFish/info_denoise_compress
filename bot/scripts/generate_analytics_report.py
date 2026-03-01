#!/usr/bin/env python3
"""
用户行为分析报表生成脚本

Usage:
    python scripts/generate_analytics_report.py [days]
    
    days: 统计最近多少天的数据，默认 7 天

Output:
    生成 Markdown 格式的报表到 data/analytics/ 目录
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# 添加父目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATA_DIR, EVENTS_DIR
from utils.json_storage import get_events_summary, get_users


def generate_report(days: int = 7) -> str:
    """生成 Markdown 格式的分析报表"""
    
    summary = get_events_summary(days)
    users = get_users()
    
    # 构建用户 ID 到信息的映射
    user_map = {}
    for user in users:
        uid = user.get("telegram_id")
        user_map[uid] = {
            "name": user.get("first_name", "未知"),
            "username": user.get("username"),
            "user_id": user.get("id"),
        }
    
    # 生成报表
    lines = []
    lines.append(f"# 用户行为分析报表")
    lines.append(f"")
    lines.append(f"> 统计周期：最近 {days} 天")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    
    # 概览
    lines.append(f"## 📊 概览")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总事件数 | {summary['total_events']} |")
    lines.append(f"| 活跃用户数 | {summary['active_users']} |")
    lines.append(f"| 注册用户总数 | {len(users)} |")
    if summary['active_users'] > 0:
        avg_events = summary['total_events'] / summary['active_users']
        lines.append(f"| 人均事件数 | {avg_events:.1f} |")
    lines.append(f"")
    
    # 按事件类型统计
    lines.append(f"## 📈 事件类型分布")
    lines.append(f"")
    lines.append(f"| 事件类型 | 次数 | 说明 |")
    lines.append(f"|----------|------|------|")
    
    event_descriptions = {
        "session_start": "会话开始",
        "feedback_positive": "正面反馈",
        "feedback_negative": "负面反馈",
        "item_like": "单条点赞",
        "item_dislike": "单条踩",
        "settings_changed": "设置变更",
        "source_added": "添加信息源",
        "source_removed": "删除信息源",
    }
    
    for event_type, count in sorted(summary['event_counts'].items(), key=lambda x: -x[1]):
        desc = event_descriptions.get(event_type, event_type)
        lines.append(f"| {event_type} | {count} | {desc} |")
    lines.append(f"")
    
    # 每日趋势
    if summary['daily_counts']:
        lines.append(f"## 📅 每日事件趋势")
        lines.append(f"")
        lines.append(f"| 日期 | 事件数 |")
        lines.append(f"|------|--------|")
        for date, count in sorted(summary['daily_counts'].items()):
            lines.append(f"| {date} | {count} |")
        lines.append(f"")
    
    # 活跃用户排行
    if summary['top_users']:
        lines.append(f"## 🏆 活跃用户 Top 10")
        lines.append(f"")
        lines.append(f"| 排名 | 用户 | 用户名 | 事件数 |")
        lines.append(f"|------|------|--------|--------|")
        for i, (uid, count) in enumerate(summary['top_users'], 1):
            user_info = user_map.get(uid, {})
            name = user_info.get("name", "未知")
            username = user_info.get("username")
            username_str = f"@{username}" if username else "-"
            lines.append(f"| {i} | {name} | {username_str} | {count} |")
        lines.append(f"")
    
    # 反馈分析
    lines.append(f"## 💬 反馈分析")
    lines.append(f"")
    positive = summary['event_counts'].get('feedback_positive', 0)
    negative = summary['event_counts'].get('feedback_negative', 0)
    item_like = summary['event_counts'].get('item_like', 0)
    item_dislike = summary['event_counts'].get('item_dislike', 0)
    
    total_feedback = positive + negative
    if total_feedback > 0:
        positive_rate = positive / total_feedback * 100
        lines.append(f"- 整体反馈：{positive} 正面 / {negative} 负面 （正面率 {positive_rate:.1f}%）")
    else:
        lines.append(f"- 整体反馈：暂无数据")
    
    total_item = item_like + item_dislike
    if total_item > 0:
        like_rate = item_like / total_item * 100
        lines.append(f"- 单条反馈：{item_like} 点赞 / {item_dislike} 踩 （点赞率 {like_rate:.1f}%）")
    else:
        lines.append(f"- 单条反馈：暂无数据")
    lines.append(f"")
    
    # 信息源变更
    source_added = summary['event_counts'].get('source_added', 0)
    source_removed = summary['event_counts'].get('source_removed', 0)
    if source_added or source_removed:
        lines.append(f"## 📡 信息源变更")
        lines.append(f"")
        lines.append(f"- 新增信息源：{source_added} 次")
        lines.append(f"- 删除信息源：{source_removed} 次")
        lines.append(f"")
    
    # 不活跃用户预警
    lines.append(f"## ⚠️ 用户活跃度预警")
    lines.append(f"")
    
    # 计算每个用户的最后活跃时间
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
        lines.append(f"以下用户已超过 3 天未活跃：")
        lines.append(f"")
        lines.append(f"| 用户 | 用户名 | 不活跃天数 |")
        lines.append(f"|------|--------|------------|")
        for u in inactive_users[:20]:
            username_str = f"@{u['username']}" if u['username'] else "-"
            lines.append(f"| {u['name']} | {username_str} | {u['days']} 天 |")
        lines.append(f"")
    else:
        lines.append(f"所有用户近 3 天内都有活动 ✅")
        lines.append(f"")
    
    return "\n".join(lines)


def main():
    # 解析参数
    days = 7
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"无效的天数参数: {sys.argv[1]}")
            sys.exit(1)
    
    # 生成报表
    report = generate_report(days)
    
    # 保存到文件
    analytics_dir = os.path.join(DATA_DIR, "analytics")
    os.makedirs(analytics_dir, exist_ok=True)
    
    filename = f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(analytics_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"报表已生成: {filepath}")
    print(f"")
    print(report)


if __name__ == "__main__":
    main()
