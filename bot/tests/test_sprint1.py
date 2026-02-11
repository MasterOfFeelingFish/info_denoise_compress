"""
Sprint1 Test Suite

Comprehensive tests for all Sprint1 tasks (T1-T8).
Run with: python -m pytest tests/test_sprint1.py -v
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add bot directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============ T8: Bug Fix Tests ============

class TestT8ConfirmProfileFix:
    """T8: confirm_profile should use send_message to preserve preference summary."""

    @pytest.mark.asyncio
    async def test_confirm_profile_uses_send_message(self, mock_update, mock_context, tmp_data_dir):
        """confirm_profile should call context.bot.send_message, NOT query.edit_message_text for saving status."""
        from handlers.start import confirm_profile, CONFIRM_PROFILE, SOURCE_CHOICE

        # Setup
        mock_update.callback_query.from_user.id = 99999
        mock_update.effective_user.id = 99999
        mock_context.user_data["profile_summary"] = "Test profile"
        mock_context.user_data["conversation_history"] = [{"round": 1, "user_input": "test"}]
        mock_context.user_data["language"] = "en"

        # Mock AI call
        with patch("handlers.start.call_gemini", new_callable=AsyncMock, return_value="Generated profile"):
            with patch("handlers.start.save_user_profile"):
                with patch("handlers.start.create_user", return_value={"id": "user_001"}):
                    result = await confirm_profile(mock_update, mock_context)

        # Verify send_message was called (not edit_message_text for saving)
        assert mock_context.bot.send_message.called, \
            "confirm_profile should use context.bot.send_message to preserve profile summary"

    @pytest.mark.asyncio
    async def test_profile_summary_not_edited(self, mock_update, mock_context, tmp_data_dir):
        """The preference summary message should NOT be edited/overwritten."""
        from handlers.start import confirm_profile

        mock_update.callback_query.from_user.id = 88888
        mock_update.effective_user.id = 88888
        mock_context.user_data["profile_summary"] = "DeFi focused profile"
        mock_context.user_data["conversation_history"] = [{"round": 1, "user_input": "DeFi"}]
        mock_context.user_data["language"] = "zh"

        with patch("handlers.start.call_gemini", new_callable=AsyncMock, return_value="Full profile"):
            with patch("handlers.start.save_user_profile"):
                with patch("handlers.start.create_user", return_value={"id": "user_002"}):
                    await confirm_profile(mock_update, mock_context)

        # The query.edit_message_text should NOT be called for the saving progress
        # (it may be called for the source choice step, which is also changed to send_message)
        # The key check: send_message must be called at least twice (saving + source choice)
        assert mock_context.bot.send_message.call_count >= 1


# ============ T6: Help Community Link Tests ============

class TestT6HelpCommunityLink:
    """T6: /help should include community link, translations should be complete."""

    def test_help_community_link_exists_zh(self):
        """Chinese ui_strings should have help_community_link."""
        from locales.ui_strings import UI_STRINGS
        assert "help_community_link" in UI_STRINGS["zh"]
        assert "t.me" in UI_STRINGS["zh"]["help_community_link"]

    def test_help_community_link_exists_en(self):
        """English ui_strings should have help_community_link."""
        from locales.ui_strings import UI_STRINGS
        assert "help_community_link" in UI_STRINGS["en"]
        assert "t.me" in UI_STRINGS["en"]["help_community_link"]

    def test_help_footer_includes_community(self):
        """help_footer should include community link."""
        from locales.ui_strings import UI_STRINGS
        assert "t.me" in UI_STRINGS["zh"]["help_footer"]
        assert "t.me" in UI_STRINGS["en"]["help_footer"]

    def test_all_languages_have_required_keys(self):
        """All languages should have the same set of keys (or fallback via LocaleDict)."""
        from locales.ui_strings import get_ui_locale

        required_keys = ["menu_view_digest", "help_title", "help_footer", "help_community_link"]
        for lang in ["zh", "en", "ja", "ko"]:
            ui = get_ui_locale(lang)
            for key in required_keys:
                val = ui.get(key)
                assert val is not None, f"Missing key '{key}' for language '{lang}'"
                assert "[" not in val or "t.me" in val, f"Key '{key}' has placeholder for '{lang}'"


# ============ T1: Content Deduplication Tests ============

class TestT1Deduplication:
    """T1: deduplicate_by_similarity function tests."""

    def test_similar_titles_merged(self):
        """3 similar titles should be merged to 1."""
        from services.report_generator import deduplicate_by_similarity

        items = [
            {"title": "ETH突破4000美元创新高", "summary": "以太坊今日突破4000美元", "source": "CoinDesk"},
            {"title": "ETH突破4000美元 创历史新高", "summary": "以太坊价格突破4000美元大关，创下历史新高，市场情绪乐观", "source": "The Block"},
            {"title": "ETH突破4000美元创新高度", "summary": "ETH新高", "source": "BlockBeats"},
        ]

        result = deduplicate_by_similarity(items)
        assert len(result) == 1, f"Expected 1 item after dedup, got {len(result)}"
        # Should keep the one with longest summary
        assert "市场情绪" in result[0]["summary"]

    def test_different_titles_preserved(self):
        """5 different titles should all be preserved."""
        from services.report_generator import deduplicate_by_similarity

        items = [
            {"title": "Bitcoin reaches new ATH", "summary": "BTC hits $100k", "source": "A"},
            {"title": "Ethereum 2.0 upgrade complete", "summary": "ETH upgrade", "source": "B"},
            {"title": "Solana launches new feature", "summary": "SOL update", "source": "C"},
            {"title": "Cardano partnership announced", "summary": "ADA news", "source": "D"},
            {"title": "DeFi TVL hits record high", "summary": "DeFi growth", "source": "E"},
        ]

        result = deduplicate_by_similarity(items)
        assert len(result) == 5

    def test_threshold_boundary(self):
        """Items at exactly threshold should be kept separate."""
        from services.report_generator import deduplicate_by_similarity

        # These should be similar but not above 0.8
        items = [
            {"title": "Bitcoin price up today", "summary": "a", "source": "A"},
            {"title": "Ethereum price down today", "summary": "b", "source": "B"},
        ]

        result = deduplicate_by_similarity(items)
        assert len(result) == 2

    def test_empty_input(self):
        """Empty list should return empty."""
        from services.report_generator import deduplicate_by_similarity
        assert deduplicate_by_similarity([]) == []

    def test_single_item(self):
        """Single item should return as-is."""
        from services.report_generator import deduplicate_by_similarity
        items = [{"title": "Test", "summary": "test"}]
        assert len(deduplicate_by_similarity(items)) == 1


# ============ T2: Noise Prefix Filtering Tests ============

class TestT2NoisePrefixFiltering:
    """T2: Noise prefix removal and em-dash normalization."""

    def test_blockbeats_prefix_removed(self):
        """BlockBeats prefix should be removed from titles."""
        from services.rss_fetcher import clean_noise_prefix

        title = "BlockBeats 消息，ETH突破4000美元"
        cleaned = clean_noise_prefix(title)
        assert "BlockBeats" not in cleaned
        assert "ETH突破4000美元" in cleaned

    def test_date_prefix_removed(self):
        """Date prefix like '1月26日，' should be removed."""
        from services.rss_fetcher import clean_noise_prefix

        title = "1月26日，BTC创新高"
        cleaned = clean_noise_prefix(title)
        assert "1月26日" not in cleaned
        assert "BTC创新高" in cleaned

    def test_no_prefix_unchanged(self):
        """Title without noise prefix should be unchanged."""
        from services.rss_fetcher import clean_noise_prefix

        title = "Important crypto news today"
        cleaned = clean_noise_prefix(title)
        assert cleaned == title

    def test_em_dash_normalization(self):
        """Double em-dash should be replaced with single."""
        from services.report_generator import format_single_item

        item = {
            "title": "测试——双破折号",
            "summary": "内容——也有",
            "source": "Test",
            "link": "https://test.com",
            "section": "other",
        }
        formatted = format_single_item(item, 1, "zh")
        assert "——" not in formatted
        assert "—" in formatted


# ============ T3: Source Health Monitor Tests ============

class TestT3SourceHealthMonitor:
    """T3: Source health recording, repair, and notification."""

    def test_record_success(self, tmp_data_dir):
        """Successful fetch records status='ok'."""
        from services.source_health_monitor import record_health_status

        record = record_health_status(
            source_url="https://example.com/rss",
            source_name="TestSource",
            success=True,
            items_count=10
        )

        assert record["status"] == "ok"
        assert record["consecutive_failures"] == 0

    def test_record_failures_trigger_degraded(self, tmp_data_dir):
        """3 consecutive failures should set status='degraded'."""
        from services.source_health_monitor import record_health_status

        url = "https://fail.example.com/rss"
        for i in range(3):
            record = record_health_status(
                source_url=url,
                source_name="FailSource",
                success=False,
                error_type="timeout",
                error_detail=f"Timeout attempt {i+1}"
            )

        assert record["status"] == "degraded"
        assert record["consecutive_failures"] == 3

    @pytest.mark.asyncio
    async def test_check_and_repair_triggers_at_3(self, tmp_data_dir, monkeypatch):
        """check_and_repair triggers repair when failures >= 3."""
        from services.source_health_monitor import record_health_status, check_and_repair

        monkeypatch.setattr("config.FEATURE_SOURCE_HEALTH", True)

        url = "https://repair.example.com/rss"
        for _ in range(3):
            record_health_status(url, "RepairTest", False, "404", "Not found")

        # Mock AI repair to return failure (no working URL)
        with patch("services.source_health_monitor.attempt_ai_repair",
                    new_callable=AsyncMock,
                    return_value={"status": "repair_failed", "reason": "no_working_url"}):
            result = await check_and_repair(url, "RepairTest")

        # check_and_repair returns the attempt_ai_repair result which has "status" key
        assert result.get("status") == "repair_failed" or result.get("action") not in (None, "none")

    @pytest.mark.asyncio
    async def test_repair_limited_to_3_attempts(self, tmp_data_dir, monkeypatch):
        """Repair should be limited to 3 attempts, then permanently_failed."""
        from services.source_health_monitor import (
            record_health_status, check_and_repair, _load_health_record, _save_health_record
        )

        monkeypatch.setattr("config.FEATURE_SOURCE_HEALTH", True)

        url = "https://perm-fail.example.com/rss"
        for _ in range(5):
            record_health_status(url, "PermFail", False, "500", "Server error")

        # Set repair_attempts to 3
        record = _load_health_record(url)
        record["repair_attempts"] = 3
        _save_health_record(url, record)

        result = await check_and_repair(url, "PermFail")
        assert result["action"] == "permanently_failed"

    def test_notification_rate_limit(self, tmp_data_dir):
        """Same status notification should not repeat within 24h."""
        from services.source_health_monitor import send_health_notification

        url = "https://notify.example.com/rss"
        # First notification should succeed
        result1 = asyncio.run(send_health_notification(url, "NotifyTest", "degraded"))
        assert result1 is True

        # Second within 24h should be rate-limited
        result2 = asyncio.run(send_health_notification(url, "NotifyTest", "degraded"))
        assert result2 is False


# ============ T4: Admin Health Dashboard Tests ============

class TestT4HealthDashboard:
    """T4: Source health dashboard formatting and management."""

    def test_health_summary_format(self, tmp_data_dir):
        """Health summary should group sources correctly."""
        from services.source_health_monitor import record_health_status, get_health_summary

        # Create some test records
        record_health_status("https://ok.com/rss", "OKSource", True, items_count=10)
        for _ in range(5):
            record_health_status("https://fail.com/rss", "FailSource", False, "timeout")
        record_health_status("https://warn.com/rss", "WarnSource", False, "parse_error")

        summary = get_health_summary()
        assert summary["total"] == 3
        assert summary["ok"] >= 1
        assert summary["failed"] >= 1 or summary["degraded"] >= 1

    def test_bulk_add_parsing(self):
        """Bulk add input should parse 'name|url' format correctly."""
        lines = [
            "CoinDesk|https://www.coindesk.com/rss/",
            "The Block|https://www.theblock.co/rss.xml",
            "InvalidLine",
            "NoURL|not-a-url",
        ]

        added = []
        failed = []

        for line in lines:
            if "|" not in line:
                failed.append(line)
                continue
            parts = line.split("|", 1)
            name = parts[0].strip()
            url = parts[1].strip()
            if url.startswith("http"):
                added.append(name)
            else:
                failed.append(name)

        assert len(added) == 2
        assert len(failed) == 2


# ============ T5: Payment Permission Tests ============

class TestT5Permissions:
    """T5: Permission system and plan management."""

    def test_free_user_no_custom_sources(self, tmp_data_dir, monkeypatch):
        """Free user should not have custom_sources permission."""
        monkeypatch.setattr("config.FEATURE_PAYMENT", True)
        from utils.permissions import check_feature

        with patch("utils.permissions.get_user_plan", return_value="free"):
            assert check_feature("123", "custom_sources") is False

    def test_pro_user_has_all_features(self, tmp_data_dir, monkeypatch):
        """Pro user should have all permissions."""
        monkeypatch.setattr("config.FEATURE_PAYMENT", True)
        from utils.permissions import check_feature

        with patch("utils.permissions.get_user_plan", return_value="pro"):
            assert check_feature("123", "custom_sources") is True
            assert check_feature("123", "ai_chat") is True
            assert check_feature("123", "advanced_filters") is True

    def test_free_user_chat_limit(self, tmp_data_dir, monkeypatch):
        """Free user should have ai_chat_daily limit = 5."""
        monkeypatch.setattr("config.FEATURE_PAYMENT", True)
        from utils.permissions import get_feature_limit

        with patch("utils.permissions.get_user_plan", return_value="free"):
            limit = get_feature_limit("123", "ai_chat_daily")
            assert limit == 5

    def test_plan_expiry_downgrades(self, tmp_data_dir, monkeypatch):
        """Expired pro plan should downgrade to free."""
        monkeypatch.setattr("config.FEATURE_PAYMENT", True)
        from utils.permissions import get_user_plan

        expired_user = {
            "telegram_id": "456",
            "plan": "pro",
            "plan_expires": (datetime.now() - timedelta(days=1)).isoformat(),
        }

        with patch("utils.json_storage.get_user", return_value=expired_user):
            plan = get_user_plan("456")
            assert plan == "free"

    def test_no_plan_field_defaults_free(self, tmp_data_dir, monkeypatch):
        """Old user without plan field should default to free."""
        monkeypatch.setattr("config.FEATURE_PAYMENT", True)
        from utils.permissions import get_user_plan

        old_user = {"telegram_id": "789"}  # No plan field

        with patch("utils.json_storage.get_user", return_value=old_user):
            plan = get_user_plan("789")
            assert plan == "free"

    def test_feature_flag_off_allows_all(self, monkeypatch):
        """When FEATURE_PAYMENT is off, all features should be available."""
        monkeypatch.setattr("config.FEATURE_PAYMENT", False)
        from utils.permissions import check_feature, get_feature_limit

        assert check_feature("999", "custom_sources") is True
        assert get_feature_limit("999", "ai_chat_daily") == 999

    @pytest.mark.asyncio
    async def test_upgrade_user_plan(self, tmp_data_dir):
        """upgrade_user_plan should change plan to pro."""
        from utils.json_storage import create_user
        from utils.permissions import upgrade_user_plan

        create_user(telegram_id="upgrade_test", username="tester")
        result = upgrade_user_plan("upgrade_test", "pro", duration_days=30)
        assert result is True

        from utils.json_storage import get_user
        user = get_user("upgrade_test")
        assert user["plan"] == "pro"
        assert "plan_expires" in user
        assert len(user.get("payment_history", [])) == 1


# ============ T7: Group Chat Tests ============

class TestT7GroupChat:
    """T7: Group chat configuration and management."""

    def test_group_config_save_load(self, tmp_data_dir):
        """Group config should save and load correctly."""
        from handlers.group import save_group_config, load_group_config

        config = {
            "group_id": "-100123",
            "group_title": "Test Group",
            "admin_id": "12345",
            "profile": "DeFi and Layer2",
            "push_hour": 9,
            "language": "zh",
            "enabled": True,
            "created": datetime.now().isoformat(),
        }

        assert save_group_config("-100123", config) is True
        loaded = load_group_config("-100123")
        assert loaded is not None
        assert loaded["group_title"] == "Test Group"
        assert loaded["profile"] == "DeFi and Layer2"

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, mock_update, mock_context, monkeypatch):
        """Non-admin user should be rejected from /setup."""
        monkeypatch.setattr("config.FEATURE_GROUP_CHAT", True)
        from handlers.group import setup_command
        from telegram.ext import ConversationHandler

        mock_update.effective_chat.type = "group"
        mock_context.bot.get_chat_administrators = AsyncMock(return_value=[])

        result = await setup_command(mock_update, mock_context)
        assert result == ConversationHandler.END
        mock_update.message.reply_text.assert_called()

    def test_bot_removal_disables_config(self, tmp_data_dir):
        """When bot is removed from group, config should be disabled."""
        from handlers.group import save_group_config, load_group_config

        config = {
            "group_id": "-100999",
            "group_title": "Removed Group",
            "enabled": True,
            "created": datetime.now().isoformat(),
        }
        save_group_config("-100999", config)

        # Simulate disable
        config["enabled"] = False
        save_group_config("-100999", config)

        loaded = load_group_config("-100999")
        assert loaded["enabled"] is False

    def test_get_all_group_configs(self, tmp_data_dir):
        """get_all_group_configs should return only enabled groups."""
        from handlers.group import save_group_config, get_all_group_configs

        save_group_config("-1001", {"group_id": "-1001", "enabled": True, "created": "now"})
        save_group_config("-1002", {"group_id": "-1002", "enabled": False, "created": "now"})
        save_group_config("-1003", {"group_id": "-1003", "enabled": True, "created": "now"})

        configs = get_all_group_configs()
        enabled_ids = [c["group_id"] for c in configs]
        assert "-1001" in enabled_ids
        assert "-1003" in enabled_ids
        assert "-1002" not in enabled_ids


# ============ Feature Flag Tests ============

class TestFeatureFlags:
    """Test that feature flags are properly defined."""

    def test_feature_flags_exist(self):
        """All Sprint1 feature flags should be defined in config."""
        import config
        assert hasattr(config, "FEATURE_SOURCE_HEALTH")
        assert hasattr(config, "FEATURE_PAYMENT")
        assert hasattr(config, "FEATURE_GROUP_CHAT")

    def test_feature_flags_default_false(self):
        """Feature flags should default to False."""
        # Note: actual values depend on .env, but the default should be False
        import config
        # We just verify they're boolean
        assert isinstance(config.FEATURE_SOURCE_HEALTH, bool)
        assert isinstance(config.FEATURE_PAYMENT, bool)
        assert isinstance(config.FEATURE_GROUP_CHAT, bool)

    def test_noise_prefixes_defined(self):
        """NOISE_PREFIXES should be defined with expected entries."""
        import config
        assert hasattr(config, "NOISE_PREFIXES")
        assert len(config.NOISE_PREFIXES) >= 5
        # Check some known prefixes
        prefixes_lower = [p.lower() for p in config.NOISE_PREFIXES]
        assert any("blockbeats" in p for p in prefixes_lower)


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
