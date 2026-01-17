"""
简报生成器 - 整合信息抓取、筛选和生成
"""
import asyncio
import json
from collections import Counter
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.llm_client import LLMClient
from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient

logger = setup_logger(__name__)


class DigestGenerator:
    """简报生成器"""

    def __init__(self):
        self.llm_client = LLMClient()
        self.wiseflow_client = WiseFlowClient()
        self.data_dir = Path(settings.DATA_DIR)

    async def generate_digest(self, user_id: int, user_profile: str, test_data: List[Dict] = None) -> Optional[Dict]:
        """
        为用户生成简报

        Args:
            user_id: 用户ID
            user_profile: 用户画像
            test_data: 测试数据（可选）

        Returns:
            {
                "text": "简报文本",
                "top_items": [
                    {"id": "xxx", "title": "xxx", "summary": "xxx", "source": "xxx", "url": "xxx"},
                    ...
                ],
                "stats": {...}
            }
        """
        try:
            # 1. 获取结构化画像数据（用于AI筛选）
            from core.custom_processes.web3digest.core.profile_manager import ProfileManager
            profile_manager = ProfileManager()
            structured_profile = await profile_manager.get_structured_profile(user_id)

            # 构建增强的画像描述（结合结构化数据和文本）
            enhanced_profile = await self._build_enhanced_profile(user_profile, structured_profile)

            # 2. 获取今日原始信息（使用测试数据或正常获取）
            if test_data is not None:
                raw_info = test_data
                logger.info(f"使用测试数据生成简报，共 {len(raw_info)} 条")
            else:
                raw_info = await self._fetch_raw_info()

            if not raw_info:
                logger.warning("没有获取到原始信息，生成友好提示简报")
                # 即使没有原始信息，也生成一个友好的提示简报
                try:
                    total_time_saved = await self._get_total_time_saved(user_id, exclude_today=False)
                except Exception as e:
                    logger.warning(f"获取累计节省时间失败: {e}")
                    total_time_saved = 0.0

                stats = {
                    "sources_count": 0,
                    "raw_count": 0,
                    "selected_count": 0,
                    "filter_rate": "0%",
                    "time_saved": 0,
                    "total_time_saved": total_time_saved
                }

                digest_text = f"""📰 **Web3 每日简报** - {datetime.now().strftime('%Y年%m月%d日')}

⚠️ **今日暂无新信息**

可能原因：
• 信息源正在更新中，请稍后再试
• 今日暂无符合您偏好的新内容

💡 **建议**：
• 您可以稍后使用 /test 命令重新生成简报
• 或调整偏好设置，扩大关注范围

📊 **统计信息**
• 累计节省时间：{stats['total_time_saved']} 小时
"""

                return {
                    "text": digest_text,
                    "top_items": [],
                    "stats": stats
                }

            # 3. AI 筛选个性化内容（使用增强的画像）
            selected_info, filter_stats = await self._filter_info(raw_info, enhanced_profile, user_id)

            # 确保筛选结果不为空（_filter_info 已有兜底逻辑，但这里再检查一次）
            if not selected_info:
                logger.error(f"用户 {user_id} 筛选结果为空，使用原始信息前 {settings.MIN_INFO_PER_USER} 条作为兜底")
                # 最终兜底：直接使用原始信息前 N 条(带评分)
                selected_info = []
                for info in raw_info[:settings.MIN_INFO_PER_USER]:
                    selected_info.append({
                        "id": info.get("id"),
                        "title": info.get("title", ""),
                        "summary": info.get("content", "")[:200],
                        "source": info.get("source", ""),
                        "url": info.get("url", ""),
                        "publish_time": info.get("publish_time", ""),
                        "scores": {
                            "relevance_score": 2.0,
                            "importance_score": 1.0,
                            "freshness_score": 1.0,
                            "total_score": 4.0,
                            "confidence": 0.4
                        },
                        "recommendation_reason": "系统兜底（确保有内容）"
                    })

                if not selected_info:
                    logger.error(f"用户 {user_id} 原始信息也为空，生成友好提示简报")
                    # 即使原始信息为空，也生成一个友好的提示简报
                    try:
                        total_time_saved = await self._get_total_time_saved(user_id, exclude_today=False)
                        # 确保返回的是浮点数
                        if not isinstance(total_time_saved, (int, float)):
                            total_time_saved = float(total_time_saved)
                        total_time_saved = abs(total_time_saved)  # 确保不是负数
                    except Exception as e:
                        logger.warning(f"获取累计节省时间失败: {e}")
                        total_time_saved = 0.0

                    stats = {
                        "sources_count": 0,
                        "raw_count": 0,
                        "selected_count": 0,
                        "filter_rate": "0%",
                        "time_saved": 0,
                        "total_time_saved": total_time_saved
                    }

                    digest_text = f"""📰 **Web3 每日简报** - {datetime.now().strftime('%Y年%m月%d日')}

⚠️ **今日暂无新信息**

可能原因：
• 信息源正在更新中，请稍后再试
• 今日暂无符合您偏好的新内容

💡 **建议**：
• 您可以稍后使用 /test 命令重新生成简报
• 或调整偏好设置，扩大关注范围

📊 **统计信息**
• 累计节省时间：{stats['total_time_saved']} 小时
"""

                    return {
                        "text": digest_text,
                        "top_items": [],
                        "stats": stats
                    }

            # 4. 生成简报和质量指标
            stats = await self._calculate_stats(len(raw_info), len(selected_info), user_id)

            # 确保 stats 中的数值类型正确
            stats = {
                "sources_count": int(stats.get("sources_count", 0)),
                "raw_count": int(stats.get("raw_count", 0)),
                "selected_count": int(stats.get("selected_count", 0)),
                "filter_rate": str(stats.get("filter_rate", "0%")),
                "time_saved": float(stats.get("time_saved", 0)),
                "total_time_saved": float(stats.get("total_time_saved", 0))
            }

            stats["filtered_stats"] = filter_stats  # 添加过滤统计

            # 4.1. 计算简报质量指标
            from core.custom_processes.web3digest.core.quality_analyzer import DigestQualityAnalyzer
            quality_analyzer = DigestQualityAnalyzer()
            digest_quality = await quality_analyzer.calculate_digest_quality(
                user_id=user_id,
                selected_info=selected_info,
                user_profile=structured_profile
            )
            stats["digest_quality"] = digest_quality  # 添加质量指标

            digest_text = await self.llm_client.generate_digest(user_profile, selected_info, stats)

            # 4. 保存统计信息
            await self._save_daily_stats(user_id, stats)

            # 5. 返回结构化数据（包含 Top 3 信息用于单条反馈）
            top_items = selected_info[:3] if selected_info else []

            return {
                "text": digest_text,
                "top_items": top_items,
                "stats": stats
            }

        except Exception as e:
            logger.error(f"生成简报失败 {user_id}: {e}", exc_info=True)
            # 即使发生异常，也返回一个友好的错误提示简报
            try:
                # 尝试获取累计节省时间，如果失败则使用默认值
                try:
                    total_time_saved = await self._get_total_time_saved(user_id, exclude_today=False)
                except Exception as time_error:
                    logger.warning(f"获取累计节省时间失败: {time_error}")
                    total_time_saved = 0.0

                stats = {
                    "sources_count": 0,
                    "raw_count": 0,
                    "selected_count": 0,
                    "filter_rate": "0%",
                    "time_saved": 0,
                    "total_time_saved": total_time_saved
                }

                digest_text = f"""📰 **Web3 每日简报** - {datetime.now().strftime('%Y年%m月%d日')}

⚠️ **简报生成遇到问题**

抱歉，在生成简报时遇到了技术问题。

💡 **建议**：
• 请稍后使用 /test 命令重新生成简报
• 如果问题持续，请联系管理员

📊 **统计信息**
• 累计节省时间：{total_time_saved} 小时
"""

                return {
                    "text": digest_text,
                    "top_items": [],
                    "stats": stats
                }
            except Exception as fallback_error:
                # 如果连兜底都失败了，记录错误并返回一个最简单的简报
                logger.error(f"兜底简报生成也失败: {fallback_error}", exc_info=True)
                digest_text = f"""📰 **Web3 每日简报** - {datetime.now().strftime('%Y年%m月%d日')}

⚠️ **简报生成遇到问题**

抱歉，在生成简报时遇到了技术问题。

💡 **建议**：
• 请稍后使用 /test 命令重新生成简报
• 如果问题持续，请联系管理员
"""

                return {
                    "text": digest_text,
                    "top_items": [],
                    "stats": {
                        "sources_count": 0,
                        "raw_count": 0,
                        "selected_count": 0,
                        "filter_rate": "0%",
                        "time_saved": 0,
                        "total_time_saved": 0.0
                    }
                }

    async def _fetch_raw_info(self, user_id: int = None) -> List[Dict]:
        """获取今日原始信息"""
        # 从 WiseFlow 获取今日抓取的信息
        # 如果指定了 user_id，可以按用户筛选（未来扩展）
        return await self.wiseflow_client.get_today_info()

    def _analyze_filtered_content(self, raw_info: List[Dict], selected_indices: List[int]) -> Dict:
        """分析被过滤的内容类型（Phase 4优化：展示过滤噪音）"""
        filtered_info = []
        selected_set = set(selected_indices)

        for i, info in enumerate(raw_info):
            if i not in selected_set:
                filtered_info.append(info)

        # 分类统计
        category_stats = {
            "meme_promotion": 0,  # Meme币推广
            "price_predictions": 0,  # 价格预测
            "duplicates": 0,  # 重复信息
            "ads": 0,  # 广告/推广
            "irrelevant": 0,  # 不相关内容
            "low_quality": 0  # 低质量内容
        }

        for info in filtered_info:
            title = info.get("title", "").lower()
            content = info.get("content", "").lower()
            text = f"{title} {content}"

            # Meme币推广
            if any(keyword in text for keyword in ["meme", "土狗", "拉盘", "空投", "白送", "免费"]):
                category_stats["meme_promotion"] += 1
            # 价格预测
            elif any(keyword in text for keyword in ["预测", "行情", "价格", "突破", "跌破", "将要"]):
                category_stats["price_predictions"] += 1
            # 广告推广
            elif any(keyword in text for keyword in ["广告", "推广", "合作", "联系", "vx", "qq", "微信"]):
                category_stats["ads"] += 1
            # 低质量/不相关
            else:
                category_stats["irrelevant"] += 1

        return category_stats

    async def _filter_info(self, raw_info: List[Dict], user_profile: str, user_id: int = None) -> tuple[List[Dict], Dict]:
        """使用 AI 批量筛选信息（优化版：一次筛选多条）

        Returns:
            tuple: (selected_info, filter_stats) - 筛选后的信息和统计数据
        """

        # 0. 先按发布时间排序，确保最新内容优先
        from datetime import datetime
        def get_publish_time(item):
            pub_time = item.get("publish_time", "")
            if pub_time:
                try:
                    # 尝试解析各种时间格式
                    if "T" in pub_time:
                        return datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                    else:
                        # 处理其他格式
                        return datetime.strptime(pub_time[:19], "%Y-%m-%d %H:%M:%S")
                except:
                    pass
            # 如果没有发布时间，使用抓取时间
            crawl_time = item.get("crawl_time", "")
            if crawl_time:
                try:
                    return datetime.fromisoformat(crawl_time)
                except:
                    pass
            # 最后使用当前时间
            return datetime.now()
        
        # 按发布时间降序排序（最新的在前）
        raw_info.sort(key=get_publish_time, reverse=True)
        logger.info(f"已按发布时间排序，最新内容优先")

        # 1. 限制输入数量，只取最新的 40 条（避免 token 超限）
        MAX_INPUT = 40
        if len(raw_info) > MAX_INPUT:
            logger.info(f"原始信息 {len(raw_info)} 条，只取最新 {MAX_INPUT} 条进行筛选")
            raw_info = raw_info[:MAX_INPUT]

        # 2. 准备批量筛选的内容（只提取关键信息，减少 token）
        info_list = []
        for i, info in enumerate(raw_info):
            title = info.get("title", "")[:100]  # 限制标题长度
            content = info.get("content", "")[:300]  # 限制内容长度
            source = info.get("source", "")

            info_list.append({
                "index": i,
                "title": title,
                "content": content,
                "source": source
            })

        # 3. 调用 LLM 批量筛选(带评分)
        logger.info(f"开始为用户 {user_id} 筛选个性化内容（带评分），输入 {len(info_list)} 条")

        # 使用新的batch_filter_info_with_scores方法
        selected_with_scores = await self.llm_client.batch_filter_info_with_scores(
            info_list=info_list,
            user_profile=user_profile,
            max_select=settings.MAX_INFO_PER_USER
        )

        logger.info(f"AI 筛选完成，选中 {len(selected_with_scores)} 条内容（含评分）")

        # 4. 使用带评分的筛选结果
        selected = selected_with_scores

        # 5. 确保至少返回 MIN_INFO_PER_USER 条（兜底逻辑-带评分）
        if len(selected) < settings.MIN_INFO_PER_USER:
            logger.info(f"AI 筛选只选出 {len(selected)} 条，补充到最少数量 {settings.MIN_INFO_PER_USER}")
            selected_ids = {s.get("id") for s in selected}
            for info in raw_info:
                if len(selected) >= settings.MIN_INFO_PER_USER:
                    break
                if info.get("id") not in selected_ids:
                    # 为补充的信息添加默认评分
                    selected.append({
                        "id": info.get("id"),
                        "title": info.get("title", ""),
                        "summary": info.get("content", "")[:200],
                        "source": info.get("source", ""),
                        "url": info.get("url", ""),
                        "publish_time": info.get("publish_time", ""),
                        "scores": {
                            "relevance_score": 2.5,
                            "importance_score": 1.5,
                            "freshness_score": 1.0,
                            "total_score": 5.0,
                            "confidence": 0.5
                        },
                        "recommendation_reason": "补充信息（确保最少数量）"
                    })
                    selected_ids.add(info.get("id"))

        # 6. 最终检查：如果还是为空，返回前 N 条（绝对不能返回空-带评分）
        if not selected and raw_info:
            logger.warning(f"筛选结果为空，使用兜底逻辑返回前 {settings.MIN_INFO_PER_USER} 条")
            for info in raw_info[:settings.MIN_INFO_PER_USER]:
                selected.append({
                    "id": info.get("id"),
                    "title": info.get("title", ""),
                    "summary": info.get("content", "")[:200],
                    "source": info.get("source", ""),
                    "url": info.get("url", ""),
                    "publish_time": info.get("publish_time", ""),
                    "scores": {
                        "relevance_score": 2.0,
                        "importance_score": 1.0,
                        "freshness_score": 1.0,
                        "total_score": 4.0,
                        "confidence": 0.4
                    },
                    "recommendation_reason": "兜底信息（确保有内容）"
                })

        # 7. 构建筛选统计信息
        filter_stats = {
            "total": len(raw_info),
            "selected": len(selected),
            "filter_rate": f"{(len(selected) / len(raw_info) * 100):.1f}%" if raw_info else "0%"
        }

        return selected[:settings.MAX_INFO_PER_USER], filter_stats

    async def _build_enhanced_profile(self, text_profile: str, structured_profile: Optional[Dict] = None) -> str:
        """构建增强的画像描述（结合结构化数据和文本，用于 AI 筛选）"""
        if not structured_profile:
            return text_profile

        # 从结构化数据中提取关键信息
        interests = structured_profile.get("interests", [])
        preferences = structured_profile.get("preferences", {})
        feedback_history = structured_profile.get("feedback_history", [])
        ai_understanding = structured_profile.get("ai_understanding", "")

        # 构建结构化偏好描述（用于 AI 筛选的精确 prompt）
        structured_parts = []

        # 1. 关注领域（最重要）
        if interests:
            structured_parts.append(f"【关注领域】{', '.join(interests)}")

        # 2. 内容类型偏好
        if preferences.get("content_types"):
            structured_parts.append(f"【内容类型偏好】{', '.join(preferences['content_types'])}")

        # 3. 偏好信息源
        if preferences.get("sources"):
            structured_parts.append(f"【偏好信息源】{', '.join(preferences['sources'])}")

        # 4. 喜欢的内容
        if preferences.get("likes"):
            structured_parts.append(f"【喜欢的内容】{', '.join(preferences['likes'])}")

        # 5. 不感兴趣的内容（重要：用于排除）
        if preferences.get("dislikes"):
            structured_parts.append(f"【不感兴趣】{', '.join(preferences['dislikes'])}（避免选择此类内容）")

        # 6. AI 理解（从反馈中学习到的）
        if ai_understanding:
            structured_parts.append(f"【AI 理解】{ai_understanding}")

        # 7. 最近的反馈模式（用于优化筛选）
        if feedback_history:
            recent_feedback = feedback_history[-5:]  # 最近5条反馈
            negative_reasons = []
            positive_count = 0
            for fb in recent_feedback:
                if fb.get("overall") == "negative" and fb.get("reason_selected"):
                    negative_reasons.extend(fb["reason_selected"])
                elif fb.get("overall") == "positive":
                    positive_count += 1

            if negative_reasons:
                # 统计最常见的负面反馈原因
                reason_counts = Counter(negative_reasons)
                top_reasons = [reason for reason, _ in reason_counts.most_common(3)]
                structured_parts.append(f"【最近反馈问题】{', '.join(top_reasons)}（避免类似问题）")

            if positive_count > 0:
                structured_parts.append(f"【最近正面反馈】{positive_count}次（保持当前方向）")

        # 组合：结构化数据优先，文本画像作为补充
        if structured_parts:
            enhanced = "## 用户偏好画像（结构化数据）\n" + "\n".join(structured_parts)
            if text_profile:
                enhanced += f"\n\n## 详细描述\n{text_profile}"
        else:
            enhanced = text_profile

        return enhanced

    async def _get_sources_count(self, user_id: int = None) -> int:
        """获取信息源数量"""
        try:
            if user_id:
                # 使用用户自定义的信息源配置
                from core.custom_processes.web3digest.core.source_manager import SourceManager
                source_manager = SourceManager()
                enabled_sources = await source_manager.get_enabled_sources_for_crawl(user_id)
                count = len(enabled_sources)
                return int(count) if count is not None else 20
            else:
                # 使用默认源
                sources = await self.wiseflow_client.get_sources()
                enabled_sources = [s for s in sources if s.get("enabled", True)]
                count = len(enabled_sources)
                return int(count) if count is not None else 20
        except Exception as e:
            logger.warning(f"获取源数量失败，使用默认值: {e}")
            return 20  # 默认值

    async def _get_total_time_saved(self, user_id: int, exclude_today: bool = False) -> float:
        """获取累计节省时间（小时）

        Args:
            user_id: 用户ID
            exclude_today: 是否排除今日的统计（用于计算时避免重复计算）
        """
        total_hours = 0.0
        today_str = date.today().isoformat()

        try:
            # 读取所有历史统计文件
            stats_dir = self.data_dir / "daily_stats"
            if not stats_dir.exists():
                return 0.0

            # 遍历所有统计文件
            for stats_file in stats_dir.glob("*.json"):
                try:
                    # 如果排除今日，跳过今日的统计文件
                    if exclude_today and stats_file.stem == today_str:
                        continue

                    with open(stats_file, 'r', encoding='utf-8') as f:
                        daily_stats = json.load(f)

                    # 获取该用户的统计
                    user_stats = daily_stats.get("users", {}).get(str(user_id), {})
                    if user_stats:
                        time_saved = user_stats.get("time_saved", 0.0)
                        if isinstance(time_saved, (int, float, str)):
                            try:
                                time_saved = float(time_saved)
                                total_hours += time_saved
                            except (ValueError, TypeError):
                                logger.warning(f"无效的时间保存值: {time_saved} (文件: {stats_file})")
                                continue
                        else:
                            logger.warning(f"无效的时间保存类型: {type(time_saved)} (文件: {stats_file})")
                            continue
                except Exception as e:
                    logger.debug(f"读取统计文件失败 {stats_file}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"计算累计节省时间失败: {e}")

        return round(float(total_hours), 1)

    async def _calculate_stats(self, raw_count: int, selected_count: int, user_id: int) -> Dict:
        """计算统计数据"""
        # 确保输入是整数
        raw_count = int(raw_count) if raw_count is not None else 0
        selected_count = int(selected_count) if selected_count is not None else 0
        
        filter_rate = f"{(selected_count/raw_count*100):.1f}%" if raw_count > 0 else "0%"

        # 假设每条信息平均节省 2 分钟
        time_saved_today = round((raw_count - selected_count) * 2 / 60, 1)

        # 获取实际源数量（用户启用的源）
        try:
            sources_count = await self._get_sources_count(user_id)
            sources_count = int(sources_count) if sources_count is not None else 20
        except Exception as e:
            logger.warning(f"获取源数量失败: {e}")
            sources_count = 20

        # 获取历史累计节省时间（不包括今日）
        try:
            historical_total = await self._get_total_time_saved(user_id, exclude_today=True)
            historical_total = float(historical_total) if historical_total is not None else 0.0
        except Exception as e:
            logger.warning(f"获取历史累计时间失败: {e}")
            historical_total = 0.0

        # 累计时间 = 历史累计 + 今日节省
        total_time_saved = round(float(historical_total) + float(time_saved_today), 1)

        return {
            "sources_count": sources_count,
            "raw_count": raw_count,
            "selected_count": selected_count,
            "filter_rate": filter_rate,
            "time_saved": float(time_saved_today),
            "total_time_saved": float(total_time_saved)
        }

    async def _save_daily_stats(self, user_id: int, stats: Dict):
        """保存每日统计"""
        stats_file = self.data_dir / "daily_stats" / f"{date.today().isoformat()}.json"

        # 读取现有统计
        existing_stats = {}
        if stats_file.exists():
            with open(stats_file, 'r', encoding='utf-8') as f:
                existing_stats = json.load(f)

        # 更新用户统计
        if "users" not in existing_stats:
            existing_stats["users"] = {}

        existing_stats["users"][str(user_id)] = stats
        existing_stats["date"] = date.today().isoformat()

        # 保存
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(existing_stats, f, ensure_ascii=False, indent=2)
