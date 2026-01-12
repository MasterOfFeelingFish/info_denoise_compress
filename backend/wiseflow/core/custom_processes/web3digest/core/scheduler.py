"""
任务调度器 - 管理定时推送
"""
import asyncio
from datetime import datetime, time
from typing import Optional

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
        
        # 添加每日推送任务
        push_time = settings.DAILY_PUSH_TIME.split(":")
        hour = int(push_time[0])
        minute = int(push_time[1])
        
        self.scheduler.add_job(
            func=self._daily_digest_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            id="daily_digest",
            name="每日简报推送",
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
        
        logger.info(f"调度器已启动，每日 {settings.DAILY_PUSH_TIME} 推送简报")
    
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        # 停止抓取调度器
        await self.crawler_scheduler.stop()
        
        self.scheduler.shutdown()
        self._running = False
        logger.info("调度器已停止")
    
    async def _daily_digest_job(self):
        """每日简报任务"""
        from datetime import datetime
        job_start_time = datetime.now()
        logger.info(f"开始执行每日简报任务 - {job_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        try:
            # 获取所有活跃用户
            users = await self.bot.user_manager.get_active_users()
            
            if not users:
                logger.info("没有活跃用户，任务结束")
                return
            
            logger.info(f"找到 {len(users)} 个活跃用户，开始推送")
            
            # 为每个用户生成并推送简报
            for user in users:
                try:
                    user_id = int(user["id"])
                    
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
                            logger.info(f"✅ 已为用户 {user_id} 推送简报")
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
            
            job_end_time = datetime.now()
            duration = (job_end_time - job_start_time).total_seconds()
            
            logger.info(
                f"每日简报任务完成 - "
                f"成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count}, "
                f"耗时: {duration:.1f}秒"
            )
            
        except Exception as e:
            logger.error(f"每日简报任务失败: {e}", exc_info=True)
    
    async def _send_digest(self, user_id: int, digest: str):
        """发送简报给用户"""
        try:
            # 分批发送，避免消息过长
            messages = self._split_message(digest, max_length=4000)
            
            for i, msg in enumerate(messages):
                if i == len(messages) - 1:
                    # 最后一条消息添加反馈按钮
                    await self._send_with_feedback(user_id, msg)
                else:
                    await self.bot.application.bot.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode="Markdown"
                    )
                
                # 避免发送过快
                if i < len(messages) - 1:
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"发送简报失败 {user_id}: {e}")
            raise
    
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
    
    async def _send_with_feedback(self, user_id: int, message: str):
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
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    def _split_message(self, text: str, max_length: int = 4000) -> list:
        """分割长消息"""
        if len(text) <= max_length:
            return [text]
        
        messages = []
        current_msg = ""
        
        lines = text.split("\n")
        for line in lines:
            if len(current_msg) + len(line) + 1 <= max_length:
                current_msg += line + "\n"
            else:
                if current_msg:
                    messages.append(current_msg.rstrip())
                current_msg = line + "\n"
        
        if current_msg:
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
    
    async def trigger_manual_digest_with_status(self, user_id: int, status_msg):
        """
        手动触发完整流程，带状态更新
        
        流程：抓取 → 筛选 → 生成 → 推送
        """
        logger.info(f"用户 {user_id} 手动触发完整流程")
        
        try:
            # 步骤 1: 抓取信息
            await status_msg.edit_text("🚀 开始完整流程测试...\n\n步骤 1/4: 正在抓取信息...")
            
            from core.custom_processes.web3digest.core.crawler_scheduler import CrawlerScheduler
            crawler = CrawlerScheduler()
            # 使用用户自定义的信息源
            user_sources = await self.bot.source_manager.get_enabled_sources_for_crawl(user_id)
            crawl_result = await crawler.wiseflow_client.trigger_crawl(sources=user_sources)
            
            if crawl_result.get("status") != 0:
                return {"success": False, "error": f"抓取失败：{crawl_result.get('warnings', [])}"}
            
            logger.info(f"抓取完成：{crawl_result.get('articles_count', 0)} 条文章")
            
            # 步骤 2: 获取用户画像
            await status_msg.edit_text("✅ 步骤 1/4 完成：已抓取信息\n\n步骤 2/4: 正在筛选个性化内容...")
            
            profile = await self.bot.profile_manager.get_profile(user_id)
            if not profile:
                return {"success": False, "error": "请先使用 /start 完成偏好设置"}
            
            # 步骤 3: 生成简报
            await status_msg.edit_text("✅ 步骤 2/4 完成：已筛选内容\n\n步骤 3/4: 正在生成简报...")
            
            digest = await self.digest_generator.generate_digest(user_id, profile)
            
            if not digest:
                return {"success": False, "error": "抱歉，暂无符合您偏好的信息"}
            
            # 步骤 4: 推送简报
            await status_msg.edit_text("✅ 步骤 3/4 完成：简报已生成\n\n步骤 4/4: 正在推送...")
            
            await self._send_digest(user_id, digest)
            
            return {"success": True, "message": "完整流程测试成功！"}
            
        except Exception as e:
            logger.error(f"完整流程失败: {e}", exc_info=True)
            return {"success": False, "error": f"流程失败：{str(e)}"}
    
    async def _weekly_feedback_analysis_job(self):
        """每周反馈分析任务"""
        logger.info("开始执行每周反馈分析任务...")
        
        try:
            analyzed_count = await self.feedback_analyzer.check_and_analyze_all_users()
            logger.info(f"每周反馈分析任务完成，共分析 {analyzed_count} 个用户")
        except Exception as e:
            logger.error(f"每周反馈分析任务失败: {e}", exc_info=True)
