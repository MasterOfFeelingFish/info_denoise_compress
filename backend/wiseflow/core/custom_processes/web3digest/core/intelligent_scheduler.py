"""
Intelligent RSS Scheduler - 基于更新模式的智能调度
"""
import time
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict, deque

from core.custom_processes.web3digest.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SourceMetrics:
    """源的性能指标"""
    url: str
    name: str
    avg_response_time: float = 0.0
    success_rate: float = 1.0
    update_frequency: float = 1.0  # 每小时更新次数
    last_update: Optional[datetime] = None
    last_articles_count: int = 0
    failure_count: int = 0
    total_requests: int = 0

    def to_dict(self) -> dict:
        return {
            'url': self.url,
            'name': self.name,
            'avg_response_time': self.avg_response_time,
            'success_rate': self.success_rate,
            'update_frequency': self.update_frequency,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'last_articles_count': self.last_articles_count,
            'failure_count': self.failure_count,
            'total_requests': self.total_requests
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SourceMetrics':
        return cls(
            url=data['url'],
            name=data['name'],
            avg_response_time=data.get('avg_response_time', 0.0),
            success_rate=data.get('success_rate', 1.0),
            update_frequency=data.get('update_frequency', 1.0),
            last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None,
            last_articles_count=data.get('last_articles_count', 0),
            failure_count=data.get('failure_count', 0),
            total_requests=data.get('total_requests', 0)
        )


class IntelligentScheduler:
    """智能RSS调度器"""

    def __init__(self, metrics_file: str = "intelligent_metrics.json"):
        self.metrics_file = Path(metrics_file)
        self.metrics: Dict[str, SourceMetrics] = {}
        self.response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self.load_metrics()

    def load_metrics(self):
        """加载历史指标"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.metrics = {
                        url: SourceMetrics.from_dict(metrics)
                        for url, metrics in data.items()
                    }
                logger.info(f"Loaded metrics for {len(self.metrics)} sources")
            except Exception as e:
                logger.error(f"Failed to load metrics: {e}")
                self.metrics = {}

    def save_metrics(self):
        """保存指标"""
        try:
            data = {
                url: metrics.to_dict()
                for url, metrics in self.metrics.items()
            }
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Saved metrics")
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def update_source_metrics(self, source: dict, response_time: float,
                            success: bool, articles_count: int):
        """更新源指标"""
        url = source['url']
        name = source['name']

        if url not in self.metrics:
            self.metrics[url] = SourceMetrics(url=url, name=name)

        metrics = self.metrics[url]
        metrics.total_requests += 1

        # 更新响应时间
        self.response_times[url].append(response_time)
        metrics.avg_response_time = sum(self.response_times[url]) / len(self.response_times[url])

        # 更新成功率
        if success:
            metrics.success_rate = (metrics.success_rate * (metrics.total_requests - 1) + 1) / metrics.total_requests
            metrics.failure_count = 0
            metrics.last_articles_count = articles_count
            metrics.last_update = datetime.now()
        else:
            metrics.success_rate = (metrics.success_rate * (metrics.total_requests - 1)) / metrics.total_requests
            metrics.failure_count += 1

        # 更新频率（基于文章数变化）
        if articles_count > 0 and articles_count != metrics.last_articles_count:
            # 有新文章，增加更新频率
            metrics.update_frequency = min(metrics.update_frequency * 1.1, 12)  # 最多每小时12次
        elif articles_count == 0:
            # 无新文章，降低更新频率
            metrics.update_frequency = max(metrics.update_frequency * 0.9, 0.1)  # 最少每小时0.1次

    def should_crawl_source(self, source: dict, current_time: datetime) -> bool:
        """判断是否应该抓取该源"""
        url = source['url']

        if url not in self.metrics:
            # 新源，应该抓取
            return True

        metrics = self.metrics[url]

        # 如果源连续失败多次，暂时跳过
        if metrics.failure_count > 5:
            logger.warning(f"Skipping {source['name']} due to repeated failures")
            return False

        # 基于更新频率计算下次应该抓取的时间
        if metrics.last_update:
            hours_since_update = (current_time - metrics.last_update).total_seconds() / 3600

            # 更新频率越高，间隔越短
            crawl_interval = max(1 / metrics.update_frequency, 0.5)  # 最少30分钟

            if hours_since_update < crawl_interval:
                logger.debug(f"Skipping {source['name']} - updated {hours_since_update:.1f}h ago (interval: {crawl_interval:.1f}h)")
                return False

        return True

    def get_crawl_priority(self, source: dict) -> float:
        """获取源的抓取优先级（数值越高优先级越高）"""
        url = source['url']

        if url not in self.metrics:
            return 1.0  # 新源中等优先级

        metrics = self.metrics[url]

        # 计算优先级（基于多个因素）
        priority = 0.0

        # 1. 更新频率权重 (0-5)
        priority += min(metrics.update_frequency, 5)

        # 2. 成功率权重 (0-3)
        priority += metrics.success_rate * 3

        # 3. 响应时间权重 (0-2) - 响应越快优先级越高
        response_score = max(0, 2 - metrics.avg_response_time / 5)
        priority += response_score

        # 4. 新鲜度权重 (0-1)
        if metrics.last_update:
            hours_ago = (datetime.now() - metrics.last_update).total_seconds() / 3600
            freshness_score = min(hours_ago / 6, 1)  # 6小时内线性增加
            priority += freshness_score

        return priority

    def get_optimized_crawl_list(self, sources: List[dict]) -> List[dict]:
        """获取优化的抓取列表"""
        current_time = datetime.now()

        # 过滤应该抓取的源
        crawl_candidates = []
        for source in sources:
            if source.get('enabled', True) and self.should_crawl_source(source, current_time):
                priority = self.get_crawl_priority(source)
                crawl_candidates.append((source, priority))

        # 按优先级排序
        crawl_candidates.sort(key=lambda x: x[1], reverse=True)

        # 限制并发数量（避免过载）- 提升以配合并发爬虫能力
        max_concurrent = 40
        if len(crawl_candidates) > max_concurrent:
            logger.info(f"Limiting crawl to {max_concurrent} highest priority sources")
            crawl_candidates = crawl_candidates[:max_concurrent]

        return [source for source, _ in crawl_candidates]

    def get_source_recommendations(self) -> List[dict]:
        """获取源优化建议"""
        recommendations = []

        for url, metrics in self.metrics.items():
            if metrics.total_requests < 5:  # 数据不足，跳过
                continue

            # 慢响应源建议
            if metrics.avg_response_time > 5:
                recommendations.append({
                    'type': 'slow_response',
                    'source': metrics.name,
                    'metric': f"{metrics.avg_response_time:.1f}s",
                    'suggestion': 'Consider increasing timeout or checking source health'
                })

            # 低成功率源建议
            if metrics.success_rate < 0.8:
                recommendations.append({
                    'type': 'low_success_rate',
                    'source': metrics.name,
                    'metric': f"{metrics.success_rate*100:.1f}%",
                    'suggestion': 'Source may be unstable, consider disabling temporarily'
                })

            # 低更新频率源建议
            if metrics.update_frequency < 0.5:
                recommendations.append({
                    'type': 'low_update_frequency',
                    'source': metrics.name,
                    'metric': f"{metrics.update_frequency:.1f}/hour",
                    'suggestion': 'Source updates infrequently, can reduce crawl frequency'
                })

            # 高更新频率源建议
            if metrics.update_frequency > 6:
                recommendations.append({
                    'type': 'high_update_frequency',
                    'source': metrics.name,
                    'metric': f"{metrics.update_frequency:.1f}/hour",
                    'suggestion': 'Source updates frequently, consider hourly crawling'
                })

        return recommendations

    def print_stats(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("INTELLIGENT SCHEDULER STATISTICS")
        print("="*60)

        if not self.metrics:
            print("No metrics available yet")
            return

        # 总体统计
        total_sources = len(self.metrics)
        avg_response_time = sum(m.avg_response_time for m in self.metrics.values()) / total_sources
        avg_success_rate = sum(m.success_rate for m in self.metrics.values()) / total_sources
        avg_update_freq = sum(m.update_frequency for m in self.metrics.values()) / total_sources

        print(f"\nOverall Statistics:")
        print(f"  Total sources tracked: {total_sources}")
        print(f"  Average response time: {avg_response_time:.2f}s")
        print(f"  Average success rate: {avg_success_rate*100:.1f}%")
        print(f"  Average update frequency: {avg_update_freq:.1f}/hour")

        # 源排名
        sorted_sources = sorted(self.metrics.items(),
                              key=lambda x: x[1].get_crawl_priority(x[1].__dict__),
                              reverse=True)

        print(f"\nTop 5 Priority Sources:")
        for i, (url, metrics) in enumerate(sorted_sources[:5], 1):
            print(f"  {i}. {metrics.name}")
            print(f"     Priority: {metrics.get_crawl_priority(metrics.__dict__):.2f}")
            print(f"     Success Rate: {metrics.success_rate*100:.1f}%")
            print(f"     Update Freq: {metrics.update_frequency:.1f}/hour")

        # 建议
        recommendations = self.get_source_recommendations()
        if recommendations:
            print(f"\nRecommendations:")
            for rec in recommendations:
                print(f"  - {rec['source']}: {rec['suggestion']} ({rec['type']})")

        print("="*60)