"""
End-to-End Simulation Tests

Simulates real user Telegram operations through the full handler pipeline.
Uses realistic Telegram-like objects to verify complete flows:
1. Bot startup smoke test (handler registration)
2. Group /setup → AI onboarding → push time → language → save (full flow)
3. Admin CTA configuration (edit → save → reset)
4. Group digest CTA integration

Run with: python -m pytest tests/test_e2e_simulation.py -v --tb=long
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============ Realistic Telegram Object Factory ============

def make_user(user_id=111222333, username="groupadmin", first_name="Admin", language_code="zh"):
    """Build a User-like object mimicking telegram.User."""
    u = MagicMock()
    u.id = user_id
    u.username = username
    u.first_name = first_name
    u.last_name = None
    u.language_code = language_code
    u.is_bot = False
    u.full_name = first_name
    return u


def make_chat(chat_id=-1001234567890, chat_type="supergroup", title="Web3 DeFi 讨论群"):
    """Build a Chat-like object mimicking telegram.Chat."""
    c = MagicMock()
    c.id = chat_id
    c.type = chat_type
    c.title = title
    c.send_action = AsyncMock()
    return c


def make_message(user, chat, text="", message_id=100):
    """Build a Message-like object."""
    m = MagicMock()
    m.text = text
    m.from_user = user
    m.chat = chat
    m.chat_id = chat.id
    m.message_id = message_id
    m.reply_text = AsyncMock(return_value=MagicMock(message_id=message_id + 1, delete=AsyncMock()))
    m.edit_text = AsyncMock()
    m.delete = AsyncMock()
    return m


def make_callback_query(user, message, data=""):
    """Build a CallbackQuery-like object."""
    q = MagicMock()
    q.id = f"cb_{data}_{user.id}"
    q.from_user = user
    q.message = message
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    return q


def make_update(user, chat, message=None, callback_query=None):
    """Build an Update-like object."""
    u = MagicMock()
    u.effective_user = user
    u.effective_chat = chat
    if message is None:
        message = make_message(user, chat)
    u.message = message
    u.callback_query = callback_query
    return u


def make_context(admin_user_id=111222333):
    """Build a Context with realistic bot mock."""
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.chat_data = {}
    ctx.bot_data = {}
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=200))
    ctx.bot.edit_message_text = AsyncMock()

    admin_member = MagicMock()
    admin_member.user = MagicMock()
    admin_member.user.id = admin_user_id
    ctx.bot.get_chat_administrators = AsyncMock(return_value=[admin_member])
    ctx.bot.send_invoice = AsyncMock()
    return ctx


# ============ Test 1: Bot Startup Smoke Test ============

class TestBotStartup:
    """Verify bot can initialize and register all handlers without errors."""

    def test_all_handlers_importable(self):
        """E2E-01: All handler modules import cleanly."""
        from handlers.start import get_start_handler, get_start_callbacks
        from handlers.feedback import get_feedback_handlers
        from handlers.settings import get_settings_handler, get_settings_callbacks
        from handlers.sources import get_sources_handler, get_sources_callbacks
        from handlers.admin import get_admin_handlers
        from handlers.payment import get_payment_handlers
        from handlers.group import get_group_handler, get_group_callbacks

        assert callable(get_start_handler)
        assert callable(get_group_handler)
        assert callable(get_admin_handlers)

    def test_group_handler_registration(self):
        """E2E-02: Group handler creates valid ConversationHandler."""
        from handlers.group import get_group_handler
        from telegram.ext import ConversationHandler

        with patch("config.FEATURE_GROUP_CHAT", True):
            handler = get_group_handler()

        assert isinstance(handler, ConversationHandler)
        assert len(handler.entry_points) >= 1
        assert len(handler.states) == 6
        assert handler.conversation_timeout == 600

    def test_admin_handlers_include_cta(self):
        """E2E-03: Admin handlers include CTA callbacks."""
        from handlers.admin import get_admin_handlers

        with patch("config.ADMIN_TELEGRAM_IDS", ["345396984"]):
            handlers = get_admin_handlers()

        handler_patterns = []
        for h in handlers:
            if hasattr(h, "pattern") and h.pattern:
                handler_patterns.append(h.pattern.pattern if hasattr(h.pattern, "pattern") else str(h.pattern))

        cta_found = any("admin_cta" in p for p in handler_patterns)
        assert cta_found, f"CTA handlers not found in admin handlers. Patterns: {handler_patterns}"

    def test_main_module_imports(self):
        """E2E-04: main.py imports succeed (no circular imports or missing deps)."""
        import importlib
        import config
        assert hasattr(config, "FEATURE_GROUP_CHAT")
        assert hasattr(config, "TELEGRAM_BOT_TOKEN")

        from handlers.group import get_group_handler, get_group_callbacks
        from handlers.admin import get_admin_handlers, DEFAULT_CTA_TEXT
        from utils.json_storage import get_system_config, set_system_config

        assert DEFAULT_CTA_TEXT is not None


# ============ Test 2: Full Group /setup E2E Flow ============

class TestGroupSetupE2E:
    """Simulate full /setup flow: command → 3 AI rounds → push time → language → save."""

    @pytest.mark.asyncio
    async def test_full_setup_flow_new_group(self, tmp_data_dir):
        """E2E-05: Complete new group setup from /setup to config saved."""
        from handlers.group import (
            setup_command, handle_onboard_r1, handle_onboard_r2,
            handle_confirm_profile, handle_push_time, handle_language_choice,
            load_group_config, GROUP_ONBOARD_R1, GROUP_ONBOARD_R2,
            GROUP_CONFIRM_PROFILE, GROUP_PUSH_TIME, GROUP_LANGUAGE,
        )
        from telegram.ext import ConversationHandler

        admin = make_user(111222333, "groupadmin", "Admin", "zh")
        group_chat = make_chat(-1001234567890, "supergroup", "Web3 DeFi 讨论群")
        ctx = make_context(111222333)

        # ---- Step 1: /setup command ----
        msg1 = make_message(admin, group_chat, "/setup")
        upd1 = make_update(admin, group_chat, message=msg1)

        with patch("config.FEATURE_GROUP_CHAT", True):
            with patch("handlers.group.call_gemini", new_callable=AsyncMock,
                        return_value="你好！请告诉我，你们群主要关注 Web3 的哪些领域？例如 DeFi、NFT、Layer2 等？"):
                result = await setup_command(upd1, ctx)

        assert result == GROUP_ONBOARD_R1, f"Expected GROUP_ONBOARD_R1, got {result}"
        assert ctx.chat_data["setup_admin_id"] == 111222333
        assert ctx.chat_data["current_round"] == 1
        print(f"  ✓ Step 1: /setup → AI Round 1 question sent (state={result})")

        # ---- Step 2: Admin round 1 reply ----
        msg2 = make_message(admin, group_chat, "我们群主要关注 DeFi 协议和 Layer2，比如 Uniswap、Arbitrum、Optimism")
        upd2 = make_update(admin, group_chat, message=msg2)

        with patch("handlers.group.call_gemini", new_callable=AsyncMock,
                    return_value="了解！那关于内容类型呢？你们更喜欢深度分析、快讯还是项目评测？每天大概想看多少条？"):
            result = await handle_onboard_r1(upd2, ctx)

        assert result == GROUP_ONBOARD_R2, f"Expected GROUP_ONBOARD_R2, got {result}"
        assert len(ctx.chat_data["conversation_history"]) == 1
        assert ctx.chat_data["current_round"] == 2
        print(f"  ✓ Step 2: Round 1 reply → AI Round 2 question sent (state={result})")

        # ---- Step 3: Admin round 2 reply (generates profile summary) ----
        msg3 = make_message(admin, group_chat, "深度分析为主，每天 10-15 条就够了，不要太多快讯")
        msg3.reply_text = AsyncMock(side_effect=[
            MagicMock(message_id=301, delete=AsyncMock()),
            MagicMock(message_id=302),
        ])
        upd3 = make_update(admin, group_chat, message=msg3)

        mock_profile_summary = (
            "📋 群组偏好总结：\n"
            "- 主要关注：DeFi 协议（Uniswap, Aave）、Layer2（Arbitrum, Optimism）\n"
            "- 内容偏好：深度分析为主，少量快讯\n"
            "- 每日数量：10-15 条\n"
            "- 不感兴趣：纯营销内容"
        )

        with patch("handlers.group.call_gemini", new_callable=AsyncMock,
                    return_value=mock_profile_summary):
            result = await handle_onboard_r2(upd3, ctx)

        assert result == GROUP_CONFIRM_PROFILE, f"Expected GROUP_CONFIRM_PROFILE, got {result}"
        assert ctx.chat_data["profile_summary"] == mock_profile_summary
        assert len(ctx.chat_data["conversation_history"]) == 2
        print(f"  ✓ Step 3: Round 2 reply → Profile summary generated (state={result})")

        # ---- Step 4: Admin confirms profile ----
        msg4 = make_message(admin, group_chat)
        cb4 = make_callback_query(admin, msg4, "group_confirm_profile")
        upd4 = make_update(admin, group_chat, message=msg4, callback_query=cb4)
        upd4.callback_query = cb4

        mock_full_profile = (
            "[群组类型]\n"
            "DeFi / Layer2 深度研究群\n\n"
            "[关注领域]\n"
            "- DeFi: Uniswap, Aave, Compound, Curve\n"
            "- Layer2: Arbitrum, Optimism, zkSync\n\n"
            "[内容偏好]\n"
            "- 深度分析 > 项目评测 > 快讯\n"
            "- 每日 10-15 条\n\n"
            "[排除]\n"
            "- 纯营销推广\n"
            "- Meme 币"
        )

        with patch("handlers.group.call_gemini", new_callable=AsyncMock,
                    return_value=mock_full_profile):
            result = await handle_confirm_profile(upd4, ctx)

        assert result == GROUP_PUSH_TIME, f"Expected GROUP_PUSH_TIME, got {result}"
        assert ctx.chat_data["full_profile"] == mock_full_profile
        print(f"  ✓ Step 4: Confirm profile → Full AI profile generated (state={result})")

        # ---- Step 5: Select push time ----
        msg5 = make_message(admin, group_chat)
        cb5 = make_callback_query(admin, msg5, "group_time_9")
        upd5 = make_update(admin, group_chat, message=msg5, callback_query=cb5)
        upd5.callback_query = cb5

        result = await handle_push_time(upd5, ctx)

        assert result == GROUP_LANGUAGE, f"Expected GROUP_LANGUAGE, got {result}"
        assert ctx.chat_data["push_hour"] == 9
        print(f"  ✓ Step 5: Selected 9:00 push time (state={result})")

        # ---- Step 6: Select language & save ----
        msg6 = make_message(admin, group_chat)
        cb6 = make_callback_query(admin, msg6, "group_lang_zh")
        upd6 = make_update(admin, group_chat, message=msg6, callback_query=cb6)
        upd6.callback_query = cb6

        result = await handle_language_choice(upd6, ctx)

        assert result == ConversationHandler.END, f"Expected END, got {result}"
        print(f"  ✓ Step 6: Selected 中文, config saved (state=END)")

        # ---- Verify persisted config ----
        group_id = str(group_chat.id)
        saved_config = load_group_config(group_id)

        assert saved_config is not None, "Config should be saved to disk"
        assert saved_config["group_id"] == group_id
        assert saved_config["group_title"] == "Web3 DeFi 讨论群"
        assert saved_config["admin_id"] == "111222333"
        assert saved_config["push_hour"] == 9
        assert saved_config["language"] == "zh"
        assert saved_config["enabled"] is True
        assert "[群组类型]" in saved_config["profile"]
        assert "DeFi" in saved_config["profile"]
        print(f"  ✓ Step 7: Config verified on disk — all fields correct")

        print("\n  ✅ Full group /setup E2E flow PASSED")

    @pytest.mark.asyncio
    async def test_non_admin_blocked_at_every_step(self, tmp_data_dir):
        """E2E-06: Non-admin user is blocked at every interactive step."""
        from handlers.group import (
            handle_onboard_r1, handle_onboard_r2,
            handle_confirm_profile, handle_push_time, handle_language_choice,
            GROUP_ONBOARD_R1, GROUP_ONBOARD_R2,
            GROUP_CONFIRM_PROFILE, GROUP_PUSH_TIME, GROUP_LANGUAGE,
        )

        admin = make_user(111222333, "groupadmin", "Admin", "zh")
        member = make_user(999888777, "member1", "Member", "en")
        group_chat = make_chat(-1001234567890, "supergroup", "Test Group")
        ctx = make_context(111222333)
        ctx.chat_data["setup_admin_id"] = 111222333
        ctx.chat_data["conversation_history"] = [
            {"round": 1, "user_input": "DeFi"},
        ]
        ctx.chat_data["language"] = "zh"
        ctx.chat_data["language_native"] = "Chinese"
        ctx.chat_data["profile_summary"] = "Test profile"

        # Non-admin message in Round 1
        msg = make_message(member, group_chat, "I also want NFT news!")
        upd = make_update(member, group_chat, message=msg)
        result = await handle_onboard_r1(upd, ctx)
        assert result == GROUP_ONBOARD_R1
        print("  ✓ Non-admin blocked in Round 1")

        # Non-admin message in Round 2
        result = await handle_onboard_r2(upd, ctx)
        assert result == GROUP_ONBOARD_R2
        print("  ✓ Non-admin blocked in Round 2")

        # Non-admin callback for confirm
        cb = make_callback_query(member, msg, "group_confirm_profile")
        upd_cb = make_update(member, group_chat, callback_query=cb)
        upd_cb.callback_query = cb
        result = await handle_confirm_profile(upd_cb, ctx)
        assert result == GROUP_CONFIRM_PROFILE
        cb.answer.assert_called_once()
        print("  ✓ Non-admin blocked at confirm profile")

        # Non-admin callback for push time
        cb_time = make_callback_query(member, msg, "group_time_9")
        upd_time = make_update(member, group_chat, callback_query=cb_time)
        upd_time.callback_query = cb_time
        result = await handle_push_time(upd_time, ctx)
        assert result == GROUP_PUSH_TIME
        print("  ✓ Non-admin blocked at push time")

        # Non-admin callback for language
        cb_lang = make_callback_query(member, msg, "group_lang_zh")
        upd_lang = make_update(member, group_chat, callback_query=cb_lang)
        upd_lang.callback_query = cb_lang
        result = await handle_language_choice(upd_lang, ctx)
        assert result == GROUP_LANGUAGE
        print("  ✓ Non-admin blocked at language selection")

        print("\n  ✅ Non-admin blocking E2E PASSED (all 5 steps verified)")

    @pytest.mark.asyncio
    async def test_setup_existing_config_view_and_disable(self, tmp_data_dir):
        """E2E-07: Existing group → view config → disable push."""
        from handlers.group import (
            setup_command, handle_group_view, handle_group_disable,
            save_group_config, load_group_config, GROUP_ONBOARD_R1,
        )
        from telegram.ext import ConversationHandler

        admin = make_user(111222333)
        group_chat = make_chat(-1009999999, "supergroup", "Existing Group")
        ctx = make_context(111222333)

        save_group_config("-1009999999", {
            "group_id": "-1009999999",
            "group_title": "Existing Group",
            "admin_id": "111222333",
            "profile": "[群组类型]\nDeFi 分析群",
            "push_hour": 8,
            "language": "zh",
            "enabled": True,
            "created": "2026-02-22T10:00:00",
        })

        msg = make_message(admin, group_chat, "/setup")
        upd = make_update(admin, group_chat, message=msg)

        with patch("config.FEATURE_GROUP_CHAT", True):
            result = await setup_command(upd, ctx)
        assert result == GROUP_ONBOARD_R1
        print("  ✓ Existing group /setup shows options")

        # View config
        msg_v = make_message(admin, group_chat)
        cb_v = make_callback_query(admin, msg_v, "group_view")
        upd_v = make_update(admin, group_chat, callback_query=cb_v)
        upd_v.callback_query = cb_v
        result = await handle_group_view(upd_v, ctx)
        assert result == ConversationHandler.END
        cb_v.edit_message_text.assert_called_once()
        view_text = cb_v.edit_message_text.call_args[0][0]
        assert "DeFi" in view_text
        print("  ✓ View shows correct config details")

        # Disable
        msg_d = make_message(admin, group_chat)
        cb_d = make_callback_query(admin, msg_d, "group_disable")
        upd_d = make_update(admin, group_chat, callback_query=cb_d)
        upd_d.callback_query = cb_d
        result = await handle_group_disable(upd_d, ctx)
        assert result == ConversationHandler.END

        config = load_group_config("-1009999999")
        assert config["enabled"] is False
        print("  ✓ Disable set enabled=False")

        print("\n  ✅ Existing group view/disable E2E PASSED")


# ============ Test 3: Admin CTA Configuration E2E ============

class TestAdminCTAE2E:
    """Simulate full admin CTA configuration flow."""

    @pytest.mark.asyncio
    async def test_full_cta_config_flow(self, tmp_data_dir, monkeypatch):
        """E2E-08: Admin configures CTA: view → edit → save → verify in digest."""
        import utils.json_storage as storage
        monkeypatch.setattr(storage, "SYSTEM_CONFIG_FILE",
                            str(tmp_data_dir / "system_config.json"))

        from handlers.admin import (
            admin_cta_config, admin_cta_edit, handle_cta_text_input,
            admin_cta_reset, DEFAULT_CTA_TEXT, WAITING_FOR_CTA_TEXT,
        )
        from telegram.ext import ConversationHandler

        admin = make_user(345396984, "platformadmin", "PlatformAdmin", "zh")

        # ---- Step 1: View current CTA (should be default) ----
        msg1 = make_message(admin, make_chat(345396984, "private"))
        cb1 = make_callback_query(admin, msg1, "admin_cta_config")
        upd1 = make_update(admin, msg1.chat, callback_query=cb1)
        upd1.callback_query = cb1

        with patch("handlers.admin.is_admin", return_value=True):
            await admin_cta_config(upd1, MagicMock(bot=MagicMock()))

        view_text = cb1.edit_message_text.call_args[0][0]
        assert "/start" in view_text
        print(f"  ✓ Step 1: View CTA shows default text containing /start")

        # ---- Step 2: Click edit ----
        msg2 = make_message(admin, make_chat(345396984, "private"))
        cb2 = make_callback_query(admin, msg2, "admin_cta_edit")
        upd2 = make_update(admin, msg2.chat, callback_query=cb2)
        upd2.callback_query = cb2
        ctx2 = make_context()

        with patch("handlers.admin.is_admin", return_value=True):
            with patch("utils.conv_manager.activate_conv"):
                result = await admin_cta_edit(upd2, ctx2)
        assert result == WAITING_FOR_CTA_TEXT
        print(f"  ✓ Step 2: Click edit → awaiting text input (state={result})")

        # ---- Step 3: Input new CTA text ----
        custom_cta = "🚀 加入我们的社区！私聊 /start 获取个性化 Web3 资讯\nJoin our community! DM /start for personalized Web3 news"
        msg3 = make_message(admin, make_chat(345396984, "private"), custom_cta)
        upd3 = make_update(admin, msg3.chat, message=msg3)
        ctx3 = make_context()

        with patch("handlers.admin.is_admin", return_value=True):
            result = await handle_cta_text_input(upd3, ctx3)
        assert result == ConversationHandler.END
        print(f"  ✓ Step 3: Input CTA text → saved (state=END)")

        # ---- Step 4: Verify saved ----
        saved_cta = storage.get_system_config("group_cta_text")
        assert saved_cta == custom_cta
        print(f"  ✓ Step 4: Verified CTA persisted to system_config.json")

        # ---- Step 5: Verify group_digest_push_job would use custom CTA ----
        cta_for_digest = storage.get_system_config("group_cta_text", DEFAULT_CTA_TEXT)
        assert cta_for_digest == custom_cta
        assert "个性化" in cta_for_digest
        print(f"  ✓ Step 5: Digest push would use custom CTA text")

        # ---- Step 6: Reset to default ----
        msg6 = make_message(admin, make_chat(345396984, "private"))
        cb6 = make_callback_query(admin, msg6, "admin_cta_reset")
        upd6 = make_update(admin, msg6.chat, callback_query=cb6)
        upd6.callback_query = cb6

        with patch("handlers.admin.is_admin", return_value=True):
            with patch("handlers.admin.admin_cta_config", new_callable=AsyncMock):
                await admin_cta_reset(upd6, MagicMock())

        reset_cta = storage.get_system_config("group_cta_text")
        assert reset_cta == DEFAULT_CTA_TEXT
        print(f"  ✓ Step 6: Reset → CTA restored to default")

        print("\n  ✅ Full CTA configuration E2E flow PASSED")

    @pytest.mark.asyncio
    async def test_cta_validation_boundaries(self, tmp_data_dir, monkeypatch):
        """E2E-09: CTA input validation — too short, too long, edge cases."""
        import utils.json_storage as storage
        monkeypatch.setattr(storage, "SYSTEM_CONFIG_FILE",
                            str(tmp_data_dir / "system_config.json"))

        from handlers.admin import handle_cta_text_input, WAITING_FOR_CTA_TEXT
        from telegram.ext import ConversationHandler

        admin = make_user(345396984)

        # Too short (< 5 chars)
        msg = make_message(admin, make_chat(345396984, "private"), "abc")
        upd = make_update(admin, msg.chat, message=msg)
        ctx = make_context()
        with patch("handlers.admin.is_admin", return_value=True):
            result = await handle_cta_text_input(upd, ctx)
        assert result == WAITING_FOR_CTA_TEXT
        assert storage.get_system_config("group_cta_text") is None
        print("  ✓ Too short (3 chars) → rejected, nothing saved")

        # Too long (> 500 chars)
        msg2 = make_message(admin, make_chat(345396984, "private"), "X" * 501)
        upd2 = make_update(admin, msg2.chat, message=msg2)
        with patch("handlers.admin.is_admin", return_value=True):
            result = await handle_cta_text_input(upd2, ctx)
        assert result == WAITING_FOR_CTA_TEXT
        assert storage.get_system_config("group_cta_text") is None
        print("  ✓ Too long (501 chars) → rejected, nothing saved")

        # Exact boundary: 5 chars (should pass)
        msg3 = make_message(admin, make_chat(345396984, "private"), "Hello")
        upd3 = make_update(admin, msg3.chat, message=msg3)
        with patch("handlers.admin.is_admin", return_value=True):
            result = await handle_cta_text_input(upd3, ctx)
        assert result == ConversationHandler.END
        assert storage.get_system_config("group_cta_text") == "Hello"
        print("  ✓ Boundary (5 chars) → accepted and saved")

        # Exact boundary: 500 chars (should pass)
        text_500 = "Y" * 500
        storage.set_system_config("group_cta_text", None)
        msg4 = make_message(admin, make_chat(345396984, "private"), text_500)
        upd4 = make_update(admin, msg4.chat, message=msg4)
        with patch("handlers.admin.is_admin", return_value=True):
            result = await handle_cta_text_input(upd4, ctx)
        assert result == ConversationHandler.END
        assert storage.get_system_config("group_cta_text") == text_500
        print("  ✓ Boundary (500 chars) → accepted and saved")

        print("\n  ✅ CTA validation boundaries E2E PASSED")


# ============ Test 4: Group Digest CTA Integration ============

class TestDigestCTAIntegration:
    """Verify the CTA is correctly fetched in group digest push context."""

    def test_digest_footer_with_custom_cta(self, tmp_data_dir, monkeypatch):
        """E2E-10: Simulate digest push building footer with custom CTA."""
        import utils.json_storage as storage
        monkeypatch.setattr(storage, "SYSTEM_CONFIG_FILE",
                            str(tmp_data_dir / "system_config.json"))

        from handlers.admin import DEFAULT_CTA_TEXT

        custom_cta = "🔥 快来试试！私聊 /start 获取你的专属简报"
        storage.set_system_config("group_cta_text", custom_cta)

        cta_text = storage.get_system_config("group_cta_text", DEFAULT_CTA_TEXT)
        footer = (
            "\n\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"{cta_text}\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )

        assert custom_cta in footer
        assert "━━━" in footer
        print("  ✓ Digest footer contains custom CTA with separators")

    def test_digest_footer_with_default_cta(self, tmp_data_dir, monkeypatch):
        """E2E-11: Simulate digest push with no custom CTA (fallback to default)."""
        import utils.json_storage as storage
        monkeypatch.setattr(storage, "SYSTEM_CONFIG_FILE",
                            str(tmp_data_dir / "system_config.json"))

        from handlers.admin import DEFAULT_CTA_TEXT

        cta_text = storage.get_system_config("group_cta_text", DEFAULT_CTA_TEXT)
        assert cta_text == DEFAULT_CTA_TEXT
        assert "/start" in cta_text
        print("  ✓ Digest footer falls back to default CTA with /start")


# ============ Test 5: Prompt Files + AI Call Chain ============

class TestAICallChain:
    """Verify the AI call chain is correct for group onboarding."""

    @pytest.mark.asyncio
    async def test_prompt_loading_with_variables(self):
        """E2E-12: Prompt files load and format with variables correctly."""
        from utils.prompt_loader import get_prompt

        r1 = get_prompt("group_onboarding_round1.txt", user_language="Chinese")
        assert "Chinese" in r1
        assert "group" in r1.lower() or "GROUP" in r1

        r2 = get_prompt("group_onboarding_round2.txt",
                         user_input="DeFi and Layer2", user_language="Chinese")
        assert "DeFi and Layer2" in r2

        r3 = get_prompt("group_onboarding_round3.txt",
                         round_1="DeFi", round_2="deep analysis", user_language="Chinese")
        assert "DeFi" in r3
        assert "deep analysis" in r3

        confirm = get_prompt("group_onboarding_confirm.txt",
                              user_language="Chinese",
                              conversation_summary="DeFi group summary")
        assert "DeFi group summary" in confirm
        print("  ✓ All 4 prompt files load and format correctly with variables")

    @pytest.mark.asyncio
    async def test_ai_error_graceful_handling(self, tmp_data_dir):
        """E2E-13: AI failure during setup is handled gracefully (no crash)."""
        from handlers.group import setup_command, GROUP_ONBOARD_R1
        from telegram.ext import ConversationHandler

        admin = make_user(111222333)
        group_chat = make_chat(-1001234567890, "supergroup", "Error Test Group")
        ctx = make_context(111222333)

        msg = make_message(admin, group_chat, "/setup")
        upd = make_update(admin, group_chat, message=msg)

        with patch("config.FEATURE_GROUP_CHAT", True):
            with patch("handlers.group.call_gemini", new_callable=AsyncMock,
                        side_effect=Exception("API timeout")):
                result = await setup_command(upd, ctx)

        assert result == ConversationHandler.END
        msg.reply_text.assert_called()
        print("  ✓ AI failure → graceful error message, no crash (state=END)")
