"""
简报质量分析器 - 计算整体质量指标
"""
from typing import List, Dict
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)


class DigestQualityAnalyzer:
    """简报质量分析器"""

    def __init__(self):
        pass

    async def calculate_digest_quality(self, user_id: int,
                                      selected_info: List[Dict],
                                      user_profile: Dict) -> Dict:
        """
        计算简报整体质量指标

        Args:
            user_id: 用户ID
            selected_info: 筛选后的信息列表(每条包含scores字段)
            user_profile: 用户结构化画像

        Returns:
            {
                "overall_score": 8.5,              # 整体评分(0-10)
                "personalization_level": 0.85,     # 个性化程度(0-1)
                "diversity_score": 0.75,           # 多样性(0-1)
                "authority_score": 0.90,           # 权威性(0-1)
                "freshness_level": 0.95,           # 新鲜度(0-1)
                "coverage": {
                    "user_interests_covered": 3,
                    "total_interests": 5,
                    "coverage_rate": 0.6,
                    "covered_interests": ["DeFi", "NFT", "Layer2"]
                },
                "quality_distribution": {
                    "high_quality": 7,
                    "medium_quality": 3,
                    "low_quality": 0
                }
            }
        """

        if not selected_info:
            return self._get_empty_quality_metrics()

        try:
            # 1. 整体评分(所有信息总分的平均值)
            total_scores = [
                item.get("scores", {}).get("total_score", 0)
                for item in selected_info
            ]
            overall_score = sum(total_scores) / len(total_scores) if total_scores else 0

            # 2. 个性化程度(相关度评分平均值)
            relevance_scores = [
                item.get("scores", {}).get("relevance_score", 0)
                for item in selected_info
            ]
            personalization_level = (sum(relevance_scores) / len(relevance_scores) / 5.0) if relevance_scores else 0

            # 3. 多样性(来源的多样性)
            sources = [item.get("source", "") for item in selected_info]
            unique_sources = len(set(filter(None, sources)))
            diversity_score = min(unique_sources / 10.0, 1.0)  # 假设10个不同来源为满分

            # 4. 权威性(权威来源占比)
            authority_sources = ['vitalik', 'ethereum', 'uniswap', 'coinbase',
                               'binance', 'consensys', 'a16z', 'paradigm']
            authority_count = sum(
                1 for src in sources
                if any(auth.lower() in src.lower() for auth in authority_sources)
            )
            authority_score = min(authority_count / len(sources), 1.0) if sources else 0

            # 5. 新鲜度(新鲜度评分平均值)
            freshness_scores = [
                item.get("scores", {}).get("freshness_score", 0)
                for item in selected_info
            ]
            freshness_level = (sum(freshness_scores) / len(freshness_scores) / 2.0) if freshness_scores else 0

            # 6. 兴趣覆盖度
            user_interests = user_profile.get("interests", [])
            covered_interests = self._calculate_interest_coverage(selected_info, user_interests)
            coverage_rate = len(covered_interests) / len(user_interests) if user_interests else 0

            # 7. 质量分布
            high_quality = sum(1 for score in total_scores if score >= 8)
            medium_quality = sum(1 for score in total_scores if 6 <= score < 8)
            low_quality = sum(1 for score in total_scores if score < 6)

            return {
                "overall_score": round(overall_score, 1),
                "personalization_level": round(personalization_level, 2),
                "diversity_score": round(diversity_score, 2),
                "authority_score": round(authority_score, 2),
                "freshness_level": round(freshness_level, 2),
                "coverage": {
                    "user_interests_covered": len(covered_interests),
                    "total_interests": len(user_interests),
                    "coverage_rate": round(coverage_rate, 2),
                    "covered_interests": covered_interests
                },
                "quality_distribution": {
                    "high_quality": high_quality,
                    "medium_quality": medium_quality,
                    "low_quality": low_quality
                }
            }

        except Exception as e:
            logger.error(f"计算简报质量失败 user_id={user_id}: {e}")
            return self._get_empty_quality_metrics()

    def _calculate_interest_coverage(self, selected_info: List[Dict],
                                    user_interests: List[str]) -> List[str]:
        """
        计算哪些用户兴趣被覆盖

        Args:
            selected_info: 筛选后的信息列表
            user_interests: 用户兴趣列表

        Returns:
            被覆盖的兴趣列表
        """
        covered = []

        for interest in user_interests:
            for item in selected_info:
                title = item.get("title", "").lower()
                summary = item.get("summary", "").lower()
                combined_text = f"{title} {summary}"

                if interest.lower() in combined_text:
                    covered.append(interest)
                    break  # 找到一个匹配就跳过

        return covered

    def _get_empty_quality_metrics(self) -> Dict:
        """返回空的质量指标"""
        return {
            "overall_score": 0.0,
            "personalization_level": 0.0,
            "diversity_score": 0.0,
            "authority_score": 0.0,
            "freshness_level": 0.0,
            "coverage": {
                "user_interests_covered": 0,
                "total_interests": 0,
                "coverage_rate": 0.0,
                "covered_interests": []
            },
            "quality_distribution": {
                "high_quality": 0,
                "medium_quality": 0,
                "low_quality": 0
            }
        }
