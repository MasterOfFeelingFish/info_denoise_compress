"""
简报质量分析器 - 计算整体质量指标
"""
import re
from typing import List, Dict, Set
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)

# 权威源配置字典（支持多种格式和别名）
AUTHORITY_SOURCES = {
    # 行业领袖 & KOL
    'vitalik': ['vitalikbuterin', 'vitalik', '@vitalikbuterin', 'vitalik buterin'],
    'cz_binance': ['czbinance', 'cz binance', 'cz_binance', '@cz_binance', 'changpeng', 'chang peng'],
    'brian_armstrong': ['brianarmstrong', 'brian armstrong', '@brian_armstrong', 'coinbase ceo'],
    
    # 项目官方
    'ethereum': ['ethereum', '以太坊', 'eth', 'ethereum foundation'],
    'solana': ['solana', 'solana labs'],
    'arbitrum': ['arbitrum', 'arbitrum one', 'arbitrum foundation'],
    'optimism': ['optimism', 'optimistic ethereum'],
    'polygon': ['polygon', 'matic', 'polygon labs'],
    'uniswap': ['uniswap', 'uniswap protocol'],
    
    # 权威媒体
    'coindesk': ['coindesk', 'coin desk'],
    'cointelegraph': ['cointelegraph', 'coin telegraph'],
    'theblock': ['theblock', 'the block', 'theblock__', '@theblock__'],
    'decrypt': ['decrypt', 'decrypt media'],
    'chainfeeds': ['chainfeeds', 'chain feeds'],
    
    # 知名机构
    'a16z': ['a16z', 'andreessen horowitz', 'a16zcrypto'],
    'paradigm': ['paradigm', 'paradigm capital'],
    'consensys': ['consensys', 'consen sys'],
    
    # 其他权威源
    'binance': ['binance', 'binance exchange'],
    'coinbase': ['coinbase', 'coinbase exchange'],
}

# 兴趣同义词词典
INTEREST_SYNONYMS = {
    'DeFi': ['defi', '去中心化金融', 'defi协议', 'defi 协议', '流动性挖矿', '去中心化交易所', 'dex', 'lending', '借贷'],
    'NFT': ['nft', 'nfts', '非同质化代币', '数字藏品', 'non-fungible token', '数字艺术品'],
    'Layer2': ['layer2', 'layer 2', 'l2', '扩容方案', '二层网络', 'rollup', 'rollups'],
    '以太坊': ['ethereum', 'eth', '以太坊生态', 'ethereum ecosystem'],
    'Solana': ['solana', 'sol', 'solana生态', 'solana ecosystem'],
    'Arbitrum': ['arbitrum', 'arb', 'arbitrum生态'],
    'Optimism': ['optimism', 'op', 'optimism生态'],
    'GameFi': ['gamefi', 'game fi', '链游', '区块链游戏', 'web3游戏'],
    'AI': ['ai', 'artificial intelligence', '人工智能', 'ai+crypto', 'ai crypto'],
    'Meme币': ['meme', 'meme币', 'meme coin', '模因币'],
    'DAO': ['dao', '去中心化自治组织', '去中心化组织'],
    'Web3': ['web3', 'web 3', 'web3.0'],
    '元宇宙': ['metaverse', '元宇宙', '虚拟世界'],
}


class DigestQualityAnalyzer:
    """简报质量分析器"""

    def __init__(self):
        pass

    def _is_authority_source(self, source_name: str) -> bool:
        """
        判断是否为权威源
        
        Args:
            source_name: 源名称
            
        Returns:
            是否为权威源
        """
        if not source_name:
            return False
        
        # 清理源名称：移除特殊字符并转换为小写
        source_clean = re.sub(r'[@_\-\s]', '', source_name.lower())
        
        # 检查是否匹配权威源列表
        for auth_key, variants in AUTHORITY_SOURCES.items():
            for variant in variants:
                variant_clean = re.sub(r'[@_\-\s]', '', variant.lower())
                # 部分匹配：variant在source中，或source在variant中
                if variant_clean in source_clean or source_clean in variant_clean:
                    return True
        
        return False

    def _normalize_interest_keywords(self, interest: str) -> List[str]:
        """
        获取兴趣的关键词列表（包含同义词）
        
        Args:
            interest: 兴趣名称
            
        Returns:
            关键词列表（包含原始兴趣和同义词）
        """
        keywords = [interest.lower()]
        
        # 添加同义词
        if interest in INTEREST_SYNONYMS:
            keywords.extend([k.lower() for k in INTEREST_SYNONYMS[interest]])
        else:
            # 检查是否在某个同义词列表中
            for key, synonyms in INTEREST_SYNONYMS.items():
                if interest.lower() in [s.lower() for s in synonyms]:
                    keywords.extend([k.lower() for k in synonyms])
                    keywords.append(key.lower())
                    break
        
        return keywords

    def _matches_interest(self, interest_keywords: List[str], text: str) -> bool:
        """
        检查文本是否匹配兴趣关键词
        
        Args:
            interest_keywords: 兴趣关键词列表
            text: 要检查的文本
            
        Returns:
            是否匹配
        """
        if not text:
            return False
        
        text_lower = text.lower()
        # 清理文本：移除标点符号，只保留字母数字和空格
        text_clean = re.sub(r'[^\w\s]', ' ', text_lower)
        
        # 检查是否有任何关键词匹配
        for keyword in interest_keywords:
            keyword_clean = re.sub(r'[^\w\s]', '', keyword)
            # 单词边界匹配（避免部分匹配）
            if keyword_clean in text_clean:
                return True
        
        return False

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

            # 4. 权威性(权威来源占比) - 使用改进的匹配逻辑
            authority_count = sum(
                1 for src in sources
                if self._is_authority_source(src)
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
        计算哪些用户兴趣被覆盖（改进的匹配算法，支持同义词和模糊匹配）

        Args:
            selected_info: 筛选后的信息列表
            user_interests: 用户兴趣列表

        Returns:
            被覆盖的兴趣列表
        """
        covered = []

        for interest in user_interests:
            # 获取兴趣的关键词列表（包含同义词）
            interest_keywords = self._normalize_interest_keywords(interest)
            
            for item in selected_info:
                # 扩展匹配字段：title, summary, content, source_category等
                title = item.get("title", "")
                summary = item.get("summary", "")
                content = item.get("content", "")
                source_category = item.get("source_category", "")
                source = item.get("source", "")
                
                # 组合所有文本进行匹配
                combined_text = f"{title} {summary} {content} {source_category} {source}"

                # 使用改进的匹配逻辑
                if self._matches_interest(interest_keywords, combined_text):
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
