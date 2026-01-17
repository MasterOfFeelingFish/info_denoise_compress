"""
LLM 客户端模块 - 封装 OpenAI 兼容 API
"""
import asyncio
import json
import re
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
        批量筛选信息（一次 LLM 调用完成所有筛选，大幅提升速度）- 优化版

        优化点：
        1. 改进信息摘要（包含content内容，不仅仅是title）
        2. 增强Prompt，明确多维度评分策略
        3. 智能兜底机制（基于关键词匹配）
        4. 更精准的用户画像提取

        Args:
            info_list: 信息列表，每条包含 index, title, content, source
            user_profile: 用户画像（增强版，包含结构化数据）
            max_select: 最多选择几条

        Returns:
            选中的信息索引列表
        """
        if not info_list:
            return []

        # 1. 构建更详细的信息摘要列表（包含content预览）
        info_summary = []
        for item in info_list:
            title = item.get('title', '')[:60]  # 限制标题长度
            content_preview = item.get('content', '')[:100]  # 添加内容预览
            source = item.get('source', '')

            # 格式化：[索引] 来源: 标题 - 内容预览
            summary_line = f"[{item['index']}] {source}: {title}"
            if content_preview:
                summary_line += f"\n    内容预览: {content_preview}..."

            info_summary.append(summary_line)

        info_summary_text = "\n\n".join(info_summary)

        # 2. 从用户画像中提取结构化偏好数据
        interests_keywords = []
        dislikes_keywords = []
        likes_keywords = []
        feedback_patterns = []

        # 提取关注领域
        if "【关注领域】" in user_profile:
            interests_match = re.search(r'【关注领域】([^\n【]+)', user_profile)
            if interests_match:
                interests_text = interests_match.group(1)
                interests_keywords = [x.strip() for x in interests_text.split(",") if x.strip()]

        # 提取不感兴趣内容
        if "【不感兴趣】" in user_profile:
            dislikes_match = re.search(r'【不感兴趣】([^\n【]+)', user_profile)
            if dislikes_match:
                dislikes_text = dislikes_match.group(1)
                dislikes_keywords = [x.strip() for x in dislikes_text.replace("（避免选择此类内容）", "").split(",") if x.strip()]

        # 提取喜欢的内容
        if "【喜欢的内容】" in user_profile:
            likes_match = re.search(r'【喜欢的内容】([^\n【]+)', user_profile)
            if likes_match:
                likes_text = likes_match.group(1)
                likes_keywords = [x.strip() for x in likes_text.split(",") if x.strip()]

        # 提取最近反馈问题
        if "【最近反馈问题】" in user_profile:
            feedback_match = re.search(r'【最近反馈问题】([^\n【]+)', user_profile)
            if feedback_match:
                feedback_text = feedback_match.group(1)
                feedback_patterns = [x.strip() for x in feedback_text.replace("（避免类似问题）", "").split(",") if x.strip()]

        # 3. 构建增强的筛选 Prompt（多维度评分策略）
        prompt = f"""你是 Web3 资讯智能筛选专家。请使用**多维度评分策略**，从以下信息中选出最适合用户的 {max_select} 条。

## 用户画像（详细版）
{user_profile}

## 关键偏好总结
- ✅ 关注领域: {', '.join(interests_keywords[:5]) if interests_keywords else '未明确'}
- ✅ 喜欢的内容: {', '.join(likes_keywords[:5]) if likes_keywords else '未明确'}
- ❌ 不感兴趣: {', '.join(dislikes_keywords[:5]) if dislikes_keywords else '无'}
- ⚠️ 最近反馈问题: {', '.join(feedback_patterns[:3]) if feedback_patterns else '无'}

## 待筛选信息（共 {len(info_list)} 条）
{info_summary_text}

## 筛选策略（多维度评分）

### 评分维度（总分10分 = 相关度5分 + 重要性3分 + 新鲜度2分）

1. **相关度评分（0-5分）**
   - 完全匹配用户关注领域：5分
   - 部分匹配用户兴趣：3-4分
   - 行业重要事件（即使不完全匹配）：3分
   - 与用户偏好无关：0-2分

2. **重要性评分（0-3分）**
   - 行业重大事件、突发新闻：3分
   - 重要公告、融资消息：2分
   - 普通资讯：1分
   - 低价值信息（推广、水文）：0分

3. **新鲜度评分（0-2分）**
   - 突发事件、实时动态：2分
   - 当日新闻：1分
   - 旧闻：0分

### 筛选规则
1. **优先选择**：总分 >= 7分 的信息（高度相关 + 重要）
2. **必须包含**：重大事件（重要性=3分），即使相关度不高也要选择
3. **严格排除**：包含用户明确不感兴趣内容的信息（❌ {', '.join(dislikes_keywords[:3]) if dislikes_keywords else '无'}）
4. **避免重复**：主题相似的信息只选一条

### 特别注意
- 最近反馈问题（{', '.join(feedback_patterns[:2]) if feedback_patterns else '无'}）：避免选择类似问题的信息
- 如果用户喜欢某类内容（{', '.join(likes_keywords[:2]) if likes_keywords else '无'}），优先选择

## 输出要求
只返回选中的 {max_select} 个索引号，用逗号分隔。
格式：0,3,5,7,12,15,18,20,25,30
不要返回其他任何说明文字，只返回索引号。"""

        try:
            # 使用更低温度，确保稳定输出
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

            # 如果解析出的索引不足，使用智能兜底机制
            if len(indices) < max_select:
                logger.warning(f"AI 只选出 {len(indices)} 条，少于要求的 {max_select} 条，启用智能兜底")
                indices = await self._smart_fallback(info_list, indices, interests_keywords, dislikes_keywords, max_select)

            logger.info(f"AI 批量筛选完成，选出 {len(indices)} 条（优化版）")
            return indices[:max_select]

        except Exception as e:
            logger.error(f"批量筛选失败: {e}，启用智能兜底机制")
            # 失败时使用智能兜底（不只是返回前N条）
            return await self._smart_fallback(info_list, [], interests_keywords, dislikes_keywords, max_select)

    async def _smart_fallback(self, info_list: List[Dict], existing_indices: List[int],
                              interests: List[str], dislikes: List[str], max_select: int) -> List[int]:
        """
        智能兜底机制 - 基于关键词匹配和来源权威性

        不再简单返回前N条，而是根据用户偏好智能选择
        """
        import re as regex_module

        # 计算每条信息的简单评分
        scored_items = []
        for i, item in enumerate(info_list):
            if i in existing_indices:
                continue  # 跳过已选中的

            score = 0
            title = item.get('title', '').lower()
            content = item.get('content', '').lower()
            source = item.get('source', '').lower()
            combined_text = f"{title} {content} {source}"

            # 1. 关注领域匹配（+3分）
            for interest in interests:
                if interest.lower() in combined_text:
                    score += 3
                    break

            # 2. 不感兴趣内容（-5分，严格排除）
            for dislike in dislikes:
                if dislike.lower() in combined_text:
                    score -= 5
                    break

            # 3. 权威来源加分（+2分）
            authority_sources = ['vitalik', 'ethereum', 'coinbase', 'binance', 'uniswap',
                               'arbitrum', 'optimism', 'polygon', 'solana']
            for auth_source in authority_sources:
                if auth_source in source:
                    score += 2
                    break

            # 4. 重要关键词（+1分）
            important_keywords = ['融资', 'funding', '空投', 'airdrop', '升级', 'upgrade',
                                 '漏洞', 'vulnerability', '公告', 'announcement']
            for keyword in important_keywords:
                if keyword in combined_text:
                    score += 1
                    break

            scored_items.append((i, score))

        # 按评分排序，选择高分项
        scored_items.sort(key=lambda x: x[1], reverse=True)

        # 组合已选中的和新选择的
        result_indices = list(existing_indices)
        for idx, score in scored_items:
            if len(result_indices) >= max_select:
                break
            result_indices.append(idx)

        # 如果还不够，再从剩余的随机补充
        if len(result_indices) < max_select:
            for i in range(len(info_list)):
                if len(result_indices) >= max_select:
                    break
                if i not in result_indices:
                    result_indices.append(i)

        logger.info(f"智能兜底完成，最终选择 {len(result_indices)} 条（评分排序）")
        return result_indices[:max_select]

    async def batch_filter_info_with_scores(self, info_list: List[Dict],
                                            user_profile: str,
                                            max_select: int = 10) -> List[Dict]:
        """
        批量筛选信息并返回详细评分

        优化版: 先使用现有筛选逻辑,再为选中的信息生成详细评分和推荐理由

        Args:
            info_list: 信息列表,每条包含 index, title, content, source
            user_profile: 用户画像(增强版)
            max_select: 最多选择几条

        Returns:
            List[Dict]: 包含评分、推荐理由的信息列表
            [
                {
                    "id": "xxx",
                    "title": "xxx",
                    "summary": "xxx",
                    "source": "xxx",
                    "url": "xxx",
                    "publish_time": "xxx",
                    "scores": {
                        "relevance_score": 4.5,
                        "importance_score": 2.5,
                        "freshness_score": 1.8,
                        "total_score": 8.8,
                        "confidence": 0.88
                    },
                    "recommendation_reason": "匹配您关注的DeFi领域..."
                },
                ...
            ]
        """
        if not info_list:
            return []

        # 1. 先使用现有的batch_filter_info获取选中的索引
        selected_indices = await self.batch_filter_info(info_list, user_profile, max_select)

        if not selected_indices:
            return []

        # 2. 为选中的信息生成详细评分和推荐理由
        scored_items = []
        for idx in selected_indices:
            if 0 <= idx < len(info_list):
                info = info_list[idx]

                # 生成评分和推荐理由
                scores_and_reason = await self._generate_scores_and_reason(
                    info=info,
                    user_profile=user_profile
                )

                scored_items.append({
                    "id": info.get("id", f"item_{idx}"),
                    "title": info.get("title", ""),
                    "summary": info.get("content", "")[:200],
                    "source": info.get("source", ""),
                    "url": info.get("url", ""),
                    "publish_time": info.get("publish_time", ""),
                    "scores": scores_and_reason["scores"],
                    "recommendation_reason": scores_and_reason["reason"]
                })

        logger.info(f"完成评分生成,共 {len(scored_items)} 条信息")
        return scored_items

    async def _generate_scores_and_reason(self, info: Dict, user_profile: str) -> Dict:
        """
        为单条信息生成评分和推荐理由

        Args:
            info: 单条信息
            user_profile: 用户画像

        Returns:
            {
                "scores": {
                    "relevance_score": 4.5,
                    "importance_score": 2.5,
                    "freshness_score": 1.8,
                    "total_score": 8.8,
                    "confidence": 0.88
                },
                "reason": "推荐理由文本"
            }
        """

        prompt = f"""你是Web3资讯评分专家。请对这条信息进行多维度评分。

## 用户画像
{user_profile[:500]}

## 信息内容
标题: {info.get('title', '')}
内容: {info.get('content', '')[:300]}
来源: {info.get('source', '')}

## 评分维度
1. 相关度(0-5分): 与用户兴趣的匹配程度
2. 重要性(0-3分): 信息本身的重要程度
3. 新鲜度(0-2分): 信息的时效性

## 输出要求
返回JSON格式,不要添加任何其他文字:
{{
    "relevance_score": 4.5,
    "importance_score": 2.5,
    "freshness_score": 1.8,
    "reason": "匹配您关注的DeFi领域,来自权威来源,讨论了您关心的TVL变化"
}}"""

        try:
            response = await self.complete(prompt, max_tokens=200, temperature=0.2)

            # 尝试解析JSON
            # 清理可能的markdown代码块标记
            response_clean = response.strip()
            if response_clean.startswith("```"):
                # 移除代码块标记
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean

            result = json.loads(response_clean)

            # 计算总分
            total = result.get("relevance_score", 3.0) + result.get("importance_score", 2.0) + result.get("freshness_score", 1.0)

            return {
                "scores": {
                    "relevance_score": round(result.get("relevance_score", 3.0), 1),
                    "importance_score": round(result.get("importance_score", 2.0), 1),
                    "freshness_score": round(result.get("freshness_score", 1.0), 1),
                    "total_score": round(total, 1),
                    "confidence": round(min(total / 10.0, 1.0), 2)
                },
                "reason": result.get("reason", "AI推荐")[:100]  # 限制理由长度
            }

        except json.JSONDecodeError as e:
            logger.warning(f"评分JSON解析失败: {e}, 响应: {response[:100]}")
            # 返回默认评分
            return {
                "scores": {
                    "relevance_score": 3.0,
                    "importance_score": 2.0,
                    "freshness_score": 1.0,
                    "total_score": 6.0,
                    "confidence": 0.6
                },
                "reason": "AI推荐"
            }
        except Exception as e:
            logger.error(f"生成评分失败: {e}")
            # 返回默认评分
            return {
                "scores": {
                    "relevance_score": 3.0,
                    "importance_score": 2.0,
                    "freshness_score": 1.0,
                    "total_score": 6.0,
                    "confidence": 0.6
                },
                "reason": "AI推荐"
            }

    def _format_filter_stats(self, filter_stats: Dict) -> str:
        """格式化过滤统计信息（Phase 4优化）"""
        if not filter_stats:
            return "• 暂无详细过滤统计"
        
        lines = []
        # 只计算预期的数字类型键，跳过 total, selected, filter_rate
        numeric_keys = ["meme_promotion", "price_predictions", "ads", "irrelevant", "duplicates", "low_quality"]
        total_filtered = sum(int(filter_stats.get(key, 0)) for key in numeric_keys)
        
        if total_filtered == 0:
            return "• 暂无详细过滤统计"
        
        # 定义显示顺序和标签
        stat_labels = {
            "meme_promotion": "Meme币推广",
            "price_predictions": "价格预测",
            "ads": "广告推广",
            "irrelevant": "不相关内容"
        }
        
        # 只显示有统计的类别
        for key, label in stat_labels.items():
            count = int(filter_stats.get(key, 0)) if filter_stats.get(key) is not None else 0
            if count > 0:
                lines.append(f"• {label}: {count}条")
        
        return "\n".join(lines) if lines else "• 暂无详细过滤统计"

    async def generate_digest(self, user_profile: str, info_list: List[Dict], stats: Dict) -> str:
        """生成美化的简报（Telegram 兼容格式）"""
        from datetime import datetime
        import re
        
        def escape_md(text: str) -> str:
            """转义 Markdown 特殊字符（完整版）"""
            # 按顺序转义，反斜杠必须先转义
            text = text.replace('\\', '\\\\')  # 反斜杠
            text = text.replace('_', '\\_')    # 下划线
            text = text.replace('*', '\\*')    # 星号
            text = text.replace('[', '\\[')    # 左方括号
            text = text.replace(']', '\\]')    # 右方括号
            text = text.replace('(', '\\(')    # 左圆括号
            text = text.replace(')', '\\)')    # 右圆括号
            text = text.replace('`', '\\`')    # 反引号
            text = text.replace('~', '\\~')    # 波浪号
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

🔍 监控 {int(stats.get('sources_count', 5))} 个信息源
📥 扫描 {int(stats.get('raw_count', 0))} 条原始信息
✨ 精选 {int(stats.get('selected_count', 0))} 条 ({str(stats.get('filter_rate', '5%'))})
⏱ 今日节省 ~{float(stats.get('time_saved', 1))}小时 阅读时间
📈 累计节省 {float(stats.get('total_time_saved', 0))}小时

{'━' * 25}

🛡️ 为您过滤的噪音
{'─' * 25}

{self._format_filter_stats(stats.get('filtered_stats', {}))}

{'━' * 25}

💬 这份简报对您有帮助吗？
点击下方按钮反馈 👇
"""
        
        return digest.strip()
    
    def _deduplicate_info(self, info_list: List[Dict]) -> List[Dict]:
        """去重：避免语义重复的信息（优化版，O(n)复杂度）"""
        if len(info_list) <= 1:
            return info_list

        # 优化的去重：基于标题相似度
        unique_list = []
        seen_exact_titles = set()  # 完全匹配的标题（快速查找）
        seen_normalized_titles = []  # 规范化后的标题（用于包含关系检查）

        for info in info_list:
            title = info.get('title', '').lower().strip()
            # 移除常见标点符号
            title_clean = ''.join(c for c in title if c.isalnum() or c.isspace()).strip()

            if not title_clean:
                continue

            # 快速检查：完全匹配（O(1)）
            if title_clean in seen_exact_titles:
                continue

            # 检查包含关系（仅对长标题，避免误判）
            is_duplicate = False
            if len(title_clean) > 10:
                # 只检查前5个标题，避免O(n²)
                for seen_title in seen_normalized_titles[-5:]:
                    if title_clean in seen_title or seen_title in title_clean:
                        is_duplicate = True
                        break

            if not is_duplicate:
                unique_list.append(info)
                seen_exact_titles.add(title_clean)
                seen_normalized_titles.append(title_clean)

        return unique_list
    
    async def analyze_feedback(self, current_profile: str, feedbacks: List[Dict]) -> str:
        """分析用户反馈，更新画像理解"""
        # 只取最近5条反馈，减少token消耗
        recent_feedbacks = feedbacks[-5:]
        
        # 简化反馈格式
        feedback_text = "\n".join([
            f"- {fb.get('overall', '')}: {', '.join(fb.get('reason_selected', []))}"
            for fb in recent_feedbacks
        ])
        
        # 简化画像，只取关键部分
        profile_summary = current_profile[:500] + "..." if len(current_profile) > 500 else current_profile
        
        prompt = f"""分析用户反馈，更新理解：

画像：{profile_summary}

最近反馈：
{feedback_text}

基于反馈总结用户偏好（100字以内）："""
        
        # 设置超时并减少token
        import asyncio
        try:
            result = await asyncio.wait_for(
                self.complete(prompt, max_tokens=200, temperature=0.3),
                timeout=10.0  # 10秒超时
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("反馈分析超时，使用默认结果")
            return "用户偏好持续学习中"
