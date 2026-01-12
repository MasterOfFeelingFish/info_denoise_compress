#!/usr/bin/env python3
"""
抓取功能测试脚本
"""
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient
from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient
from core.custom_processes.web3digest.core.crawler_scheduler import CrawlerScheduler

logger = setup_logger(__name__)


async def test_rss_app_client():
    """测试 RSS.app 客户端"""
    print("\n" + "="*50)
    print("测试 RSS.app 客户端")
    print("="*50)
    
    client = RSSAppClient()
    
    # 测试获取所有源
    sources = await client.get_all_rss_sources()
    print(f"\n获取到 {len(sources)} 个信息源:")
    
    for i, source in enumerate(sources[:5], 1):  # 只显示前5个
        print(f"{i}. {source['name']} ({source['category']})")
        print(f"   URL: {source['url']}")
        print(f"   类型: {source['source_type']}")
    
    if len(sources) > 5:
        print(f"\n... 还有 {len(sources) - 5} 个源")
    
    # 测试验证 RSS URL（只测试第一个）
    if sources:
        test_url = sources[0]["url"]
        print(f"\n验证 RSS URL: {test_url}")
        is_valid = await client.verify_rss_url(test_url)
        print(f"验证结果: {'✅ 有效' if is_valid else '❌ 无效'}")


async def test_wiseflow_client():
    """测试 WiseFlow 客户端"""
    print("\n" + "="*50)
    print("测试 WiseFlow 客户端")
    print("="*50)
    
    client = WiseFlowClient()
    
    # 初始化
    print("\n初始化 WiseFlow 客户端...")
    await client.initialize()
    print("✅ 初始化成功")
    
    # 获取源列表
    print("\n获取信息源列表...")
    sources = await client.get_sources()
    print(f"✅ 获取到 {len(sources)} 个源")
    
    # 测试抓取（只抓取前3个源，避免耗时过长）
    print("\n开始测试抓取（仅抓取前3个源）...")
    test_sources = sources[:3]
    print(f"测试源: {[s['name'] for s in test_sources]}")
    
    try:
        result = await client.trigger_crawl(sources=test_sources)
        print(f"\n✅ 抓取完成:")
        print(f"   状态: {result['status']}")
        print(f"   处理数量: {result['apply_count']}")
        print(f"   RSS源: {result['rss_sources']}")
        print(f"   文章数: {result['articles_count']}")
        
        if result.get("warnings"):
            print(f"   警告: {result['warnings']}")
        
        # 获取今日信息
        print("\n获取今日抓取的信息...")
        today_info = await client.get_today_info()
        print(f"✅ 获取到 {len(today_info)} 条今日信息")
        
        if today_info:
            print("\n前3条信息:")
            for i, info in enumerate(today_info[:3], 1):
                print(f"\n{i}. {info['title']}")
                print(f"   来源: {info['source']}")
                print(f"   URL: {info['url']}")
                print(f"   内容预览: {info['content'][:100]}...")
        
    except Exception as e:
        print(f"\n❌ 抓取失败: {e}")
        import traceback
        traceback.print_exc()


async def test_full_workflow():
    """测试完整工作流程"""
    print("\n" + "="*50)
    print("测试完整工作流程（抓取→筛选→生成）")
    print("="*50)
    
    from core.custom_processes.web3digest.core.digest_generator import DigestGenerator
    from core.custom_processes.web3digest.core.profile_manager import ProfileManager
    
    # 1. 抓取信息
    print("\n[1/3] 抓取信息...")
    crawler = CrawlerScheduler()
    crawl_result = await crawler.trigger_manual_crawl()
    print(f"✅ 抓取完成: {crawl_result['articles_count']} 条文章")
    
    # 2. 获取用户画像（测试用）
    print("\n[2/3] 准备用户画像...")
    profile_manager = ProfileManager()
    # 创建一个测试画像
    test_profile = """这是一个关注 Web3 领域的用户。

【关注领域】
• DeFi, Layer2, 以太坊

【关注项目】
• ETH, ARB, OP

【内容偏好】
• 技术进展
• 链上数据
• 融资动态

【偏好信息源】
• VitalikButerin
• lookonchain

【信息量偏好】
• 标准版(10-20条)
"""
    print("✅ 使用测试画像")
    
    # 3. 生成简报
    print("\n[3/3] 生成简报...")
    digest_generator = DigestGenerator()
    test_user_id = 999999  # 测试用户ID
    
    digest = await digest_generator.generate_digest(test_user_id, test_profile)
    
    if digest:
        print("✅ 简报生成成功")
        print("\n" + "-"*50)
        print("简报预览（前500字符）:")
        print("-"*50)
        print(digest[:500] + "...")
    else:
        print("❌ 简报生成失败（可能没有符合条件的信息）")


async def main():
    """主测试函数"""
    print("🚀 Web3 Digest 抓取功能测试")
    print("="*50)
    
    # 设置事件循环策略 (Windows 兼容性)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        # 测试1: RSS.app 客户端
        await test_rss_app_client()
        
        # 测试2: WiseFlow 客户端
        await test_wiseflow_client()
        
        # 测试3: 完整工作流程（可选，耗时较长）
        print("\n" + "="*50)
        user_input = input("是否测试完整工作流程？(y/n): ")
        if user_input.lower() == 'y':
            await test_full_workflow()
        
        print("\n" + "="*50)
        print("✅ 所有测试完成")
        print("="*50)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
