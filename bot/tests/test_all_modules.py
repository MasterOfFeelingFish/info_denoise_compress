"""
Automated Test Script for Web3 Daily Digest Bot

Tests all functionality against the test case document.
Run with: python -m pytest tests/test_all_modules.py -v
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============ Module 1: User Registration Tests ============

class TestUserRegistration:
    """TC-1.1, TC-1.2: User registration and Telegram binding"""

    def test_create_new_user(self, tmp_data_dir):
        """TC-1.1: New user can be created"""
        from utils.json_storage import create_user, get_user

        user = create_user(
            telegram_id="123456789",
            username="testuser",
            first_name="Test"
        )

        assert user is not None
        assert user["telegram_id"] == "123456789"
        assert user["username"] == "testuser"
        assert "created" in user

        # Verify retrieval
        retrieved = get_user("123456789")
        assert retrieved is not None
        assert retrieved["telegram_id"] == "123456789"

    def test_existing_user_returns_same(self, tmp_data_dir):
        """TC-1.2: Existing user is recognized"""
        from utils.json_storage import create_user, get_user

        # Create user first time
        user1 = create_user(telegram_id="111222333")

        # Create same user again
        user2 = create_user(telegram_id="111222333")

        assert user1["id"] == user2["id"]


# ============ Module 2: AI Preference Collection Tests ============

class TestPreferenceCollection:
    """TC-2.1-2.4: AI dialogue preference collection"""

    def test_profile_storage(self, tmp_data_dir):
        """TC-2.3: Preferences are correctly stored"""
        from utils.json_storage import create_user, save_user_profile, get_user_profile

        # Create user
        create_user(telegram_id="987654321")

        # Save profile
        profile = """[User Type]
DeFi-focused trader

[Focus Areas]
- DeFi protocols (Uniswap, Aave, Compound)
- Layer 2 solutions (Arbitrum, Optimism)
- On-chain data analysis

[Content Preferences]
- News and analysis
- Whale movements
- 10-15 items per day"""

        result = save_user_profile("987654321", profile)
        assert result is True

        # Verify retrieval
        retrieved = get_user_profile("987654321")
        assert retrieved is not None
        assert "DeFi" in retrieved
        assert "Layer 2" in retrieved


# ============ Module 3: Source Management Tests ============

class TestSourceManagement:
    """TC-3.1-3.4: Information source management"""

    def test_get_source_list(self):
        """TC-3.1: View preset sources"""
        from services.rss_fetcher import get_source_list

        sources = get_source_list()

        assert "twitter" in sources
        assert "websites" in sources
        assert len(sources["twitter"]) > 0
        assert len(sources["websites"]) > 0

    def test_add_twitter_source(self):
        """TC-3.2: Add custom Twitter account"""
        from services.rss_fetcher import add_source, get_source_list, remove_source

        # Add new Twitter source
        result = add_source("twitter", "@TestAccount", "https://rss.app/feeds/test")
        assert result is True

        # Verify added
        sources = get_source_list()
        assert "@TestAccount" in sources["twitter"]

        # Cleanup
        remove_source("twitter", "@TestAccount")

    def test_add_website_source(self):
        """TC-3.3: Add custom website"""
        from services.rss_fetcher import add_source, get_source_list, remove_source

        # Add new website
        result = add_source("websites", "Test Site", "https://example.com/rss")
        assert result is True

        # Verify added
        sources = get_source_list()
        assert "Test Site" in sources["websites"]

        # Cleanup
        remove_source("websites", "Test Site")

    def test_remove_source(self):
        """TC-3.4: Remove source"""
        from services.rss_fetcher import add_source, remove_source, get_source_list

        # Add then remove
        add_source("twitter", "@TempAccount", "https://temp.url")
        result = remove_source("twitter", "@TempAccount")
        assert result is True

        sources = get_source_list()
        assert "@TempAccount" not in sources["twitter"]

    def test_validate_twitter_handle(self):
        """TC-3.2: Validate Twitter handle format"""
        import asyncio
        from services.rss_fetcher import validate_twitter_handle

        # Valid handles
        result = asyncio.run(validate_twitter_handle("@VitalikButerin"))
        assert result["valid"] is True
        assert result["handle"] == "@VitalikButerin"

        result = asyncio.run(validate_twitter_handle("lookonchain"))
        assert result["valid"] is True
        assert result["handle"] == "@lookonchain"

        # Invalid handles
        result = asyncio.run(validate_twitter_handle("@invalid handle with spaces"))
        assert result["valid"] is False

        result = asyncio.run(validate_twitter_handle("@toolonghandlethatexceedslimit"))
        assert result["valid"] is False

    def test_add_custom_twitter_source(self):
        """TC-3.2: Add custom Twitter with validation"""
        import asyncio
        from services.rss_fetcher import add_custom_source, remove_source

        # Valid addition
        result = asyncio.run(add_custom_source("twitter", "@TestUser123"))
        assert result["success"] is True

        # Cleanup
        remove_source("twitter", "@TestUser123")

        # Invalid addition
        result = asyncio.run(add_custom_source("twitter", "invalid handle!!!"))
        assert result["success"] is False

    def test_invalid_source_handling(self):
        """TC-3.4: Invalid source handling"""
        import asyncio
        from services.rss_fetcher import add_custom_source

        # Invalid Twitter handle
        result = asyncio.run(add_custom_source("twitter", "@"))
        assert result["success"] is False
        assert "Invalid" in result["message"] or "无效" in result["message"]

        # Website without URL
        result = asyncio.run(add_custom_source("websites", "Test Site", ""))
        assert result["success"] is False
        assert "URL" in result["message"] or "RSS" in result["message"]

        # Invalid URL format
        result = asyncio.run(add_custom_source("websites", "Test", "not-a-url"))
        assert result["success"] is False


# ============ Module 4: RSS Fetcher Tests ============

class TestRSSFetcher:
    """TC-4.1-4.4: Information fetching engine"""

    def test_generate_item_id(self):
        """TC-4.4: Deduplication via unique IDs"""
        from services.rss_fetcher import generate_item_id

        entry = {"id": "12345", "link": "https://example.com/post"}
        id1 = generate_item_id(entry, "source1")
        id2 = generate_item_id(entry, "source1")

        # Same entry should produce same ID
        assert id1 == id2

        # Different source should produce different ID
        id3 = generate_item_id(entry, "source2")
        assert id1 != id3

    def test_parse_published_date(self):
        """Test date parsing from RSS entries"""
        from services.rss_fetcher import parse_published_date

        # RFC 2822 format
        entry1 = {"published": "Mon, 01 Jan 2024 12:00:00 GMT"}
        date1 = parse_published_date(entry1)
        assert date1 is not None

        # ISO format
        entry2 = {"updated": "2024-01-01T12:00:00Z"}
        date2 = parse_published_date(entry2)
        assert date2 is not None

    def test_extract_summary(self):
        """Test summary extraction and cleaning"""
        from services.rss_fetcher import extract_summary

        entry = {"summary": "<p>This is <b>HTML</b> content</p>"}
        summary = extract_summary(entry)

        assert "<p>" not in summary
        assert "<b>" not in summary
        assert "HTML" in summary

    def test_extract_twitter_author(self):
        """Test Twitter author extraction from tweet links"""
        from services.rss_fetcher import extract_twitter_author

        # Valid Twitter/X links
        assert extract_twitter_author("https://x.com/VitalikButerin/status/123") == "@VitalikButerin"
        assert extract_twitter_author("https://twitter.com/elonmusk/status/456") == "@elonmusk"
        assert extract_twitter_author("https://x.com/caborunda") == "@caborunda"

        # Non-Twitter links should return empty
        assert extract_twitter_author("https://example.com/article") == ""
        assert extract_twitter_author("https://coindesk.com/news/123") == ""

        # Edge cases
        assert extract_twitter_author("") == ""
        assert extract_twitter_author("https://x.com/i/status/123") == ""  # 'i' is a special path
        assert extract_twitter_author("https://x.com/search") == ""  # 'search' is a special path


# ============ Module 4.5: Twitter Author Display Tests ============

class TestTwitterAuthorDisplay:
    """Test Twitter author display in report generation"""

    def test_format_item_with_twitter_author(self):
        """Twitter item should display author"""
        from services.report_generator import format_single_item

        item = {
            "title": "ETH breaks $4000",
            "summary": "Market sentiment is bullish",
            "source": "Twitter Bundle",
            "author": "@VitalikButerin",
            "link": "https://x.com/VitalikButerin/status/123",
            "section": "must_read",
            "reason": "Matches your DeFi interest"
        }

        formatted = format_single_item(item, 1, "zh")

        assert "@VitalikButerin" in formatted
        assert "📣" in formatted

    def test_format_item_without_author(self):
        """Non-Twitter item should not display author line"""
        from services.report_generator import format_single_item

        item = {
            "title": "Bitcoin analysis",
            "summary": "Technical analysis report",
            "source": "CoinDesk",
            "author": "",  # No author
            "link": "https://coindesk.com/article",
            "section": "recommended",
            "reason": "Industry news"
        }

        formatted = format_single_item(item, 1, "zh")

        assert "📣" not in formatted

    def test_format_item_with_invalid_author(self):
        """Item with non-Twitter author format should not display author"""
        from services.report_generator import format_single_item

        item = {
            "title": "News article",
            "summary": "Summary text",
            "source": "Some Source",
            "author": "John Doe",  # Not a Twitter handle (no @)
            "link": "https://example.com",
            "section": "other"
        }

        formatted = format_single_item(item, 1, "zh")

        assert "📣" not in formatted
        assert "John Doe" not in formatted


# ============ Module 5: AI Content Filtering Tests ============

class TestSmartTruncate:
    """Task 1: 智能摘要截断测试"""
    
    def test_short_text_unchanged(self):
        """T1-01: 短文本（< 200字）原样返回"""
        from services.content_filter import smart_truncate
        
        text = "这是一段短文本"
        result = smart_truncate(text, 200)
        assert result == text
    
    def test_empty_text(self):
        """空文本返回空字符串"""
        from services.content_filter import smart_truncate
        
        assert smart_truncate("", 200) == ""
        assert smart_truncate(None, 200) is None
    
    def test_truncate_at_period_chinese(self):
        """T1-02: 在中文句号处截断"""
        from services.content_filter import smart_truncate
        
        text = "这是第一句话。这是第二句话。这是第三句话，后面还有很多内容继续写下去超过限制。"
        result = smart_truncate(text, 30)
        
        # 应该在句号处截断
        assert result.endswith("。") or result.endswith("...")
        assert len(result) <= 35  # 允许一点余量
    
    def test_truncate_at_period_english(self):
        """T1-02: 在英文句号处截断"""
        from services.content_filter import smart_truncate
        
        text = "This is sentence one. This is sentence two. This is a very long sentence that goes on and on."
        result = smart_truncate(text, 50)
        
        assert ". " in result or result.endswith(".")
    
    def test_truncate_at_comma_when_no_period(self):
        """T1-03: 没有句号时在逗号处截断"""
        from services.content_filter import smart_truncate
        
        text = "这是一段没有句号的长文本，逗号分隔，继续写更多内容，还要继续写更多"
        result = smart_truncate(text, 30)
        
        # 没有句号，应该在逗号处截断并加省略号
        assert result.endswith("...")
    
    def test_truncate_no_punctuation(self):
        """T1-04: 纯文本无标点时直接截断加省略号"""
        from services.content_filter import smart_truncate
        
        text = "这是一段纯文本没有任何标点符号只是一直在写下去很长很长的内容"
        result = smart_truncate(text, 20)
        
        assert result.endswith("...")
        assert len(result) <= 24  # 20 + "..."
    
    def test_real_case_eth_price(self):
        """T1-05: 真实案例 - ETH 价格截断"""
        from services.content_filter import smart_truncate
        
        text = "以太坊跌破 2800 美元，最低触及 2787 美元，创新低，市场恐慌情绪蔓延。分析师认为短期内可能继续下探。"
        result = smart_truncate(text, 50)
        
        # 不应该在逗号后直接截断成残句
        assert not result.endswith("，")
        # 应该是完整句子或有省略号
        assert result.endswith("。") or result.endswith("...") or result.endswith("？") or result.endswith("！")


class TestSummaryDuplicate:
    """Task 2: 标题摘要去重测试"""
    
    def test_blockbeats_duplicate(self):
        """T2-01: BlockBeats 格式的重复检测"""
        from services.report_generator import is_summary_duplicate
        
        title = "过去12小时全网爆仓5.83亿美元"
        summary = "BlockBeats消息，1月26日，过去12小时全网爆仓5.83亿美元，其中多单爆仓4.2亿美元"
        
        assert is_summary_duplicate(title, summary) is True
    
    def test_starts_with_title(self):
        """T2-02: 摘要以标题开头"""
        from services.report_generator import is_summary_duplicate
        
        title = "BTC突破10万美元"
        summary = "据悉，BTC今日突破10万美元大关，创下历史新高"
        
        # 这种情况摘要有增量信息，不应该判定为重复
        result = is_summary_duplicate(title, summary)
        # 因为 "BTC突破10万美元" 在清理后不完全在摘要开头，应该不重复
        assert result is False
    
    def test_not_duplicate_different_content(self):
        """T2-03: 不同内容不应判定为重复"""
        from services.report_generator import is_summary_duplicate
        
        title = "市场分析"
        summary = "分析师认为当前市场处于上升通道，建议关注主流币种表现"
        
        assert is_summary_duplicate(title, summary) is False
    
    def test_empty_summary(self):
        """T2-04: 空摘要不应报错"""
        from services.report_generator import is_summary_duplicate
        
        title = "重大消息"
        summary = ""
        
        assert is_summary_duplicate(title, summary) is False
    
    def test_exact_duplicate(self):
        """完全相同的标题和摘要"""
        from services.report_generator import is_summary_duplicate
        
        title = "ETH 价格突破 3000 美元"
        summary = "ETH 价格突破 3000 美元"
        
        assert is_summary_duplicate(title, summary) is True
    
    def test_prefix_stripped_duplicate(self):
        """带有日期前缀的重复"""
        from services.report_generator import is_summary_duplicate
        
        title = "某交易所宣布上线新币种"
        summary = "1月26日，某交易所宣布上线新币种，首日交易量突破1亿美元"
        
        # 去掉日期前缀后，摘要以标题开头
        assert is_summary_duplicate(title, summary) is True
    
    def test_short_title_not_duplicate(self):
        """短标题不应过度匹配"""
        from services.report_generator import is_summary_duplicate
        
        title = "BTC"
        summary = "BTC 在过去 24 小时内上涨 5%，带动整体市场情绪回暖"
        
        # 标题太短，不应判定为重复
        assert is_summary_duplicate(title, summary) is False


class TestContentFiltering:
    """TC-5.1-5.3: AI intelligent filtering"""

    def test_summarize_feedbacks(self):
        """Test feedback summarization for AI context"""
        from services.content_filter import summarize_feedbacks

        feedbacks = [
            {"overall": "positive"},
            {"overall": "negative", "reason_selected": ["Too much"]},
            {"overall": "negative", "reason_text": "Missing DeFi news"},
        ]

        summary = summarize_feedbacks(feedbacks)

        assert "1 positive" in summary
        assert "2 negative" in summary

    def test_categorize_filtered_content(self):
        """TC-5.2: Content categorization"""
        import asyncio
        from services.content_filter import categorize_filtered_content

        items = [
            {"title": "DeFi protocol update", "importance": "high"},
            {"title": "NFT collection launch", "importance": "medium"},
            {"title": "Layer2 scaling news", "importance": "high"},
            {"title": "Whale trading activity", "importance": "medium"},
        ]

        categories = asyncio.run(categorize_filtered_content(items))

        assert "top_stories" in categories
        assert len(categories["top_stories"]) >= 1


# ============ Module 6: Report Generation Tests ============

class TestReportGeneration:
    """TC-6.1-6.4: AI report generation"""

    def test_report_structure(self):
        """TC-6.1: Report structure completeness"""
        from services.report_generator import (
            format_top_stories,
            format_category_section,
            format_metrics_section,
        )

        # Test top stories format
        top_stories = [
            {"title": "Test Title", "summary": "Test summary", "source": "Test", "link": "http://test.com"}
        ]
        formatted = format_top_stories(top_stories)
        assert "TOP STORIES" in formatted or "今日必看" in formatted
        assert "Test Title" in formatted

        # Test category section
        items = [{"title": "Item 1", "source": "Source1"}]
        cat_section = format_category_section("defi", items)
        assert "DeFi" in cat_section or "Defi" in cat_section

        # Test metrics section
        metrics = format_metrics_section(50, 200, 15)
        assert "Sources" in metrics or "信息源" in metrics
        assert "Scanned" in metrics or "扫描" in metrics
        assert "Selected" in metrics or "精选" in metrics

    def test_split_report_for_telegram(self):
        """Test report splitting for Telegram limit"""
        from services.report_generator import split_report_for_telegram

        # Short report - no split
        short = "Short report"
        parts = split_report_for_telegram(short)
        assert len(parts) == 1

        # Long report - should split
        long = "Section\n\n" * 500
        parts = split_report_for_telegram(long, max_length=100)
        assert len(parts) > 1

    def test_empty_report_generation(self):
        """Test empty report when no content"""
        from services.report_generator import generate_empty_report

        report = generate_empty_report()
        assert "No updates" in report or "没有符合" in report
        assert "/settings" in report


# ============ Module 8: Feedback Collection Tests ============

class TestFeedbackCollection:
    """TC-8.1-8.4: User feedback collection"""

    def test_save_feedback(self, tmp_data_dir):
        """TC-8.4: Feedback data storage"""
        from utils.json_storage import create_user, save_feedback, get_user_feedbacks

        # Create user first
        create_user(telegram_id="feedback_test_user")

        # Save feedback
        result = save_feedback(
            telegram_id="feedback_test_user",
            overall_rating="negative",
            reason_selected=["Too much", "Not relevant"],
            reason_text="Need more DeFi content",
            item_feedbacks=[
                {"item_id": "item1", "feedback": "like"},
                {"item_id": "item2", "feedback": "dislike"},
            ]
        )
        assert result is True

        # Verify retrieval
        feedbacks = get_user_feedbacks("feedback_test_user", days=1)
        assert len(feedbacks) >= 1
        assert feedbacks[0]["overall"] == "negative"
        assert "Too much" in feedbacks[0]["reason_selected"]
        assert len(feedbacks[0]["item_feedbacks"]) == 2


# ============ Module 9: Feedback Learning Loop Tests ============

class TestFeedbackLearning:
    """TC-9.1-9.3: Feedback learning loop"""

    def test_format_feedbacks_for_ai(self):
        """TC-9.1: AI feedback analysis formatting"""
        from services.profile_updater import format_feedbacks_for_ai

        feedbacks = [
            {
                "date": "2024-01-01",
                "time": "10:00",
                "overall": "negative",
                "reason_selected": ["Too much"],
                "item_feedbacks": [
                    {"feedback": "like"},
                    {"feedback": "dislike"},
                ]
            }
        ]

        formatted = format_feedbacks_for_ai(feedbacks)
        assert "NEGATIVE" in formatted
        assert "Too much" in formatted
        assert "1 liked" in formatted
        assert "1 disliked" in formatted

    def test_analyze_feedback_trends(self, tmp_data_dir):
        """TC-9.1: Feedback trend analysis"""
        import asyncio
        from utils.json_storage import create_user, save_feedback
        from services.profile_updater import analyze_feedback_trends

        # Create user and add feedbacks
        create_user(telegram_id="trend_test_user")

        # Add multiple feedbacks
        for _ in range(3):
            save_feedback("trend_test_user", "positive")
        save_feedback("trend_test_user", "negative", reason_selected=["Too much"])

        trends = asyncio.run(analyze_feedback_trends("trend_test_user", days=1))

        assert trends["total_feedbacks"] == 4
        assert trends["positive_count"] == 3
        assert trends["negative_count"] == 1


# ============ Module 10: Language Adaptation Tests ============

class TestLanguageAdaptation:
    """Test language adaptation functionality"""

    def test_normalize_language_code_chinese(self):
        """Chinese language codes should normalize to 'zh'"""
        from utils.language import normalize_language_code
        
        assert normalize_language_code("zh") == "zh"
        assert normalize_language_code("zh-hans") == "zh"
        assert normalize_language_code("zh-hant") == "zh"
        assert normalize_language_code("zh-CN") == "zh"
        assert normalize_language_code("zh-TW") == "zh"

    def test_normalize_language_code_english(self):
        """English language codes should normalize to 'en'"""
        from utils.language import normalize_language_code
        
        assert normalize_language_code("en") == "en"
        assert normalize_language_code("en-US") == "en"
        assert normalize_language_code("en-GB") == "en"

    def test_normalize_language_code_fallback(self):
        """Unsupported languages should fall back to 'en'"""
        from utils.language import normalize_language_code
        
        assert normalize_language_code("fr") == "en"
        assert normalize_language_code("de") == "en"
        assert normalize_language_code(None) == "en"
        assert normalize_language_code("") == "en"

    def test_get_ui_locale_zh(self):
        """Chinese UI locale should have Chinese strings"""
        from locales.ui_strings import get_ui_locale
        
        ui = get_ui_locale("zh")
        assert ui["menu_view_digest"] == "查看今日简报"
        assert ui["feedback_helpful"] == "有帮助"

    def test_get_ui_locale_en(self):
        """English UI locale should have English strings"""
        from locales.ui_strings import get_ui_locale
        
        ui = get_ui_locale("en")
        assert ui["menu_view_digest"] == "View Today's Digest"
        assert ui["feedback_helpful"] == "Helpful"

    def test_get_ui_locale_fallback(self):
        """Unknown language should fall back to English"""
        from locales.ui_strings import get_ui_locale
        
        ui = get_ui_locale("xyz")
        assert ui["menu_view_digest"] == "View Today's Digest"

    def test_create_user_with_language(self, tmp_data_dir):
        """Create user should store language"""
        from utils.json_storage import create_user, get_user_language
        
        user = create_user(
            telegram_id="lang_test_user",
            username="langtest",
            first_name="Lang",
            language="ja"
        )
        
        assert user["language"] == "ja"
        assert get_user_language("lang_test_user") == "ja"

    def test_get_user_language_default(self, tmp_data_dir):
        """Non-existent user should return default language"""
        from utils.json_storage import get_user_language
        
        lang = get_user_language("nonexistent_user")
        assert lang == "zh"


# ============ Module 11: Twitter Source Addition Tests ============

class TestValidateRssUrl:
    """Test RSS URL validation function"""

    @pytest.mark.asyncio
    async def test_valid_rss_url(self):
        """Valid RSS URL should return success with title and entries count"""
        from services.rss_fetcher import validate_rss_url
        
        # Use a known working RSS feed
        result = await validate_rss_url("https://cointelegraph.com/rss")
        
        assert result["valid"] is True
        assert "title" in result
        assert "entries_count" in result
        assert result["entries_count"] > 0
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_invalid_format_no_http(self):
        """URL without http should be rejected"""
        from services.rss_fetcher import validate_rss_url
        
        result = await validate_rss_url("@VitalikButerin")
        
        assert result["valid"] is False
        assert "http" in result["error"]

    @pytest.mark.asyncio
    async def test_non_rss_webpage(self):
        """Non-RSS webpage should be rejected"""
        from services.rss_fetcher import validate_rss_url
        
        result = await validate_rss_url("https://example.com")
        
        assert result["valid"] is False
        assert "RSS" in result["error"] or "有效" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_url(self):
        """Non-existent URL should be rejected"""
        from services.rss_fetcher import validate_rss_url
        
        result = await validate_rss_url("https://rss.app/feeds/nonexistent12345.xml")
        
        assert result["valid"] is False
        assert result["error"] is not None


class TestTwitterSourceGuide:
    """Test Twitter source addition guide and flow"""

    def test_start_add_twitter_returns_correct_state(self):
        """start_add_twitter should return AWAITING_TWITTER_ADD state"""
        from handlers.sources import AWAITING_TWITTER_ADD
        
        # Verify state constant exists
        assert AWAITING_TWITTER_ADD is not None
        assert isinstance(AWAITING_TWITTER_ADD, int)

    def test_twitter_tutorial_in_conversation_handler(self):
        """twitter_tutorial callback should be in ConversationHandler states"""
        from handlers.sources import get_sources_handler, AWAITING_TWITTER_ADD
        from telegram.ext import CallbackQueryHandler
        
        handler = get_sources_handler()
        state_handlers = handler.states.get(AWAITING_TWITTER_ADD, [])
        callback_patterns = [
            h.pattern.pattern for h in state_handlers
            if isinstance(h, CallbackQueryHandler) and hasattr(h, 'pattern')
        ]
        
        assert "^twitter_tutorial$" in callback_patterns

    def test_sources_add_twitter_callback_in_conversation(self):
        """sources_add_twitter should be in conversation handler entry points"""
        from handlers.sources import get_sources_handler
        from telegram.ext import CallbackQueryHandler
        
        handler = get_sources_handler()
        # Filter for CallbackQueryHandler only (CommandHandler has no pattern)
        callback_handlers = [ep for ep in handler.entry_points if isinstance(ep, CallbackQueryHandler)]
        entry_patterns = [ep.pattern.pattern for ep in callback_handlers]
        
        assert "^sources_add_twitter$" in entry_patterns


class TestHandleTwitterAdd:
    """Test handle_twitter_add function logic"""

    @pytest.mark.asyncio
    async def test_non_url_input_rejected(self):
        """Non-URL input should be rejected with helpful message"""
        from handlers.sources import handle_twitter_add
        from telegram import Update, Message, User, Chat
        from telegram.ext import ContextTypes
        from unittest.mock import AsyncMock, MagicMock
        
        # Mock update
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        
        mock_chat = MagicMock(spec=Chat)
        mock_chat.id = 12345
        
        mock_message = MagicMock(spec=Message)
        mock_message.text = "@VitalikButerin"  # Not a URL
        mock_message.reply_text = AsyncMock()
        
        mock_update = MagicMock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.message = mock_message
        
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.user_data = {"_active_text_conv": "sources"}
        
        # Call function
        result = await handle_twitter_add(mock_update, mock_context)
        
        # Verify rejection
        mock_message.reply_text.assert_called_once()
        call_args = mock_message.reply_text.call_args
        assert "格式不正确" in call_args[0][0] or "http" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_valid_rss_url_accepted(self, tmp_data_dir):
        """Valid RSS URL should be accepted and saved"""
        from handlers.sources import handle_twitter_add
        from telegram import Update, Message, User, Chat
        from telegram.ext import ContextTypes
        from unittest.mock import AsyncMock, MagicMock, patch
        
        # Mock update
        mock_user = MagicMock(spec=User)
        mock_user.id = 99999
        
        mock_message = MagicMock(spec=Message)
        mock_message.text = "https://cointelegraph.com/rss"
        mock_message.reply_text = AsyncMock()
        
        mock_update = MagicMock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.message = mock_message
        
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.user_data = {"_active_text_conv": "sources"}
        
        # Mock track_event to avoid side effects
        with patch("handlers.sources.track_event"):
            result = await handle_twitter_add(mock_update, mock_context)
        
        # Verify acceptance
        mock_message.reply_text.assert_called_once()
        call_args = mock_message.reply_text.call_args
        # Should contain success message
        assert "成功" in call_args[0][0] or "添加" in call_args[0][0]


# ============ Fixtures ============

@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Create temporary data directory for tests"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create subdirectories
    (data_dir / "profiles").mkdir()
    (data_dir / "feedback").mkdir()
    (data_dir / "daily_stats").mkdir()
    (data_dir / "raw_content").mkdir()

    # Patch config
    monkeypatch.setattr("config.DATA_DIR", str(data_dir))
    monkeypatch.setattr("config.USERS_FILE", str(data_dir / "users.json"))
    monkeypatch.setattr("config.PROFILES_DIR", str(data_dir / "profiles"))
    monkeypatch.setattr("config.FEEDBACK_DIR", str(data_dir / "feedback"))
    monkeypatch.setattr("config.DAILY_STATS_DIR", str(data_dir / "daily_stats"))
    monkeypatch.setattr("config.RAW_CONTENT_DIR", str(data_dir / "raw_content"))

    # Also patch in json_storage module
    import utils.json_storage as storage
    monkeypatch.setattr(storage, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(storage, "USERS_FILE", str(data_dir / "users.json"))
    monkeypatch.setattr(storage, "PROFILES_DIR", str(data_dir / "profiles"))
    monkeypatch.setattr(storage, "FEEDBACK_DIR", str(data_dir / "feedback"))
    monkeypatch.setattr(storage, "DAILY_STATS_DIR", str(data_dir / "daily_stats"))
    monkeypatch.setattr(storage, "RAW_CONTENT_DIR", str(data_dir / "raw_content"))

    return data_dir


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
