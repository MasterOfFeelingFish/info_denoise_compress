#!/usr/bin/env python3
"""
Web3 Daily Digest - Main Entry Point
基于 WiseFlow 的 Web3 个性化信息聚合服务
"""

import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径，确保可以导入 core 模块
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.custom_processes.web3digest.bot.telegram_bot import Web3DigestBot
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.scheduler import DigestScheduler
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)


async def main():
    """主程序入口"""
    try:
        # 初始化数据目录
        await init_data_dirs()
        
        # 创建并启动 Telegram Bot
        bot = Web3DigestBot(token=settings.TELEGRAM_BOT_TOKEN)
        
        # 创建调度器
        scheduler = DigestScheduler(bot=bot)
        
        # 启动调度器
        await scheduler.start()
        
        # 启动 Bot
        logger.info("🚀 Web3 Daily Digest 服务启动中...")
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭服务...")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        raise
    finally:
        # 清理资源
        if 'scheduler' in locals():
            await scheduler.stop()
        if 'bot' in locals():
            await bot.stop()
        logger.info("服务已停止")


async def init_data_dirs():
    """初始化数据目录结构"""
    data_path = Path(settings.DATA_DIR)
    
    # 创建必要的目录
    dirs = ["users", "profiles", "feedback", "daily_stats", "raw_info", "logs"]
    
    for dir_name in dirs:
        dir_path = data_path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"确保目录存在: {dir_path}")


if __name__ == "__main__":
    # 设置事件循环策略 (Windows 兼容性)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())
