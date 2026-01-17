"""
任务调度器 - 管理定时推送
"""
import asyncio
from datetime import datetime, time
from typing import Optional, List, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.digest_generator import DigestGenerator
from core.custom_processes.web3digest.core.crawler_scheduler import CrawlerScheduler
from core.custom_processes.web3digest.core.feedback_analyzer import FeedbackAnalyzer

logger = setup_logger(__name__)


class DigestScheduler:
    """简报调度器"""

    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
        self.digest_generator = DigestGenerator()
        self.crawler_scheduler = CrawlerScheduler()
        self.feedback_analyzer = FeedbackAnalyzer()
        self._running = False

    async def start(self):
        """启动调度器"""
        if self._running:
            return

        # 启动抓取调度器（每小时抓取一次）
        await self.crawler_scheduler.start()

        # 添加每分钟检查推送任务（支持用户自定义推送时间，精确到分钟）
        # 每分钟执行一次，检查哪些用户需要推送
        self.scheduler.add_job(
            func=self._check_and_push_digest,
            trigger=CronTrigger(second=0),  # 每分钟的第0秒执行
            id="minutely_digest_check",
            name="每分钟检查推送任务",
            replace_existing=True
        )

        # 添加每周反馈分析任务（每周一凌晨2点）
        self.scheduler.add_job(
            func=self._weekly_feedback_analysis_job,
            trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
            id="weekly_feedback_analysis",
            name="每周反馈分析",
            replace_existing=True
        )

        # 启动调度器
        self.scheduler.start()
        self._running = True

        logger.info("调度器已启动，每分钟检查用户推送时间并推送简报（支持分钟级精度）")

    async def stop(self):
        """停止调度器"""
        if not self._running:
            return

        # 停止抓取调度器
        await self.crawler_scheduler.stop()

        self.scheduler.shutdown()
        self._running = False
        logger.info("调度器已停止")

    async def _check_and_push_digest(self):
        """每小时检查并推送简报（支持用户自定义推送时间）"""
        from datetime import datetime
        current_time = datetime.now()
        current_hour = current_time.hour
        current_minute = current_time.minute

        logger.info(f"开始检查推送任务 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

        success_count = 0
        failed_count = 0
        skipped_count = 0
        checked_count = 0

        try:
            # 获取所有活跃用户
            users = await self.bot.user_manager.get_active_users()

            if not users:
                logger.info("没有活跃用户，任务结束")
                return

            logger.info(f"找到 {len(users)} 个活跃用户，开始检查推送时间")

            # 为每个用户检查推送时间并推送
            for user in users:
                try:
                    user_id = int(user["id"])
                    checked_count += 1

                    # 获取用户推送时间
                    user_push_time = await self.bot.profile_manager.get_push_time(user_id)
                    push_hour, push_minute = map(int, user_push_time.split(":"))

                    # 检查是否到了该用户的推送时间（精确到分钟）
                    # 调度器每分钟执行一次，检查小时和分钟是否都匹配
                    if current_hour != push_hour or current_minute != push_minute:
                        # 不是这个用户的推送时间，跳过
                        continue

                    logger.info(f"用户 {user_id} 的推送时间到了 ({user_push_time})，开始推送")

                    # 检查用户是否有画像
                    profile = await self.bot.profile_manager.get_profile(user_id)
                    if not profile:
                        logger.warning(f"用户 {user_id} 没有画像，跳过")
                        skipped_count += 1
                        continue

                    # 生成简报
                    digest = await self.digest_generator.generate_digest(user_id, profile)

                    if digest:
                        # 推送简报（带重试）
                        success = await self._send_digest_with_retry(user_id, digest, max_retries=3)
                        if success:
                            logger.info(f"✅ 已为用户 {user_id} 推送简报（推送时间：{user_push_time}）")
                            success_count += 1
                        else:
                            logger.error(f"❌ 用户 {user_id} 推送失败（已重试）")
                            failed_count += 1
                    else:
                        logger.warning(f"用户 {user_id} 简报生成失败（无符合条件的信息）")
                        skipped_count += 1

                    # 避免频繁请求
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"处理用户 {user['id']} 时出错: {e}", exc_info=True)
                    failed_count += 1
                    continue

            if checked_count > 0:
                logger.info(
                    f"推送检查完成 - "
                    f"检查: {checked_count}, 成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count}"
                )

        except Exception as e:
            logger.error(f"推送检查任务失败: {e}", exc_info=True)

    async def _daily_digest_job(self):
        """每日简报任务（保留用于兼容性，实际使用 _check_and_push_digest）"""
        await self._check_and_push_digest()

    async def _send_digest(self, user_id: int, digest_data):
        """
        发送简报给用户

        Args:
            user_id: 用户ID
            digest_data: 可以是字符串（旧格式）或字典（新格式）
                字典格式: {"text": "简报文本", "top_items": [...], "stats": {...}}
        """
        try:
            # 兼容旧格式
            if isinstance(digest_data, str):
                digest_text = digest_data
                top_items = []
            else:
                digest_text = digest_data.get("text", "")
                top_items = digest_data.get("top_items", [])

            logger.info(f"开始发送简报给用户 {user_id}，长度: {len(digest_text)}，Top条目: {len(top_items)}")

            # 1. 先发送简报概览（带整体反馈按钮）
            messages = self._split_message(digest_text, max_length=4000)

            for i, msg in enumerate(messages):
                try:
                    if i == len(messages) - 1:
                        await self._send_with_feedback(user_id, msg)
                    else:
                        await self.bot.application.bot.send_message(
                            chat_id=user_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                except Exception as parse_err:
                    logger.warning(f"Markdown 解析失败，尝试纯文本: {parse_err}")
                    if i == len(messages) - 1:
                        await self._send_with_feedback(user_id, msg, use_markdown=False)
                    else:
                        await self.bot.application.bot.send_message(chat_id=user_id, text=msg)

                if i < len(messages) - 1:
                    await asyncio.sleep(0.3)

            # 2. 发送 Top 3 信息的单独卡片（带单条反馈按钮）
            if top_items:
                await asyncio.sleep(0.5)
                await self._send_item_cards(user_id, top_items)

            # 3. 发送质量报告卡片（如果有质量指标）
            if isinstance(digest_data, dict):
                stats = digest_data.get("stats", {})
                digest_quality = stats.get("digest_quality")
                if digest_quality:
                    await asyncio.sleep(0.5)
                    await self._send_quality_report(user_id, digest_quality)

            logger.info(f"✅ 简报已成功发送给用户 {user_id}")

        except Exception as e:
            logger.error(f"发送简报失败 {user_id}: {e}", exc_info=True)
            raise

    async def _send_item_cards(self, user_id: int, items: List[Dict]):
        """发送单条信息卡片（带反馈按钮）"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        import re

        def clean_html(text: str) -> str:
            """清理 HTML 标签"""
            if not text:
                return ""
            # 移除 HTML 标签
            text = re.sub(r'<[^>]+>', '', text)
            # 移除多余空白
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        def safe_url(url: str) -> str:
            """处理 URL，确保可以在 Markdown 中使用"""
            if not url:
                return ""
            # 使用 urllib.parse 进行更安全的 URL 编码
            try:
                from urllib.parse import quote, urlparse, urlunparse
                parsed = urlparse(url)
                # 只编码路径和查询参数
                safe_parsed = parsed._replace(
                    path=quote(parsed.path, safe='/%'),
                    query=quote(parsed.query, safe='=&?/%')
                )
                return urlunparse(safe_parsed)
            except:
                # 如果编码失败，至少处理最常见的特殊字符
                return url.replace('(', '%28').replace(')', '%29').replace('[', '%5B').replace(']', '%5D')

        # 发送分隔提示
        await self.bot.application.bot.send_message(
            chat_id=user_id,
            text="📋 *今日必看详情* (点击反馈帮助我们优化)",
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.3)

        emoji_list = ["1️⃣", "2️⃣", "3️⃣"]

        for i, item in enumerate(items[:3]):
            item_id = item.get("id", f"item_{i}")
            title = clean_html(item.get("title", ""))[:60]
            summary = clean_html(item.get("summary", ""))[:150]
            source = item.get("source", "未知")
            url = safe_url(item.get("url", ""))

            # 获取评分数据
            scores = item.get("scores", {})
            recommendation_reason = item.get("recommendation_reason", "")

            # 构建消息
            emoji = emoji_list[i] if i < len(emoji_list) else "📌"
            card_text = f"{emoji} *{self._escape_md(title)}*\n\n"
            if summary:
                card_text += f"{self._escape_md(summary)}\n\n"

            # 添加评分信息(如果存在)
            if scores:
                relevance_score = scores.get("relevance_score", 0)
                importance_score = scores.get("importance_score", 0)
                freshness_score = scores.get("freshness_score", 0)
                total_score = scores.get("total_score", 0)
                confidence = scores.get("confidence", 0.5)

                # 生成置信度进度条
                confidence_bar = '█' * int(confidence * 10) + '░' * (10 - int(confidence * 10))

                card_text += f"📊 *评分详情*:\n"
                card_text += f"• 置信度: {confidence_bar} {int(confidence*100)}%\n"
                card_text += f"• 相关度: {'⭐' * int(relevance_score)} {relevance_score}/5\n"
                card_text += f"• 重要性: {'⭐' * int(importance_score)} {importance_score}/3\n"
                card_text += f"• 新鲜度: {'⭐' * int(freshness_score)} {freshness_score}/2\n"
                card_text += f"• 总分: {total_score}/10\n\n"

                # 添加推荐理由
                if recommendation_reason:
                    card_text += f"💡 *推荐理由*: {self._escape_md(recommendation_reason[:80])}\n\n"

            card_text += f"📍 来源: {source}"

            # 单条反馈按钮 + 查看原文按钮
            buttons = [
                InlineKeyboardButton("⭐ 很有用", callback_data=f"item_like_{item_id}_{source[:10]}"),
                InlineKeyboardButton("👎 不感兴趣", callback_data=f"item_dislike_{item_id}_{source[:10]}")
            ]

            keyboard = [buttons]

            # 添加查看原文按钮（使用 URL 按钮，更可靠）
            if url:
                keyboard.append([InlineKeyboardButton("🔗 查看原文", url=url)])

            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=card_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception as e:
                # Markdown 失败则纯文本
                logger.warning(f"发送信息卡片失败: {e}")
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=f"{emoji} {title}\n\n{summary}\n\n来源: {source}",
                    reply_markup=reply_markup
                )

            await asyncio.sleep(0.3)

    async def _send_quality_report(self, user_id: int, quality: Dict):
        """发送简报质量报告卡片"""

        # 生成进度条
        def make_progress_bar(value: float, length: int = 10) -> str:
            filled = int(value * length)
            return '█' * filled + '░' * (length - filled)

        # 构建质量报告消息
        quality_text = f"""📊 *本次简报质量报告*

*整体评分*: {quality.get('overall_score', 0)}/10 {'⭐' * int(quality.get('overall_score', 0))}

*各维度评分*:
• 个性化程度: {make_progress_bar(quality.get('personalization_level', 0))} {int(quality.get('personalization_level', 0)*100)}%
• 内容多样性: {make_progress_bar(quality.get('diversity_score', 0))} {int(quality.get('diversity_score', 0)*100)}%
• 来源权威性: {make_progress_bar(quality.get('authority_score', 0))} {int(quality.get('authority_score', 0)*100)}%
• 信息新鲜度: {make_progress_bar(quality.get('freshness_level', 0))} {int(quality.get('freshness_level', 0)*100)}%

*兴趣覆盖*:
• 覆盖领域: {quality.get('coverage', {}).get('user_interests_covered', 0)}/{quality.get('coverage', {}).get('total_interests', 0)}
• 覆盖率: {int(quality.get('coverage', {}).get('coverage_rate', 0)*100)}%
"""

        # 添加覆盖的兴趣列表（确保数据一致性）
        coverage_data = quality.get('coverage', {})
        user_interests_covered = coverage_data.get('user_interests_covered', 0)
        covered_interests = coverage_data.get('covered_interests', [])
        
        # 只有在确实有覆盖的兴趣时才显示
        if user_interests_covered > 0 and covered_interests:
            quality_text += f"• 已覆盖: {', '.join(covered_interests[:3])}"
            if len(covered_interests) > 3:
                quality_text += f" 等{len(covered_interests)}个领域"
            quality_text += "\n"

        quality_text += f"""
*内容质量分布*:
• 🏆 高质量(≥8分): {quality.get('quality_distribution', {}).get('high_quality', 0)} 条
• 📝 中等质量(6-8分): {quality.get('quality_distribution', {}).get('medium_quality', 0)} 条
• 📄 待改进(<6分): {quality.get('quality_distribution', {}).get('low_quality', 0)} 条

━━━━━━━━━━━━━━━
💡 AI正在持续学习您的偏好,推荐会越来越精准!"""

        try:
            await self.bot.application.bot.send_message(
                chat_id=user_id,
                text=quality_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            # Markdown失败则纯文本
            logger.warning(f"发送质量报告失败: {e}")
            try:
                # 移除Markdown标记重新发送
                plain_text = quality_text.replace('*', '').replace('_', '')
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=plain_text
                )
            except Exception as e2:
                logger.error(f"发送质量报告纯文本也失败: {e2}")

    def _escape_md(self, text: str) -> str:
        """转义 Markdown 特殊字符"""
        if not text:
            return ""
        # 转义所有 Markdown 特殊字符
        text = text.replace('_', '\\_')
        text = text.replace('*', '\\*')
        text = text.replace('[', '\\[')
        text = text.replace(']', '\\]')
        text = text.replace('(', '\\(')
        text = text.replace(')', '\\)')
        text = text.replace('~', '\\~')
        text = text.replace('`', '\\`')
        text = text.replace('#', '\\#')
        text = text.replace('+', '\\+')
        text = text.replace('-', '\\-')
        text = text.replace('=', '\\=')
        text = text.replace('|', '\\|')
        text = text.replace('{', '\\{')
        text = text.replace('}', '\\}')
        text = text.replace('.', '\\.')
        text = text.replace('!', '\\!')
        return text

    async def _send_digest_with_retry(self, user_id: int, digest: str, max_retries: int = 3):
        """发送简报，带重试机制"""
        for attempt in range(max_retries):
            try:
                await self._send_digest(user_id, digest)
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 递增等待时间：2s, 4s, 6s
                    logger.warning(
                        f"用户 {user_id} 推送失败（尝试 {attempt + 1}/{max_retries}），"
                        f"{wait_time}秒后重试: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"用户 {user_id} 推送最终失败（已重试 {max_retries} 次）: {e}")
                    return False
        return False

    async def _send_with_feedback(self, user_id: int, message: str, use_markdown: bool = True):
        """发送带反馈按钮的消息"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        # 添加反馈按钮
        keyboard = [
            [
                InlineKeyboardButton("👍 有用", callback_data=f"feedback_positive_{datetime.now().strftime('%Y%m%d')}"),
                InlineKeyboardButton("👎 不太行", callback_data=f"feedback_negative_{datetime.now().strftime('%Y%m%d')}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.bot.application.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown" if use_markdown else None,
            reply_markup=reply_markup
        )

    def _split_message(self, text: str, max_length: int = 4000) -> list:
        """分割长消息，避免在 Markdown 实体中间分割"""
        if len(text) <= max_length:
            return [text]

        messages = []
        current_msg = ""
        
        # 定义需要避免分割的 Markdown 模式
        import re
        
        # 识别完整的 Markdown 实体
        # 例如：*text*, **text**, `text`, [text](url) 等
        md_patterns = [
            r'\*[^*]+\*',  # *斜体*
            r'\*\*[^*]+\*\*',  # **粗体**
            r'`[^`]+`',  # `代码`
            r'\[[^\]]+\]\([^)]+\)',  # [链接](url)
        ]
        
        lines = text.split("\n")
        i = 0
        n = len(lines)
        
        while i < n:
            line = lines[i]
            
            # 检查添加这行是否会超过长度限制
            if len(current_msg) + len(line) + 1 <= max_length:
                current_msg += line + "\n"
                i += 1
            else:
                # 如果当前行为空，直接跳过
                if not current_msg.strip():
                    current_msg = line + "\n"
                    i += 1
                    continue
                
                # 尝试在当前行找到合适的分割点
                if len(line) > max_length:
                    # 单行太长，需要分割
                    # 优先在句号、感叹号、问号后分割
                    split_points = ['。', '！', '？', '.', '!', '?', '\n']
                    best_pos = -1
                    
                    for point in split_points:
                        pos = line.rfind(point, 0, max_length - len(current_msg) - 1)
                        if pos > best_pos:
                            best_pos = pos
                    
                    if best_pos > 0:
                        # 在找到的点分割
                        current_msg += line[:best_pos + 1]
                        messages.append(current_msg.rstrip())
                        current_msg = line[best_pos + 1:] + "\n"
                        if current_msg.strip():
                            continue  # 继续处理剩余部分
                    else:
                        # 强制分割
                        messages.append(current_msg.rstrip())
                        current_msg = line + "\n"
                else:
                    # 保存当前消息
                    messages.append(current_msg.rstrip())
                    current_msg = line + "\n"
                    i += 1
        
        if current_msg.strip():
            messages.append(current_msg.rstrip())
        
        return messages

    async def trigger_manual_digest(self, user_id: int):
        """手动触发简报生成（用于测试）"""
        logger.info(f"用户 {user_id} 手动触发简报生成")

        try:
            # 获取用户画像
            profile = await self.bot.profile_manager.get_profile(user_id)
            if not profile:
                return {"success": False, "error": "请先使用 /start 完成偏好设置"}

            # 生成简报
            digest = await self.digest_generator.generate_digest(user_id, profile)

            if digest:
                await self._send_digest(user_id, digest)
                return {"success": True, "message": "简报已发送！"}
            else:
                return {"success": False, "error": "抱歉，今日暂无符合您偏好的信息"}

        except Exception as e:
            logger.error(f"手动生成简报失败: {e}", exc_info=True)
            return {"success": False, "error": f"生成失败：{str(e)}"}

    async def _safe_edit_message(self, status_msg, text: str):
        """安全地编辑消息，忽略内容相同的错误"""
        try:
            await status_msg.edit_text(text)
        except Exception as e:
            # 忽略 "Message is not modified" 错误
            if "Message is not modified" not in str(e):
                raise

    async def trigger_manual_digest_with_status(self, user_id: int, status_msg):
        """
        手动触发完整流程，带状态更新

        流程：抓取 → 筛选 → 生成 → 推送
        """
        logger.info(f"用户 {user_id} 手动触发完整流程")

        try:
            # 步骤 1: 抓取信息
            await self._safe_edit_message(status_msg, "🚀 开始完整流程测试...\n\n📥 步骤 1/4: 正在抓取信息...")

            from core.custom_processes.web3digest.core.crawler_scheduler import CrawlerScheduler
            from datetime import datetime, date
            import os
            import json
            
            crawler = CrawlerScheduler()
            # 使用用户自定义的信息源
            user_sources = await self.bot.source_manager.get_enabled_sources_for_crawl(user_id)
            
            # 在测试模式下，添加时间戳避免数据重复
            test_suffix = f"_test_{datetime.now().strftime('%H%M%S')}"
            logger.info(f"测试模式：使用后缀 {test_suffix}")
            crawl_result = await crawler.wiseflow_client.trigger_crawl(sources=user_sources, test_mode=True, test_suffix=test_suffix)

            articles_count = crawl_result.get("articles_count", 0)
            rss_sources = crawl_result.get("rss_sources", 0)

            if crawl_result.get("status") != 0:
                await self._safe_edit_message(status_msg, f"❌ 抓取失败\n\n错误：{crawl_result.get('warnings', [])}")
                return {"success": False, "error": f"抓取失败：{crawl_result.get('warnings', [])}"}

            logger.info(f"抓取完成：{articles_count} 条文章")

            # 步骤 2: 获取用户画像
            await self._safe_edit_message(status_msg,
                f"✅ 步骤 1/4 完成\n   抓取 {rss_sources} 个源，获取 {articles_count} 条内容\n\n🔍 步骤 2/4: 正在加载用户画像...")

            profile = await self.bot.profile_manager.get_profile(user_id)
            
            # 为测试用户创建默认画像，如果用户没有设置偏好
            if not profile:
                # 创建默认画像用于测试
                from core.custom_processes.web3digest.core.profile_manager import Profile
                profile = Profile(
                    user_id=user_id,
                    interests=["Web3", "区块链", "DeFi", "NFT", "Layer2"],
                    preferred_sources=["Cointelegraph", "Decrypt", "Vitalik Blog"],
                    language="zh",
                    timezone="Asia/Shanghai"
                )
            
            # 步骤 3: 生成简报
            await self._safe_edit_message(status_msg,
                f"✅ 步骤 2/4 完成\n   用户画像已加载\n\n📝 步骤 3/4: 正在生成简报...")
            
            # 获取用户最新的反馈数据，确保个性化
            # 注意：这里只是读取已有的分析结果，不触发新的分析
            from core.custom_processes.web3digest.core.feedback_analyzer import FeedbackAnalyzer
            feedback_analyzer = FeedbackAnalyzer()
            # 异步触发分析（如果需要），但不等待结果
            import asyncio
            asyncio.create_task(feedback_analyzer.analyze_if_threshold_reached(user_id))
            
            # 使用测试模式的数据文件
            from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient
            wiseflow_client = WiseFlowClient()
            test_file = f"{date.today().isoformat()}{test_suffix}.json"
            test_data = []
            
            try:
                test_file_path = wiseflow_client.data_dir / test_file
                if test_file_path.exists():
                    with open(test_file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        test_data = data.get("items", [])
            except Exception as e:
                logger.error(f"读取测试数据失败: {e}")
            
            if not test_data:
                logger.error("没有测试数据可用")
                await self._safe_edit_message(status_msg, "❌ 没有获取到测试数据")
                return {"success": False, "error": "没有测试数据"}
            
            # 生成简报时使用测试数据
            logger.info(f"使用测试数据生成简报，共 {len(test_data)} 条")
            digest = await self.digest_generator.generate_digest(user_id, profile, test_data=test_data)

            if not digest:
                # 这种情况应该很少见，因为 generate_digest 现在有完整的兜底逻辑
                logger.error(f"用户 {user_id} 简报生成失败（返回 None），这不应该发生")
                await self._safe_edit_message(status_msg,
                    "⚠️ 简报生成遇到问题\n\n"
                    "抱歉，在生成简报时遇到了技术问题。\n\n"
                    "💡 建议：\n"
                    "• 请稍后使用 /test 命令重新生成简报\n"
                    "• 如果问题持续，请联系管理员")
                return {"success": False, "error": "简报生成失败"}

            # 步骤 4: 推送简报
            profile_status = "已加载" if profile else "使用默认测试设置"
            await self._safe_edit_message(status_msg,
                f"✅ 步骤 1/4 完成\n   抓取 {rss_sources} 个源，获取 {articles_count} 条内容\n✅ 步骤 2/4 完成\n   用户画像{profile_status}\n✅ 步骤 3/4 完成\n   简报已生成\n\n📤 步骤 4/4: 正在推送...")

            # 更新状态消息为"正在发送"
            await self._safe_edit_message(status_msg, "📤 正在发送简报...")

            # 发送简报
            await self._send_digest(user_id, digest)

            # 删除状态消息
            try:
                await status_msg.delete()
            except:
                pass

            # 发送完成后显示主菜单
            try:
                await self.bot.show_main_menu_by_id(user_id)
            except Exception as e:
                logger.warning(f"显示主菜单失败: {e}")

            return {"success": True, "message": "完整流程测试成功！"}

        except Exception as e:
            logger.error(f"完整流程失败: {e}", exc_info=True)
            try:
                await self._safe_edit_message(status_msg, f"❌ 流程失败\n\n错误：{str(e)}")
            except:
                pass
            return {"success": False, "error": f"流程失败：{str(e)}"}

    async def _weekly_feedback_analysis_job(self):
        """每周反馈分析任务"""
        logger.info("开始执行每周反馈分析任务...")

        try:
            analyzed_count = await self.feedback_analyzer.check_and_analyze_all_users()
            logger.info(f"每周反馈分析任务完成，共分析 {analyzed_count} 个用户")
        except Exception as e:
            logger.error(f"每周反馈分析任务失败: {e}", exc_info=True)
