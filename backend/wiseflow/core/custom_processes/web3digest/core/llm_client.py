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
    
    async def batch_filter_info(self, info_list: List[Dict], user_profile: str, max_select: int = 10) -> List[int]:
        """
        批量筛选信息（一次 LLM 调用完成所有筛选，大幅提升速度）
        
        Args:
            info_list: 信息列表，每条包含 index, title, content, source
            user_profile: 用户画像
            max_select: 最多选择几条
        
        Returns:
            选中的信息索引列表
        """
        # 构建信息摘要列表
        info_summary = "\n".join([
            f"[{item['index']}] {item['source']}: {item['title'][:60]}"
            for item in info_list
        ])
        
        prompt = f"""你是 Web3 资讯筛选专家。请根据用户画像，从以下信息中选出最相关、最有价值的 {max_select} 条。

## 用户画像
{user_profile}

## 待筛选信息
{info_summary}

## 任务
从上述信息中选出最符合用户兴趣的 {max_select} 条，返回它们的索引号。
优先选择：
1. 与用户关注领域直接相关的
2. 重大事件、突发新闻
3. 大额链上操作（如果用户关注）
4. 空投、Meme 币信息（如果用户关注）

## 输出格式
只返回选中的索引号，用逗号分隔，例如：0,3,5,7,12
不要返回其他任何内容。"""
        
        try:
            response = await self.complete(prompt, max_tokens=100, temperature=0.1)
            
            # 解析返回的索引
            indices = []
            for part in response.replace(" ", "").split(","):
                try:
                    idx = int(part.strip())
                    if 0 <= idx < len(info_list):
                        indices.append(idx)
                except ValueError:
                    continue
            
            logger.info(f"AI 批量筛选完成，选出 {len(indices)} 条")
            return indices[:max_select]
            
        except Exception as e:
            logger.error(f"批量筛选失败: {e}")
            # 失败时返回前 N 条
            return list(range(min(max_select, len(info_list))))
    
    async def generate_digest(self, user_profile: str, info_list: List[Dict], stats: Dict) -> str:
        """生成美化的简报（Telegram 兼容格式）"""
        from datetime import datetime
        import re
        
        def escape_md(text: str) -> str:
            """转义 Markdown 特殊字符"""
            # 只转义可能导致问题的字符
            text = text.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            return text
        
        def safe_title(text: str, max_len: int = 50) -> str:
            """安全处理标题"""
            text = text[:max_len] if len(text) > max_len else text
            return escape_md(text)
        
        # 去重
        unique_info_list = self._deduplicate_info(info_list)
        
        # 获取当前日期
        today = datetime.now().strftime("%Y年%m月%d日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
        
        # 分类整理信息
        top_info = unique_info_list[:3] if unique_info_list else []
        other_info = unique_info_list[3:7] if len(unique_info_list) > 3 else []
        
        # 构建今日必看部分（含可点击链接）
        top_section = ""
        emoji_list = ["🔥", "⚡", "💎"]
        for i, info in enumerate(top_info):
            emoji = emoji_list[i] if i < len(emoji_list) else "📌"
            title = safe_title(info.get('title', ''), 45)
            summary = escape_md(info.get('summary', '')[:80]) if info.get('summary') else ""
            source = info.get('source', '未知')
            url = info.get('url', '')
            
            top_section += f"{emoji} {title}\n"
            if summary:
                top_section += f"   {summary}\n"
            # 添加可点击链接
            if url and url != '#':
                top_section += f"   📍 {source} | [查看原文]({url})\n\n"
            else:
                top_section += f"   📍 {source}\n\n"
        
        # 构建更多资讯部分（含可点击链接）
        more_section = ""
        if other_info:
            for info in other_info:
                title = safe_title(info.get('title', ''), 35)
                source = info.get('source', '')
                url = info.get('url', '')
                if url and url != '#':
                    more_section += f"• [{title}]({url}) ({source})\n"
                else:
                    more_section += f"• {title} ({source})\n"
        
        # 直接生成格式化简报
        digest = f"""
┏━━━━━━━━━━━━━━━━━━━━━━┓
   🌐 Web3 每日精选
   📅 {today} {weekday}
┗━━━━━━━━━━━━━━━━━━━━━━┛

🎯 今日必看
{'─' * 25}

{top_section if top_section else "今日暂无重大新闻\n"}
"""
        
        if more_section:
            digest += f"""📰 更多资讯
{'─' * 25}

{more_section}
"""
        
        digest += f"""📊 价值统计
{'─' * 25}

🔍 监控 {stats.get('sources_count', 5)} 个信息源
📥 扫描 {stats.get('raw_count', 0)} 条原始信息
✨ 精选 {stats.get('selected_count', 0)} 条 ({stats.get('filter_rate', '5%')})
⏱ 今日节省 ~{stats.get('time_saved', 1)}小时 阅读时间
📈 累计节省 {stats.get('total_time_saved', 0)}小时

{'━' * 25}

💬 这份简报对您有帮助吗？
点击下方按钮反馈 👇
"""
        
        return digest.strip()
    
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
