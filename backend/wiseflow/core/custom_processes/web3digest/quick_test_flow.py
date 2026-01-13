#!/usr/bin/env python3
"""
快速测试流程 - 测试抓取和生成流程
"""

import sys
import os
from pathlib import Path

# 添加项目路径
_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

# 确保环境变量在导入其他模块之前设置
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

if not os.getenv("LLM_API_BASE"):
    os.environ["LLM_API_BASE"] = "https://api.moonshot.cn/v1"
if not os.getenv("PRIMARY_MODEL"):
    os.environ["PRIMARY_MODEL"] = "moonshot-v1-32k"

import asyncio


async def test_crawl():
    """测试抓取流程"""
    print("\n=== 测试抓取流程 ===")
    
    from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient
    
    client = WiseFlowClient()
    await client.initialize()
    
    # 使用真实的 RSS.app 链接和免费 RSS 源
    sources = [
        # RSS.app 真实链接（已验证可用）
        {
            "url": "https://rss.app/feeds/zXJZGK1tpoNrKUV1.xml",
            "name": "@VitalikButerin",
            "category": "行业领袖",
            "enabled": True
        },
        {
            "url": "https://rss.app/feeds/f1b0GQFXeSZjCd9q.xml",
            "name": "@cz_binance",
            "category": "行业领袖",
            "enabled": True
        },
        # 免费网站 RSS
        {
            "url": "https://cointelegraph.com/rss",
            "name": "Cointelegraph",
            "category": "媒体",
            "enabled": True
        },
    ]
    
    print(f"开始抓取 {len(sources)} 个源...")
    result = await client.trigger_crawl(sources=sources)
    
    print(f"抓取结果:")
    print(f"  - 状态: {result['status']}")
    print(f"  - 文章数: {result['articles_count']}")
    print(f"  - RSS源: {result['rss_sources']}")
    print(f"  - 警告: {result.get('warnings', [])}")
    
    return result


async def test_get_info():
    """测试获取今日信息"""
    print("\n=== 测试获取今日信息 ===")
    
    from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient
    
    client = WiseFlowClient()
    await client.initialize()
    
    info_list = await client.get_today_info()
    
    print(f"获取到 {len(info_list)} 条信息")
    
    if info_list:
        print("\n前 3 条信息:")
        for i, info in enumerate(info_list[:3]):
            print(f"\n{i+1}. {info.get('title', '无标题')[:50]}")
            print(f"   来源: {info.get('source', '未知')}")
            print(f"   URL: {info.get('url', '')[:60]}...")
    
    return info_list


async def test_digest_generation():
    """测试简报生成（需要先有抓取的内容）"""
    print("\n=== 测试简报生成 ===")
    
    from core.custom_processes.web3digest.core.digest_generator import DigestGenerator
    
    # 模拟用户画像
    user_profile = """
    这是一个关注 Web3 领域的用户。

    【关注领域】
    • DeFi, Layer2, 以太坊

    【关注项目】
    • Ethereum, Arbitrum, Optimism

    【内容偏好】
    • 技术分析
    • 项目动态
    • 市场趋势
    """
    
    generator = DigestGenerator()
    
    print("正在生成简报...")
    digest = await generator.generate_digest(user_id=12345, user_profile=user_profile)
    
    if digest:
        print("\n生成的简报:")
        print("-" * 50)
        print(digest)
        print("-" * 50)
    else:
        print("简报生成失败或没有可用信息")
    
    return digest


async def test_llm():
    """测试 LLM 连接"""
    print("\n=== 测试 LLM 连接 ===")
    
    from core.custom_processes.web3digest.core.llm_client import LLMClient
    
    client = LLMClient()
    
    try:
        response = await client.complete("你好，请用一句话介绍自己。", max_tokens=50)
        print(f"LLM 响应: {response}")
        return True
    except Exception as e:
        print(f"LLM 连接失败: {e}")
        return False


async def main():
    """主测试流程"""
    print("=" * 60)
    print("Web3 Daily Digest - 完整流程测试")
    print("=" * 60)
    
    # 1. 测试 LLM 连接
    llm_ok = await test_llm()
    if not llm_ok:
        print("\n[ERROR] LLM 连接失败，请检查 API Key")
        return
    
    # 2. 测试抓取
    crawl_result = await test_crawl()
    
    # 3. 测试获取信息
    info_list = await test_get_info()
    
    # 4. 如果有信息，测试简报生成
    if info_list:
        await test_digest_generation()
    else:
        print("\n没有可用信息，跳过简报生成测试")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
