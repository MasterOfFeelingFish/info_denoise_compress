"""
配置管理模块
"""
import os
from datetime import time
from typing import List, Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """全局配置"""
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    
    # LLM 配置
    # 支持多种 LLM 服务商（OpenAI 兼容接口）
    # Kimi API: https://api.moonshot.cn/v1, 模型: kimi-k2-thinking-preview
    # SiliconFlow: https://api.siliconflow.cn/v1, 模型: Qwen/Qwen2.5-32B-Instruct
    LLM_API_BASE: str = Field("https://api.moonshot.cn/v1", env="LLM_API_BASE")
    LLM_API_KEY: str = Field(..., env="LLM_API_KEY")
    PRIMARY_MODEL: str = Field("kimi-k2-thinking-preview", env="PRIMARY_MODEL")
    LLM_CONCURRENT_NUMBER: int = Field(3, env="LLM_CONCURRENT_NUMBER")
    
    # RSS 配置
    RSS_APP_TOKEN: Optional[str] = Field(None, env="RSS_APP_TOKEN")
    
    # 数据存储
    DATA_DIR: str = Field("./data/web3digest", env="DATA_DIR")
    
    # 日志
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    
    # 调度配置
    DAILY_PUSH_TIME: str = Field("09:00", env="DAILY_PUSH_TIME")
    TIMEZONE: str = Field("Asia/Shanghai", env="TIMEZONE")
    
    # 任务配置
    MAX_INFO_PER_USER: int = Field(20, env="MAX_INFO_PER_USER")
    MIN_INFO_PER_USER: int = Field(5, env="MIN_INFO_PER_USER")
    
    # 反馈配置
    FEEDBACK_UPDATE_THRESHOLD: int = Field(5, env="FEEDBACK_UPDATE_THRESHOLD")
    
    # 鉴权配置
    ENABLE_WHITELIST: bool = Field(False, env="ENABLE_WHITELIST")  # 是否启用白名单模式
    ADMIN_TELEGRAM_IDS: Optional[str] = Field(None, env="ADMIN_TELEGRAM_IDS")  # 管理员 Telegram ID（逗号分隔）
    
    class Config:
        env_file = ".env"
        case_sensitive = True


class RSSSource(BaseSettings):
    """RSS 源配置"""
    name: str
    url: str
    type: str  # twitter, website, rss
    category: str  # 行业领袖, 链上数据, 项目官方, 媒体等
    enabled: bool = True


class DefaultRSSSources:
    """默认 RSS 源配置"""
    
    # Twitter 账号（需要通过 RSS.app 转换）
    TWITTER_ACCOUNTS = [
        # 行业领袖
        {"name": "VitalikButerin", "category": "行业领袖"},
        {"name": "cz_binance", "category": "行业领袖"},
        {"name": "brian_armstrong", "category": "行业领袖"},
        
        # 链上数据
        {"name": "whale_alert", "category": "链上数据"},
        {"name": "lookonchain", "category": "链上数据"},
        {"name": "EmberCN", "category": "链上数据"},
        {"name": "ai_9684xtpa", "category": "链上数据"},
        
        # 项目官方
        {"name": "ethereum", "category": "项目官方"},
        {"name": "solana", "category": "项目官方"},
        {"name": "arbitrum", "category": "项目官方"},
        {"name": "optimism", "category": "项目官方"},
        
        # 媒体
        {"name": "CoinDesk", "category": "媒体"},
        {"name": "TheBlock__", "category": "媒体"},
        {"name": "WuBlockchain", "category": "媒体"},
        {"name": "BlockBeatsAsia", "category": "媒体"},
    ]
    
    # 网站 RSS 源
    WEBSITE_RSS = [
        # 英文媒体
        {
            "name": "The Block",
            "url": "https://www.theblock.co/rss.xml",
            "type": "website",
            "category": "媒体"
        },
        {
            "name": "CoinDesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "type": "website",
            "category": "媒体"
        },
        # 中文媒体
        {
            "name": "Foresight News",
            "url": "https://foresightnews.pro/feed",
            "type": "website",
            "category": "媒体"
        },
        {
            "name": "律动 BlockBeats",
            "url": "https://www.theblockbeats.info/feed",
            "type": "website",
            "category": "媒体"
        },
        {
            "name": "金色财经",
            "url": "https://www.jinse.com/rss",
            "type": "website",
            "category": "媒体"
        },
    ]


# 全局设置实例
settings = Settings()
