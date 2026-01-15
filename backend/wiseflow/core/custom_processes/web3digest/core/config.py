"""
配置管理模块
"""
import os
from pathlib import Path
from datetime import time
from typing import List, Optional

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
except ImportError:
    from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """全局配置"""
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    
    # LLM 配置
    # 支持多种 LLM 服务商（OpenAI 兼容接口）
    # Kimi API: https://api.moonshot.cn/v1, 模型: moonshot-v1-8k / moonshot-v1-32k / moonshot-v1-128k
    # SiliconFlow: https://api.siliconflow.cn/v1, 模型: Qwen/Qwen2.5-32B-Instruct
    LLM_API_BASE: str = Field("https://api.moonshot.cn/v1", env="LLM_API_BASE")
    LLM_API_KEY: str = Field(..., env="LLM_API_KEY")
    PRIMARY_MODEL: str = Field("moonshot-v1-32k", env="PRIMARY_MODEL")
    LLM_CONCURRENT_NUMBER: int = Field(10, env="LLM_CONCURRENT_NUMBER")
    
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
        # 支持多个 .env 文件位置
        env_file = [
            Path(__file__).parent.parent / ".env",  # web3digest/.env
            ".env",  # 当前目录
        ]
        case_sensitive = True
        extra = "ignore"  # 忽略额外字段


class RSSSource(BaseSettings):
    """RSS 源配置"""
    name: str
    url: str
    type: str  # twitter, website, rss
    category: str  # 行业领袖, 链上数据, 项目官方, 媒体等
    enabled: bool = True


class DefaultRSSSources:
    """默认 RSS 源配置"""
    
    # ====== RSS.app 真实订阅链接（已验证可用 ✅）======
    # 这些是通过 RSS.app 创建的 Twitter 订阅
    RSSAPP_FEEDS = [
        {
            "name": "@VitalikButerin",
            "url": "https://rss.app/feeds/zXJZGK1tpoNrKUV1.xml",
            "type": "twitter",
            "category": "行业领袖",
            "enabled": True
        },
        {
            "name": "@cz_binance",
            "url": "https://rss.app/feeds/f1b0GQFXeSZjCd9q.xml",
            "type": "twitter",
            "category": "行业领袖",
            "enabled": True
        },
    ]
    
    # ====== Twitter 账号（待添加 RSS.app 订阅）======
    TWITTER_ACCOUNTS = [
        # 行业领袖 & KOL
        {"name": "VitalikButerin", "category": "行业领袖", "desc": "以太坊创始人"},
        {"name": "cz_binance", "category": "行业领袖", "desc": "币安创始人"},
        {"name": "brian_armstrong", "category": "行业领袖", "desc": "Coinbase CEO"},
        
        # 链上数据 & 聪明钱
        {"name": "whale_alert", "category": "链上数据", "desc": "大额转账监控"},
        {"name": "lookonchain", "category": "链上数据", "desc": "链上数据分析"},
        {"name": "EmberCN", "category": "链上数据", "desc": "链上数据分析(CN)"},
        {"name": "ai_9684xtpa", "category": "链上数据", "desc": "聪明钱追踪(CN)"},
        
        # 项目官方
        {"name": "ethereum", "category": "项目官方", "desc": "以太坊官方"},
        {"name": "solana", "category": "项目官方", "desc": "Solana 官方"},
        {"name": "arbitrum", "category": "项目官方", "desc": "Arbitrum 官方"},
        {"name": "optimism", "category": "项目官方", "desc": "Optimism 官方"},
        
        # 媒体 & 研究
        {"name": "CoinDesk", "category": "媒体", "desc": "加密媒体"},
        {"name": "TheBlock__", "category": "媒体", "desc": "加密媒体"},
        {"name": "WuBlockchain", "category": "媒体", "desc": "吴说区块链"},
        {"name": "BlockBeatsAsia", "category": "媒体", "desc": "律动"},
    ]
    
    # ====== 网站 RSS 源（免费 ✅）======
    # 注意：为了保证抓取速度（<10秒），只默认启用最稳定的几个源
    WEBSITE_RSS = [
        # 英文媒体（快速稳定 ✅）
        {
            "name": "Cointelegraph",
            "url": "https://cointelegraph.com/rss",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：快速稳定
        },
        {
            "name": "CoinDesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：快速稳定
        },
        {
            "name": "Decrypt",
            "url": "https://decrypt.co/feed",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：快速稳定
        },
        {
            "name": "ChainFeeds",
            "url": "https://www.chainfeeds.me/rss",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：稳定
        },
        {
            "name": "The Block",
            "url": "https://www.theblock.co/rss.xml",
            "type": "website",
            "category": "媒体",
            "enabled": False  # 国内访问可能慢
        },
        # 中文媒体
        {
            "name": "Foresight News",
            "url": "https://foresightnews.pro/feed",
            "type": "website",
            "category": "媒体",
            "enabled": False  # 国内访问可能慢，用户可自行启用
        },
        {
            "name": "律动 BlockBeats",
            "url": "https://www.theblockbeats.info/rss",
            "type": "website",
            "category": "媒体",
            "enabled": False  # 国内访问可能慢，用户可自行启用
        },
        {
            "name": "金色财经",
            "url": "https://www.jinse.cn/lives/rss",
            "type": "website",
            "category": "媒体",
            "enabled": False  # 国内访问可能慢，用户可自行启用
        },
        {
            "name": "ChainCatcher",
            "url": "https://www.chaincatcher.com/clist.xml",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：有效
        },
        {
            "name": "TechFlow Post",
            "url": "https://www.techflowpost.com/api/client/common/rss.xml",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：有效
        },
        {
            "name": "DeFi Rate",
            "url": "https://defirate.com/rss",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：有效
        },
        {
            "name": "Next Event Horizon",
            "url": "https://nexteventhorizon.substack.com/feed",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：有效
        },
        {
            "name": "Prediction News",
            "url": "https://predictionnews.com/feed/",
            "type": "website",
            "category": "媒体",
            "enabled": True  # 已验证：有效
        },
    ]


# 全局设置实例
settings = Settings()
