"""
简报质量分析器 - 计算整体质量指标
"""
import re
from typing import List, Dict, Set
from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)

# 权威源配置字典（支持多种格式和别名）
# 注意：配置中的源名称（如"CoinDesk"、"Cointelegraph"、"ChainFeeds"等）会通过清理和匹配逻辑识别
# 所有配置中的源名称都应该能匹配，包括精确匹配和部分匹配
AUTHORITY_SOURCES = {
    # 行业领袖 & KOL
    'vitalik': ['vitalikbuterin', 'vitalik', '@vitalikbuterin', '@vitalikbuterin', 'vitalik buterin'],
    'cz_binance': ['czbinance', 'cz binance', 'cz_binance', '@cz_binance', '@cz binance', 'changpeng', 'chang peng'],
    'brian_armstrong': ['brianarmstrong', 'brian armstrong', '@brian_armstrong', 'coinbase ceo'],
    
    # 项目官方
    'ethereum': ['ethereum', '以太坊', 'eth', 'ethereum foundation'],
    'solana': ['solana', 'solana labs'],
    'arbitrum': ['arbitrum', 'arbitrum one', 'arbitrum foundation'],
    'optimism': ['optimism', 'optimistic ethereum'],
    'polygon': ['polygon', 'matic', 'polygon labs'],
    'uniswap': ['uniswap', 'uniswap protocol'],
    
    # 权威媒体（注意：配置中的名称必须能匹配）
    # 配置中使用的名称: "CoinDesk", "Cointelegraph", "ChainFeeds", "Decrypt", "The Block", "Foresight News", "律动 BlockBeats"
    'coindesk': ['coindesk', 'coin desk', 'CoinDesk'],  # 添加原始大小写
    'cointelegraph': ['cointelegraph', 'coin telegraph', 'Cointelegraph'],  # 添加原始大小写
    'theblock': ['theblock', 'the block', 'The Block', 'theblock__', '@theblock__', 'TheBlock'],  # 添加各种变体
    'decrypt': ['decrypt', 'Decrypt', 'decrypt media'],
    'chainfeeds': ['chainfeeds', 'ChainFeeds', 'chain feeds', 'chainfeeds.me'],
    'foresight': ['foresight', 'Foresight', 'Foresight News', 'foresight news', 'foresightnews'],
    'blockbeats': ['blockbeats', 'BlockBeats', 'block beats', '律动', '律动 BlockBeats', '律动BlockBeats', 'blockbeatsasia', 'BlockBeatsAsia'],
    'chaincatcher': ['chaincatcher', 'ChainCatcher', 'chain catcher'],
    'techflow': ['techflow', 'TechFlow', 'TechFlow Post'],
    'defirate': ['defirate', 'DeFi Rate', 'defi rate'],
    
    # 知名机构
    'a16z': ['a16z', 'andreessen horowitz', 'a16zcrypto'],
    'paradigm': ['paradigm', 'Paradigm', 'paradigm capital'],
    'consensys': ['consensys', 'Consensys', 'consen sys'],
    
    # 其他权威源
    'binance': ['binance', 'Binance', 'binance exchange'],
    'coinbase': ['coinbase', 'Coinbase', 'coinbase exchange'],
}

# 兴趣同义词词典（扩展版，确保能匹配到相关内容）
INTEREST_SYNONYMS = {
    # DeFi相关（最常见的兴趣）
    'DeFi': ['defi', 'de-fi', '去中心化金融', 'defi协议', 'defi 协议', 'defi protocol', '流动性挖矿', 
             '去中心化交易所', 'dex', 'lending', '借贷', 'swap', 'yield farming', 'yield', 'staking', 
             'protocol', 'protocols', 'aave', 'compound', 'makerdao', 'uniswap'],
    # NFT相关
    'NFT': ['nft', 'nfts', '非同质化代币', '数字藏品', 'non-fungible token', '数字艺术品', 'opensea', 
            'nft market', 'nft marketplace', 'cryptoart', 'digital art'],
    # Layer2相关
    'Layer2': ['layer2', 'layer 2', 'l2', '扩容方案', '二层网络', 'rollup', 'rollups', 'optimistic rollup', 
               'zk rollup', 'zk-rollup', 'sidechain', '侧链', '扩容'],
    # 以太坊相关
    '以太坊': ['ethereum', 'eth', '以太坊生态', 'ethereum ecosystem', '以太坊网络', 'ethereum network', 
              'ethereum 2.0', 'eth2', 'pos', 'proof of stake'],
    # Solana相关
    'Solana': ['solana', 'sol', 'solana生态', 'solana ecosystem', 'solana network', 'solana链'],
    # Arbitrum相关
    'Arbitrum': ['arbitrum', 'arb', 'arbitrum生态', 'arbitrum one', 'arbitrum network', 'arbitrum链'],
    # Optimism相关
    'Optimism': ['optimism', 'op', 'optimism生态', 'optimism network', 'optimism链'],
    # GameFi相关
    'GameFi': ['gamefi', 'game fi', 'game-fi', '链游', '区块链游戏', 'web3游戏', 'web3 game', 
               'crypto game', 'p2e', 'play to earn', 'nft game'],
    # AI相关
    'AI': ['ai', 'artificial intelligence', '人工智能', 'ai+crypto', 'ai crypto', 'ai crypto', 
           'machine learning', 'ml', 'chatgpt', 'gpt', 'ai agent', 'ai bot'],
    # Meme币相关
    'Meme币': ['meme', 'meme币', 'meme coin', '模因币', 'meme token', 'memecoin'],
    # DAO相关
    'DAO': ['dao', '去中心化自治组织', '去中心化组织', 'decentralized autonomous organization', 
            'governance', '治理'],
    # Web3相关
    'Web3': ['web3', 'web 3', 'web3.0', 'web 3.0', 'web3.0'],
    # 元宇宙相关
    '元宇宙': ['metaverse', '元宇宙', '虚拟世界', 'virtual world', 'vr', 'ar', '虚拟现实', '增强现实'],
    # 区块链相关（通用）
    '区块链': ['blockchain', '区块链', 'block chain', '链上', 'on-chain', 'onchain'],
    '比特币': ['bitcoin', 'btc', '比特币', 'bitcoin network'],
    '加密货币': ['crypto', 'cryptocurrency', '加密货币', '数字货币', 'digital currency', 'token', 'coin'],
}


class DigestQualityAnalyzer:
    """简报质量分析器"""

    def __init__(self):
        pass

    def _is_authority_source(self, source_name: str) -> bool:
        """
        判断是否为权威源（改进的匹配逻辑，确保能识别所有配置中的源）
        
        Args:
            source_name: 源名称（如"CoinDesk"、"Cointelegraph"、"The Block"等）
            
        Returns:
            是否为权威源
        """
        if not source_name:
            return False
        
        # 清理源名称：移除特殊字符并转换为小写
        source_original = source_name.strip()
        source_lower = source_original.lower()
        source_clean = re.sub(r'[@_\-\s]', '', source_lower)
        
        # 检查是否匹配权威源列表（优先精确匹配）
        for auth_key, variants in AUTHORITY_SOURCES.items():
            for variant in variants:
                if not variant:
                    continue
                    
                variant_original = variant.strip()
                variant_lower = variant_original.lower()
                variant_clean = re.sub(r'[@_\-\s]', '', variant_lower)
                
                # 多种匹配策略（从最严格到最宽松）：
                # 1. 原始字符串完全匹配（精确匹配，区分大小写）
                if variant_original == source_original:
                    return True
                
                # 2. 原始字符串完全匹配（不区分大小写）
                if variant_lower == source_lower:
                    return True
                
                # 3. 清理后的字符串完全匹配
                if variant_clean == source_clean:
                    return True
                
                # 4. 部分匹配：variant在source中（处理"ChainFeeds"匹配"ChainFeeds"）
                if variant_clean and len(variant_clean) >= 3 and variant_clean in source_clean:
                    return True
                
                # 5. 部分匹配：source在variant中（处理source较短的情况，如"Block"匹配"The Block"）
                if source_clean and len(source_clean) >= 3 and source_clean in variant_clean:
                    return True
                
                # 6. 原始字符串包含匹配（处理"律动 BlockBeats"匹配"BlockBeats"）
                if len(variant_lower) >= 3 and (variant_lower in source_lower or source_lower in variant_lower):
                    return True
        
        return False

    def _normalize_interest_keywords(self, interest: str) -> List[str]:
        """
        获取兴趣的关键词列表（直接使用用户设置的兴趣，同时支持同义词扩展）
        
        Args:
            interest: 兴趣名称（用户实际设置的）
            
        Returns:
            关键词列表（原始兴趣优先，然后是同义词）
        """
        keywords = []
        
        # 优先添加原始兴趣（用户实际设置的）
        keywords.append(interest)  # 保留原始大小写
        keywords.append(interest.lower())  # 小写版本
        keywords.append(interest.strip())  # 去除空格
        
        # 添加同义词（作为补充，不替代原始兴趣）
        if interest in INTEREST_SYNONYMS:
            keywords.extend([k for k in INTEREST_SYNONYMS[interest]])
        else:
            # 检查是否在某个同义词列表中（作为补充）
            for key, synonyms in INTEREST_SYNONYMS.items():
                if interest.lower() in [s.lower() for s in synonyms]:
                    keywords.extend([k for k in synonyms])
                    keywords.append(key)  # 添加主键
                    break
        
        # 去重但保持顺序（原始兴趣优先）
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)
        
        return unique_keywords

    def _matches_interest(self, interest_keywords: List[str], text: str) -> bool:
        """
        检查文本是否匹配兴趣关键词（优先精确匹配用户设置的兴趣）
        
        Args:
            interest_keywords: 兴趣关键词列表（第一个是用户实际设置的兴趣）
            text: 要检查的文本
            
        Returns:
            是否匹配
        """
        if not text or not interest_keywords:
            return False
        
        text_lower = text.lower().strip()
        if not text_lower:
            return False
        
        # 获取用户原始设置的兴趣（第一个关键词）
        original_interest = interest_keywords[0] if interest_keywords else ""
        
        # 清理文本：移除标点符号，只保留字母数字和空格
        text_clean = re.sub(r'[^\w\s]', ' ', text_lower)
        text_words = set(text_clean.split())  # 单词集合，用于快速查找
        
        # 检查是否有任何关键词匹配（优先精确匹配）
        for idx, keyword in enumerate(interest_keywords):
            if not keyword:
                continue
                
            keyword_lower = keyword.lower().strip()
            keyword_clean = re.sub(r'[^\w\s]', '', keyword_lower)
            
            # 如果关键词太短（少于2个字符），跳过
            if len(keyword_clean) < 2:
                continue
            
            # 优先精确匹配用户原始兴趣
            is_original = (idx == 0)
            
            # 多种匹配策略（从严格到宽松）：
            # 1. 原始关键词在原始文本中（完全匹配，处理大小写）
            if keyword_lower in text_lower:
                match_type = "用户原始兴趣" if is_original else "同义词"
                logger.debug(f"✅ 匹配成功（{match_type}完全匹配）: '{keyword}' 在文本中")
                return True
            
            # 2. 清理后的关键词在清理后的文本中（部分匹配）
            if keyword_clean in text_clean:
                match_type = "用户原始兴趣" if is_original else "同义词"
                logger.debug(f"✅ 匹配成功（{match_type}部分匹配）: '{keyword}' (清理后: '{keyword_clean}') 在文本中")
                return True
            
            # 3. 关键词作为单词匹配（单词边界匹配）
            keyword_words = keyword_clean.split() if keyword_clean else []
            for kw_word in keyword_words:
                if len(kw_word) >= 2 and kw_word in text_words:
                    match_type = "用户原始兴趣" if is_original else "同义词"
                    logger.debug(f"✅ 匹配成功（{match_type}单词匹配）: '{keyword}' 中的单词 '{kw_word}' 在文本中")
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
            authority_count = 0
            authority_sources_list = []  # 用于调试
            all_sources_list = []  # 所有源名称（用于调试）
            
            for src in sources:
                if src:
                    all_sources_list.append(src)  # 记录所有源
                    if self._is_authority_source(src):
                        authority_count += 1
                        authority_sources_list.append(src)
            
            # 添加详细调试日志
            if authority_count == 0 and sources:
                unique_sources = list(set(filter(None, sources)))[:10]  # 记录前10个不同的源
                logger.warning(
                    f"用户 {user_id} 未识别到权威源！"
                    f"总源数: {len(sources)}, "
                    f"唯一源数: {len(set(filter(None, sources)))}, "
                    f"示例源名称: {unique_sources}"
                )
            elif authority_count > 0:
                logger.debug(
                    f"用户 {user_id} 识别到 {authority_count}/{len(sources)} 个权威源: {authority_sources_list[:5]}"
                )
            
            authority_score = min(authority_count / len(sources), 1.0) if sources else 0

            # 5. 新鲜度(新鲜度评分平均值)
            freshness_scores = [
                item.get("scores", {}).get("freshness_score", 0)
                for item in selected_info
            ]
            freshness_level = (sum(freshness_scores) / len(freshness_scores) / 2.0) if freshness_scores else 0

            # 6. 兴趣覆盖度
            # 尝试从多个字段获取用户兴趣
            user_interests = user_profile.get("interests", [])
            
            # 如果interests为空，尝试从preferences.likes获取
            if not user_interests:
                preferences = user_profile.get("preferences", {})
                likes = preferences.get("likes", [])
                if likes:
                    user_interests = likes
                    logger.debug(f"用户 {user_id} 从preferences.likes获取兴趣: {user_interests}")
            
            # 如果还是为空，尝试从ai_understanding中提取
            if not user_interests:
                ai_understanding = user_profile.get("ai_understanding", "")
                if ai_understanding:
                    # 尝试从文本中提取兴趣关键词
                    import re
                    interests_match = re.search(r'【关注领域】([^\n【]+)', ai_understanding)
                    if interests_match:
                        interests_text = interests_match.group(1)
                        user_interests = [x.strip() for x in interests_text.split(",") if x.strip()]
                        logger.debug(f"用户 {user_id} 从ai_understanding提取兴趣: {user_interests}")
            
            # 添加调试日志
            if not user_interests:
                logger.warning(
                    f"用户 {user_id} 没有设置兴趣！"
                    f"user_profile keys: {list(user_profile.keys())}, "
                    f"interests字段值: {user_profile.get('interests')}, "
                    f"preferences: {user_profile.get('preferences', {})}"
                )
            else:
                logger.info(f"用户 {user_id} 的兴趣（用于覆盖度计算）: {user_interests}")
            
            covered_interests = self._calculate_interest_coverage(selected_info, user_interests)
            coverage_rate = len(covered_interests) / len(user_interests) if user_interests else 0
            
            # 添加覆盖度调试日志
            if user_interests:
                logger.info(
                    f"用户 {user_id} 兴趣覆盖: {len(covered_interests)}/{len(user_interests)} = {coverage_rate*100:.1f}%, "
                    f"覆盖的兴趣: {covered_interests}"
                )
            
            # 添加覆盖度调试日志
            if user_interests:
                logger.debug(
                    f"用户 {user_id} 兴趣覆盖: {len(covered_interests)}/{len(user_interests)}, "
                    f"覆盖的兴趣: {covered_interests}"
                )

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
        
        if not user_interests:
            logger.debug("用户兴趣列表为空，无法计算覆盖度")
            return covered
        
        if not selected_info:
            logger.debug("选中信息列表为空，无法计算覆盖度")
            return covered

        for interest in user_interests:
            # 获取兴趣的关键词列表（包含同义词）
            interest_keywords = self._normalize_interest_keywords(interest)
            logger.debug(f"尝试匹配兴趣 '{interest}', 关键词列表: {interest_keywords[:5]}")
            
            matched = False
            matched_item_title = None
            
            for idx, item in enumerate(selected_info):
                # 扩展匹配字段：title, summary, content, source_category等
                title = item.get("title", "") or ""
                summary = item.get("summary", "") or ""
                content = item.get("content", "") or ""
                source_category = item.get("source_category", "") or ""
                source = item.get("source", "") or ""
                
                # 组合所有文本进行匹配
                combined_text = f"{title} {summary} {content} {source_category} {source}"
                
                # 记录前几条的文本片段用于调试
                if idx < 3:
                    logger.debug(f"检查第{idx+1}条内容匹配兴趣 '{interest}': title='{title[:50]}', summary='{summary[:30]}'")

                # 使用改进的匹配逻辑
                if self._matches_interest(interest_keywords, combined_text):
                    covered.append(interest)
                    matched = True
                    matched_item_title = title
                    logger.info(f"✅ 兴趣 '{interest}' 匹配成功！关键词: {interest_keywords[:3]}, 匹配内容标题: {title[:80]}")
                    break  # 找到一个匹配就跳过
            
            if not matched:
                # 记录未匹配的详细信息
                sample_titles = [item.get("title", "")[:50] for item in selected_info[:3]]
                logger.warning(
                    f"❌ 兴趣 '{interest}' 未匹配！"
                    f"关键词: {interest_keywords[:5]}, "
                    f"检查了 {len(selected_info)} 条内容, "
                    f"示例标题: {sample_titles}"
                )

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
