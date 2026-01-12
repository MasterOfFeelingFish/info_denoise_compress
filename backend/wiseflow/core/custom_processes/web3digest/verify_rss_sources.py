#!/usr/bin/env python3
"""
RSS 源验证脚本
验证所有配置的 RSS 源是否可访问
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

from core.custom_processes.web3digest.core.rss_app_client import RSSAppClient
from core.custom_processes.web3digest.core.config import DefaultRSSSources
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)


async def verify_all_sources():
    """验证所有 RSS 源"""
    client = RSSAppClient()
    
    print("\n" + "="*60)
    print("RSS 源验证报告")
    print("="*60)
    
    # 获取所有源
    all_sources = await client.get_all_rss_sources()
    
    print(f"\n总共 {len(all_sources)} 个信息源需要验证\n")
    
    valid_sources = []
    invalid_sources = []
    
    # 验证每个源
    for i, source in enumerate(all_sources, 1):
        name = source["name"]
        url = source["url"]
        category = source["category"]
        
        print(f"[{i}/{len(all_sources)}] 验证: {name} ({category})")
        print(f"  URL: {url}")
        
        is_valid = await client.verify_rss_url(url)
        
        if is_valid:
            print(f"  状态: ✅ 有效\n")
            valid_sources.append(source)
        else:
            print(f"  状态: ❌ 无效\n")
            invalid_sources.append(source)
        
        # 避免请求过快
        await asyncio.sleep(0.5)
    
    # 输出总结
    print("\n" + "="*60)
    print("验证总结")
    print("="*60)
    print(f"总源数: {len(all_sources)}")
    print(f"有效源: {len(valid_sources)} ✅")
    print(f"无效源: {len(invalid_sources)} ❌")
    
    if invalid_sources:
        print("\n无效源列表:")
        for source in invalid_sources:
            print(f"  - {source['name']}: {source['url']}")
    
    # 检查是否满足至少3个有效源的要求
    if len(valid_sources) >= 3:
        print(f"\n✅ 满足要求：至少有 3 个有效 RSS 源")
    else:
        print(f"\n⚠️  警告：有效 RSS 源少于 3 个，需要添加更多源")
    
    return valid_sources, invalid_sources


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(verify_all_sources())
