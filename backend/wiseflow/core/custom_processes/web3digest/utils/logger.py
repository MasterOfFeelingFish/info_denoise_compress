"""
日志配置模块
"""
import sys
from loguru import logger
from core.custom_processes.web3digest.core.config import settings


def setup_logger(name: str = None):
    """设置日志配置"""
    
    # 移除默认的处理器
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True
    )
    
    # 添加文件输出
    logger.add(
        f"{settings.DATA_DIR}/logs/web3digest.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
        rotation="10 MB",
        retention="30 days",
        compression="zip"
    )
    
    # 如果指定了 name，返回对应的 logger
    if name:
        return logger.bind(name=name)
    
    return logger
