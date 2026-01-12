"""
LLM 客户端模块 - 封装 OpenAI 兼容 API
"""
import asyncio
import json
from typing import List, Dict, Optional
import openai
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings

logger = setup_logger(__name__)


class LLMClient:
    """LLM 客户端"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE
        )
        self.model = settings.PRIMARY_MODEL
        self.semaphore = asyncio.Semaphore(settings.LLM_CONCURRENT_NUMBER)
    
    async def complete(self, prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """完成文本生成"""
        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的 Web3 信息分析助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                raise
    
    async def extract_info(self, content: str, user_profile: str) -> Dict:
        """从内容中提取信息"""
        prompt = f"""
你是一个 Web3 信息筛选专家。请从以下内容中提取有价值的信息。

## 用户画像
{user_profile}

## 内容
{content}

## 任务
1. 判断这条信息对用户是否有价值
2. 如果有价值，提取关键信息
3. 给出重要性评分（1-10）

## 输出格式
{{
    "is_valuable": true/false,
    "title": "标题",
    "summary": "一句话摘要",
    "importance_score": 1-10,
    "reason": "判断理由"
}}
"""
        
        try:
            response = await self.complete(prompt, max_tokens=300)
            return json.loads(response)
        except:
            return {
                "is_valuable": False,
                "title": "",
                "summary": "",
                "importance_score": 1,
                "reason": "解析失败"
            }
    
    async def generate_digest(self, user_profile: str, info_list: List[Dict], stats: Dict) -> str:
        """生成简报"""
        # 格式化信息列表，去重（基于标题相似度）
        unique_info_list = self._deduplicate_info(info_list)
        
        # 按重要性排序，取 Top 3
        top3_info = sorted(unique_info_list, key=lambda x: x.get("importance", 5), reverse=True)[:3]
        other_info = sorted(unique_info_list[3:], key=lambda x: x.get("importance", 5), reverse=True) if len(unique_info_list) > 3 else []
        
        # 格式化 Top 3
        top3_text = "\n".join([
            f"{i+1}. **{info['title']}**\n   {info.get('summary', '')}\n   来源: {info.get('source', '未知')} | [查看原文]({info.get('url', '#')})"
            for i, info in enumerate(top3_info)
        ])
        
        # 格式化其他信息（按来源分组）
        other_text = ""
        if other_info:
            # 按来源分组
            by_source = {}
            for info in other_info:
                source = info.get('source', '其他')
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(info)
            
            # 生成分类文本
            sections = []
            for source, items in by_source.items():
                section = f"**{source}**\n"
                for item in items[:3]:  # 每个来源最多3条
                    section += f"• {item['title']} | [查看]({item.get('url', '#')})\n"
                sections.append(section)
            other_text = "\n".join(sections)
        
        prompt = f"""
你是一个 Web3 资讯编辑。请为用户生成一份简洁、有层次的每日简报。

## 用户画像
{user_profile}

## 今日必看（Top 3）
{top3_text if top3_text else "今日暂无重要信息"}

## 更多信息
{other_text if other_text else "暂无其他信息"}

## 价值统计
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **今日为您做了什么**

• 监控信息源: {stats['sources_count']} 个
• 扫描原始信息: {stats['raw_count']} 条
• 为您精选: {stats['selected_count']} 条（仅占 {stats['filter_rate']}）
• 今日为您节省: 约 {stats['time_saved']} 小时
• 累计为您节省: {stats.get('total_time_saved', 0)} 小时

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 简报格式要求
1. 使用 Markdown 格式，确保 Telegram 能正确渲染
2. 标题使用 **粗体**
3. 链接使用 [文本](URL) 格式
4. 使用分隔线 `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━` 分隔模块
5. 保持简洁，每条信息不超过2行描述
6. 避免语义重复的信息
7. 在最后添加提示："💬 这份简报对您有帮助吗？请点击下方按钮反馈"

请直接输出完整的 Markdown 格式简报，不要添加额外的说明文字。
"""
        
        return await self.complete(prompt, max_tokens=2500, temperature=0.5)
    
    def _deduplicate_info(self, info_list: List[Dict]) -> List[Dict]:
        """去重：避免语义重复的信息"""
        if len(info_list) <= 1:
            return info_list
        
        # 简单的去重：基于标题相似度
        unique_list = []
        seen_titles = set()
        
        for info in info_list:
            title = info.get('title', '').lower().strip()
            # 移除常见标点符号
            title_clean = ''.join(c for c in title if c.isalnum() or c.isspace())
            
            # 检查是否与已有标题高度相似（简单检查：标题长度和关键词）
            is_duplicate = False
            for seen_title in seen_titles:
                # 如果标题完全相同或一个包含另一个，认为是重复
                if title_clean == seen_title or (len(title_clean) > 10 and (title_clean in seen_title or seen_title in title_clean)):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_list.append(info)
                seen_titles.add(title_clean)
        
        return unique_list
    
    async def analyze_feedback(self, current_profile: str, feedbacks: List[Dict]) -> str:
        """分析用户反馈，更新画像理解"""
        feedback_text = "\n".join([
            f"- {fb['date']}: 整体评价{fb['overall']}, 原因: {fb.get('reason', '无')}"
            for fb in feedbacks[-10:]  # 只看最近10条
        ])
        
        prompt = f"""
你是一个用户偏好分析专家。请分析用户的反馈历史。

## 当前用户画像
{current_profile}

## 最近反馈记录
{feedback_text}

## 任务
分析用户反馈，输出对用户的新理解（自然语言）：

1. 用户表达了什么不满？
2. 用户表达了什么喜好？
3. 用户对信息量的偏好变化？
4. 需要注意的特殊要求？

请用自然语言描述，用于更新画像的"AI 学习理解"部分。
"""
        
        return await self.complete(prompt, max_tokens=500, temperature=0.3)
