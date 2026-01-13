#!/usr/bin/env python3
"""
Web3 Daily Digest - 完整测试脚本
使用方法: python deploy/test_all.py
"""

import sys
import os
from pathlib import Path

# 设置项目路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
backend_dir = project_root / "backend" / "wiseflow"
web3digest_dir = backend_dir / "core" / "custom_processes" / "web3digest"

sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(web3digest_dir / ".env", override=True)

import asyncio


def print_header(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def print_ok(msg):
    print(f"[OK] {msg}")


def print_fail(msg):
    print(f"[FAIL] {msg}")


async def test_config():
    """测试 1: 配置验证"""
    print_header("测试 1: 配置验证")
    try:
        from core.custom_processes.web3digest.core.config import settings
        print(f"  LLM_API_BASE: {settings.LLM_API_BASE}")
        print(f"  PRIMARY_MODEL: {settings.PRIMARY_MODEL}")
        print(f"  DAILY_PUSH_TIME: {settings.DAILY_PUSH_TIME}")
        print(f"  DATA_DIR: {settings.DATA_DIR}")
        print_ok("配置验证通过")
        return True
    except Exception as e:
        print_fail(f"配置验证失败: {e}")
        return False


async def test_llm():
    """测试 2: LLM 连接"""
    print_header("测试 2: LLM 连接")
    try:
        from core.custom_processes.web3digest.core.llm_client import LLMClient
        client = LLMClient()
        response = await client.complete("Say OK", max_tokens=10)
        print(f"  LLM Response: {response[:50]}...")
        print_ok("LLM 连接成功")
        return True
    except Exception as e:
        print_fail(f"LLM 连接失败: {e}")
        return False


async def test_rss_crawl():
    """测试 3: RSS 抓取"""
    print_header("测试 3: RSS 抓取")
    try:
        from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient
        client = WiseFlowClient()
        await client.initialize()
        
        sources = [
            {"url": "https://cointelegraph.com/rss", "name": "Cointelegraph", "enabled": True}
        ]
        result = await client.trigger_crawl(sources=sources)
        
        print(f"  Status: {result['status']}")
        print(f"  RSS Sources: {result['rss_sources']}")
        print(f"  Articles: {result['articles_count']}")
        
        if result['status'] == 0:
            print_ok("RSS 抓取成功")
            return True
        else:
            print_fail("RSS 抓取失败")
            return False
    except Exception as e:
        print_fail(f"RSS 抓取异常: {e}")
        return False


async def test_data_storage():
    """测试 4: 数据存储"""
    print_header("测试 4: 数据存储 (JSON)")
    try:
        from core.custom_processes.web3digest.core.user_manager import UserManager
        manager = UserManager()
        
        # 注册测试用户
        is_new = await manager.register_user(99999, "TestUser")
        user = await manager.get_user(99999)
        
        if user:
            print(f"  User ID: {user['id']}")
            print(f"  User Name: {user['name']}")
            print(f"  Is New: {is_new}")
            print_ok("用户数据存储成功")
            return True
        else:
            print_fail("用户数据存储失败")
            return False
    except Exception as e:
        print_fail(f"数据存储异常: {e}")
        return False


async def test_source_manager():
    """测试 5: 信息源管理"""
    print_header("测试 5: 信息源管理")
    try:
        from core.custom_processes.web3digest.core.source_manager import SourceManager
        manager = SourceManager()
        
        sources = await manager.get_user_sources(99999)
        preset_count = len(sources['preset_sources'])
        custom_count = len(sources['custom_sources'])
        
        # 统计启用的源
        enabled_preset = sum(1 for s in sources['preset_sources'] if s.get('enabled', True))
        
        print(f"  Preset sources: {enabled_preset}/{preset_count} enabled")
        print(f"  Custom sources: {custom_count}")
        print_ok("信息源管理正常")
        return True
    except Exception as e:
        print_fail(f"信息源管理异常: {e}")
        return False


async def test_profile_manager():
    """测试 6: 用户画像管理"""
    print_header("测试 6: 用户画像管理")
    try:
        from core.custom_processes.web3digest.core.profile_manager import ProfileManager
        manager = ProfileManager()
        
        # 创建测试画像
        profile_data = {
            "interests": ["DeFi", "Layer2"],
            "projects": ["Ethereum", "Arbitrum"],
            "preferences": {
                "content_types": ["技术分析", "项目动态"]
            }
        }
        
        await manager.create_profile(99999, profile_data)
        profile = await manager.get_profile(99999)
        
        if profile:
            print(f"  Profile length: {len(profile)} chars")
            print(f"  Contains interests: {'关注领域' in profile}")
            print_ok("用户画像管理正常")
            return True
        else:
            print_fail("用户画像创建失败")
            return False
    except Exception as e:
        print_fail(f"用户画像管理异常: {e}")
        return False


async def test_feedback_manager():
    """测试 7: 反馈管理"""
    print_header("测试 7: 反馈管理")
    try:
        from core.custom_processes.web3digest.core.feedback_manager import FeedbackManager
        manager = FeedbackManager()
        
        # 保存测试反馈
        success = await manager.save_feedback(
            user_id=99999,
            overall="positive",
            reason_selected=["内容相关"],
            reason_text="测试反馈"
        )
        
        if success:
            count = await manager.get_feedback_count(99999)
            print(f"  Feedback saved: {success}")
            print(f"  Total feedbacks: {count}")
            print_ok("反馈管理正常")
            return True
        else:
            print_fail("反馈保存失败")
            return False
    except Exception as e:
        print_fail(f"反馈管理异常: {e}")
        return False


async def main():
    print("\n" + "="*60)
    print("  Web3 Daily Digest - 完整测试")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    results.append(await test_config())
    results.append(await test_llm())
    results.append(await test_rss_crawl())
    results.append(await test_data_storage())
    results.append(await test_source_manager())
    results.append(await test_profile_manager())
    results.append(await test_feedback_manager())
    
    # 汇总结果
    print_header("测试结果汇总")
    passed = sum(results)
    total = len(results)
    
    print(f"  通过: {passed}/{total}")
    print(f"  失败: {total - passed}/{total}")
    
    if passed == total:
        print("\n" + "="*60)
        print("  [SUCCESS] All tests passed!")
        print("="*60)
        print("\nNext: Start service and send /test in Telegram for E2E test")
    else:
        print("\n" + "="*60)
        print("  [FAILED] Some tests failed, check errors above")
        print("="*60)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
