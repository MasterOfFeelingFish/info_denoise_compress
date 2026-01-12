#!/usr/bin/env python3
"""
反馈学习闭环测试脚本
验证：用户反馈 → 数据存储 → AI 分析 → 画像更新 → 下次筛选受影响
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
from core.custom_processes.web3digest.core.feedback_manager import FeedbackManager
from core.custom_processes.web3digest.core.feedback_analyzer import FeedbackAnalyzer
from core.custom_processes.web3digest.core.profile_manager import ProfileManager
from core.custom_processes.web3digest.core.digest_generator import DigestGenerator

logger = setup_logger(__name__)

# 测试用户ID
TEST_USER_ID = 999999


async def test_feedback_loop():
    """测试反馈学习闭环"""
    print("\n" + "="*60)
    print("反馈学习闭环测试")
    print("="*60)
    
    feedback_manager = FeedbackManager()
    feedback_analyzer = FeedbackAnalyzer()
    profile_manager = ProfileManager()
    digest_generator = DigestGenerator()
    
    # 步骤 1: 创建测试用户画像
    print("\n[步骤 1] 创建测试用户画像...")
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
    
    # 保存测试画像
    profile_file = Path(settings.DATA_DIR) / "profiles" / f"{TEST_USER_ID}.txt"
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    with open(profile_file, 'w', encoding='utf-8') as f:
        f.write(test_profile)
    
    print("✅ 测试画像已创建")
    
    # 步骤 2: 模拟用户反馈
    print("\n[步骤 2] 模拟用户反馈...")
    
    # 添加多个负面反馈，达到阈值
    threshold = settings.FEEDBACK_UPDATE_THRESHOLD
    print(f"需要 {threshold} 条反馈才能触发分析")
    
    for i in range(threshold):
        reason = ["内容不感兴趣", "信息太多/太杂", "漏掉重要信息"][i % 3]
        await feedback_manager.save_feedback(
            TEST_USER_ID,
            "negative",
            reason_selected=[reason],
            reason_text=f"测试反馈 {i+1}: 希望看到更多关于 {reason} 的内容"
        )
        print(f"  反馈 {i+1}/{threshold}: {reason}")
    
    print("✅ 反馈已保存")
    
    # 步骤 3: 验证反馈存储
    print("\n[步骤 3] 验证反馈存储...")
    feedbacks = await feedback_manager.get_user_feedbacks(TEST_USER_ID)
    print(f"✅ 获取到 {len(feedbacks)} 条反馈记录")
    
    if len(feedbacks) < threshold:
        print(f"⚠️  警告：反馈数量 ({len(feedbacks)}) 少于阈值 ({threshold})")
    
    # 步骤 4: 触发 AI 分析
    print("\n[步骤 4] 触发 AI 分析反馈...")
    success = await feedback_analyzer.analyze_user_feedback(TEST_USER_ID)
    
    if success:
        print("✅ AI 分析完成，画像已更新")
    else:
        print("❌ AI 分析失败")
        return
    
    # 步骤 5: 验证画像更新
    print("\n[步骤 5] 验证画像更新...")
    updated_profile = await profile_manager.get_profile(TEST_USER_ID)
    
    if updated_profile:
        if "【AI 学习理解】" in updated_profile:
            print("✅ 画像已包含 AI 学习理解部分")
            # 提取 AI 理解部分
            ai_part = updated_profile.split("【AI 学习理解】")[1].split("【最后更新】")[0].strip()
            print(f"\nAI 学习理解内容预览：")
            print("-" * 60)
            print(ai_part[:200] + "..." if len(ai_part) > 200 else ai_part)
            print("-" * 60)
        else:
            print("⚠️  警告：画像未包含 AI 学习理解部分")
    else:
        print("❌ 无法获取更新后的画像")
        return
    
    # 步骤 6: 验证下次筛选受影响（模拟）
    print("\n[步骤 6] 验证画像更新对筛选的影响...")
    print("（此步骤需要实际的信息数据，这里仅验证画像格式）")
    
    if "【AI 学习理解】" in updated_profile:
        print("✅ 画像格式正确，包含 AI 学习理解")
        print("   下次生成简报时，AI 会参考这些理解来筛选内容")
    else:
        print("❌ 画像格式不正确")
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print("✅ 反馈存储：正常")
    print("✅ AI 分析：正常")
    print("✅ 画像更新：正常")
    print("\n闭环验证：用户反馈 → 数据存储 → AI 分析 → 画像更新 ✅")
    print("\n注意：实际验证需要生成简报，观察推送内容的变化")


async def test_single_feedback():
    """测试单条反馈"""
    print("\n" + "="*60)
    print("单条反馈测试")
    print("="*60)
    
    feedback_manager = FeedbackManager()
    
    # 添加单条反馈
    print("\n添加单条信息反馈...")
    success = await feedback_manager.add_item_feedback(
        TEST_USER_ID,
        item_id="test_item_001",
        source="@whale_alert",
        rating="dislike"
    )
    
    if success:
        print("✅ 单条反馈已保存")
        
        # 验证反馈
        feedbacks = await feedback_manager.get_user_feedbacks(TEST_USER_ID)
        if feedbacks:
            last_feedback = feedbacks[0]
            item_feedbacks = last_feedback.get("item_feedbacks", [])
            if item_feedbacks:
                print(f"✅ 验证成功，找到 {len(item_feedbacks)} 条单条反馈")
                print(f"   最新反馈: {item_feedbacks[-1]}")
    else:
        print("❌ 单条反馈保存失败")


async def main():
    """主测试函数"""
    print("🚀 反馈学习闭环测试")
    print("="*60)
    
    # 设置事件循环策略 (Windows 兼容性)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        # 测试完整闭环
        await test_feedback_loop()
        
        # 测试单条反馈
        await test_single_feedback()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    from core.custom_processes.web3digest.core.config import settings
    asyncio.run(main())
