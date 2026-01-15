#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web3 Daily Digest - Main Entry Point
基于 WiseFlow 的 Web3 个性化信息聚合服务
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# 设置环境变量确保UTF-8
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform == 'win32':
    os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = '1'

# 初始化每日日志器
from utils.logger import get_daily_logger, log_user_step, log_user_click, log_user_command, log_user_error
daily_logger = get_daily_logger()

# 添加项目根目录到路径，确保可以导入 core 模块
# web3digest/main.py -> custom_processes -> core -> wiseflow (项目根)
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 加载环境变量（从 web3digest 目录）- 必须在导入其他模块之前
from dotenv import load_dotenv
_env_file = Path(__file__).parent / ".env"
load_dotenv(_env_file, override=True)

# 确保 LLM 环境变量已设置（WiseFlow 依赖）
if not os.getenv("LLM_API_BASE"):
    os.environ["LLM_API_BASE"] = "https://api.moonshot.cn/v1"
if not os.getenv("LLM_API_KEY"):
    print("[ERROR] LLM_API_KEY not set in .env file")
    sys.exit(1)

print(f"[INFO] Loaded .env from: {_env_file}")
print(f"[INFO] LLM_API_BASE: {os.getenv('LLM_API_BASE')}")

from core.custom_processes.web3digest.bot.telegram_bot import Web3DigestBot
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.scheduler import DigestScheduler
from utils.logger import setup_logger

logger = setup_logger(__name__)
# 获取每日日志器
daily_logger = get_daily_logger()


async def main():
    """主程序入口"""
    # 检查是否已有实例在运行
    if await check_instance_running():
        logger.error("检测到已有 Web3 Daily Digest 实例在运行！")
        logger.error("请先停止现有实例，或等待一分钟后再试。")
        input("按回车键退出...")
        return
    
    # 确保UTF-8编码
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except:
        pass

    # 记录服务启动步骤
    log_user_step(0, "程序启动", {"status": "starting_main_loop"})
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
        logger.info("Web3 Daily Digest 服务启动...")
        log_user_step(0, "服务启动", {"service": "Web3DailyDigest", "status": "starting"})
        await bot.start()

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭服务...")
    except Exception as e:
        log_user_error(0, "service_startup_failed", str(e))
        logger.error(f"服务启动失败: {e}")
        raise
    finally:
        # 清理资源
        if 'scheduler' in locals():
            await scheduler.stop()
        if 'bot' in locals():
            await bot.stop()
        logger.info("服务已停止")
        log_user_step(0, "服务停止", {"status": "stopped"})


async def check_instance_running():
    """检查是否已有实例在运行"""
    import psutil
    import os

    current_pid = os.getpid()
    current_process = psutil.Process(current_pid)

    # 查找所有 Python 进程
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 跳过自己
            if proc.info['pid'] == current_pid:
                continue

            # 检查是否是 Python 进程且运行了相同的脚本
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info.get('cmdline', [])
                if cmdline and any('web3digest' in str(cmd).lower() for cmd in cmdline):
                    # 找到另一个运行中的实例
                    logger.warning(f"发现运行中的实例 PID: {proc.info['pid']}")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return False


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

    # 记录程序启动
    log_user_step(0, "程序启动", {"python_version": sys.version, "platform": sys.platform})

    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_user_step(0, "用户中断程序", {"status": "user_interrupted"})
        print("\n[INFO] 收到中断信号，程序退出")
    except Exception as e:
        log_user_error(0, "program_crash", str(e))
        print(f"[ERROR] 程序运行失败: {e}")
        sys.exit(1)
