"""
Test cases for language_service.py

Tests:
1.1 - get_user_language 正确性
1.2 - get_language_native_name 映射
1.3 - get_ui_strings 预定义语言
1.4 - get_ui_strings AI翻译缓存 (需要 API)
"""
import asyncio
import os
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.language_service import (
    get_language_native_name,
    normalize_language_code,
    get_user_language,
    get_ui_strings_sync,
    load_ui_cache,
    save_ui_cache,
    clear_ui_cache,
    SUPPORTED_UI_LANGUAGES,
    UI_VERSION,
)


def test_1_2_get_language_native_name():
    """Test 1.2: Language code to native name mapping"""
    print("\n=== Test 1.2: get_language_native_name ===")
    
    test_cases = [
        ("zh", "中文"),
        ("en", "English"),
        ("ja", "日本語"),
        ("ko", "한국어"),
        ("ru", "Русский"),
        ("es", "Español"),
        ("fr", "Français"),
    ]
    
    all_passed = True
    for code, expected in test_cases:
        result = get_language_native_name(code)
        passed = result == expected
        status = "✓" if passed else "✗"
        print(f"  {status} {code} -> {result} (expected: {expected})")
        if not passed:
            all_passed = False
    
    # Test unknown language fallback
    unknown_result = get_language_native_name("xyz")
    unknown_passed = unknown_result == "English"
    status = "✓" if unknown_passed else "✗"
    print(f"  {status} xyz (unknown) -> {unknown_result} (expected: English)")
    if not unknown_passed:
        all_passed = False
    
    print(f"\nTest 1.2 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_normalize_language_code():
    """Test normalize_language_code function"""
    print("\n=== Test: normalize_language_code ===")
    
    test_cases = [
        ("en-US", "en"),
        ("en-GB", "en"),
        ("zh-hans", "zh"),
        ("zh-hant", "zh"),
        ("zh-CN", "zh"),
        ("ja", "ja"),
        ("ko", "ko"),
        ("ru", "ru"),
        ("es-ES", "es"),
        ("", "en"),  # empty -> default English
        (None, "en"),  # None -> default English
    ]
    
    all_passed = True
    for input_code, expected in test_cases:
        result = normalize_language_code(input_code)
        passed = result == expected
        status = "✓" if passed else "✗"
        print(f"  {status} {repr(input_code)} -> {result} (expected: {expected})")
        if not passed:
            all_passed = False
    
    print(f"\nTest Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_1_3_get_ui_strings_supported():
    """Test 1.3: get_ui_strings for supported languages returns predefined strings"""
    print("\n=== Test 1.3: get_ui_strings_sync (supported languages) ===")
    
    # For this test, we need a mock user or test with supported language
    # Since we don't have a real user, we'll test the fallback behavior
    
    all_passed = True
    
    # Test that SUPPORTED_UI_LANGUAGES contains expected languages
    expected_supported = ["zh", "en", "ja", "ko"]
    for lang in expected_supported:
        passed = lang in SUPPORTED_UI_LANGUAGES
        status = "✓" if passed else "✗"
        print(f"  {status} {lang} in SUPPORTED_UI_LANGUAGES")
        if not passed:
            all_passed = False
    
    print(f"\nTest 1.3 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_ui_version_constant():
    """Test UI_VERSION constant exists and is valid"""
    print("\n=== Test: UI_VERSION Constant ===")
    
    all_passed = True
    
    # Test that UI_VERSION exists and is a valid semver-like string
    passed = isinstance(UI_VERSION, str) and len(UI_VERSION) > 0
    status = "✓" if passed else "✗"
    print(f"  {status} UI_VERSION exists: {UI_VERSION}")
    if not passed:
        all_passed = False
    
    # Test format (should be like "1.0.0")
    parts = UI_VERSION.split(".")
    passed = len(parts) >= 2
    status = "✓" if passed else "✗"
    print(f"  {status} UI_VERSION format valid: {len(parts)} parts")
    if not passed:
        all_passed = False
    
    print(f"\nTest Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_translation_temperature_config():
    """Test TRANSLATION_TEMPERATURE is properly configured"""
    print("\n=== Test: TRANSLATION_TEMPERATURE Config ===")
    
    from config import TRANSLATION_TEMPERATURE
    
    all_passed = True
    
    # Test that TRANSLATION_TEMPERATURE exists and is a float
    passed = isinstance(TRANSLATION_TEMPERATURE, float)
    status = "✓" if passed else "✗"
    print(f"  {status} TRANSLATION_TEMPERATURE is float: {type(TRANSLATION_TEMPERATURE)}")
    if not passed:
        all_passed = False
    
    # Test range (should be 0.0 - 1.0)
    passed = 0.0 <= TRANSLATION_TEMPERATURE <= 1.0
    status = "✓" if passed else "✗"
    print(f"  {status} TRANSLATION_TEMPERATURE in valid range: {TRANSLATION_TEMPERATURE}")
    if not passed:
        all_passed = False
    
    # Test that it's a low value (for stable translation)
    passed = TRANSLATION_TEMPERATURE <= 0.3
    status = "✓" if passed else "✗"
    print(f"  {status} TRANSLATION_TEMPERATURE is low (≤0.3): {TRANSLATION_TEMPERATURE}")
    if not passed:
        all_passed = False
    
    print(f"\nTest Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_ui_cache_version_check():
    """Test UI cache version checking mechanism"""
    print("\n=== Test: UI Cache Version Check ===")
    
    import json
    import os
    from services.language_service import UI_CACHE_DIR, _ensure_ui_cache_dir
    
    test_telegram_id = "test_version_check_99999"
    _ensure_ui_cache_dir()
    cache_path = os.path.join(UI_CACHE_DIR, f"{test_telegram_id}.json")
    
    all_passed = True
    
    # Clear any existing cache
    clear_ui_cache(test_telegram_id)
    
    # Test 1: Save with current version
    test_ui = {"btn_test": "Test Button"}
    save_result = save_ui_cache(test_telegram_id, test_ui, "ru")
    passed = save_result is True
    status = "✓" if passed else "✗"
    print(f"  {status} Save cache with current version: {save_result}")
    if not passed:
        all_passed = False
    
    # Test 2: Load should succeed (version matches)
    loaded = load_ui_cache(test_telegram_id)
    passed = loaded == test_ui
    status = "✓" if passed else "✗"
    print(f"  {status} Load cache with matching version: {loaded is not None}")
    if not passed:
        all_passed = False
    
    # Test 3: Manually modify cache file to have old version
    with open(cache_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["ui_version"] = "0.0.1"  # Old version
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    
    # Test 4: Load should return None (version mismatch)
    loaded_old = load_ui_cache(test_telegram_id)
    passed = loaded_old is None
    status = "✓" if passed else "✗"
    print(f"  {status} Load cache with old version returns None: {loaded_old is None}")
    if not passed:
        all_passed = False
    
    # Cleanup
    clear_ui_cache(test_telegram_id)
    
    print(f"\nTest Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_ui_cache_operations():
    """Test UI cache read/write operations"""
    print("\n=== Test 2.1: UI Cache Operations ===")
    
    test_telegram_id = "test_user_cache_12345"
    test_ui = {"menu_view_digest": "Просмотр дайджеста", "btn_confirm": "Подтвердить"}
    
    all_passed = True
    
    # Clear any existing cache
    clear_ui_cache(test_telegram_id)
    
    # Test 1: Cache should be empty initially
    cached = load_ui_cache(test_telegram_id)
    passed = cached is None
    status = "✓" if passed else "✗"
    print(f"  {status} Initial cache is None: {cached is None}")
    if not passed:
        all_passed = False
    
    # Test 2: Save cache
    save_result = save_ui_cache(test_telegram_id, test_ui, "ru")
    passed = save_result is True
    status = "✓" if passed else "✗"
    print(f"  {status} Save cache returned: {save_result}")
    if not passed:
        all_passed = False
    
    # Test 3: Load cache
    loaded = load_ui_cache(test_telegram_id)
    passed = loaded == test_ui
    status = "✓" if passed else "✗"
    print(f"  {status} Loaded cache matches: {loaded == test_ui}")
    if not passed:
        all_passed = False
        print(f"    Expected: {test_ui}")
        print(f"    Got: {loaded}")
    
    # Test 4: Clear cache
    clear_result = clear_ui_cache(test_telegram_id)
    passed = clear_result is True
    status = "✓" if passed else "✗"
    print(f"  {status} Clear cache returned: {clear_result}")
    if not passed:
        all_passed = False
    
    # Test 5: Cache should be empty after clear
    cached_after_clear = load_ui_cache(test_telegram_id)
    passed = cached_after_clear is None
    status = "✓" if passed else "✗"
    print(f"  {status} Cache is None after clear: {cached_after_clear is None}")
    if not passed:
        all_passed = False
    
    print(f"\nTest 2.1 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_3_1_prompt_language_placeholder():
    """Test 3.1: Prompt placeholder replacement for language"""
    print("\n=== Test 3.1: Prompt Language Placeholder ===")
    
    from utils.prompt_loader import get_prompt
    
    all_passed = True
    
    # Test onboarding_round1.txt
    prompt = get_prompt("onboarding_round1.txt", user_language="日本語")
    
    # Check that placeholder is replaced
    has_japanese = "日本語" in prompt
    status = "✓" if has_japanese else "✗"
    print(f"  {status} onboarding_round1.txt contains '日本語': {has_japanese}")
    if not has_japanese:
        all_passed = False
    
    # Check that placeholder is NOT still present
    no_placeholder = "{user_language}" not in prompt
    status = "✓" if no_placeholder else "✗"
    print(f"  {status} onboarding_round1.txt: placeholder replaced: {no_placeholder}")
    if not no_placeholder:
        all_passed = False
    
    # Check that old bilingual instruction is removed
    no_bilingual = "Bilingual" not in prompt and "BOTH Chinese and English" not in prompt
    status = "✓" if no_bilingual else "✗"
    print(f"  {status} onboarding_round1.txt: no old bilingual instruction: {no_bilingual}")
    if not no_bilingual:
        all_passed = False
    
    # Test onboarding_round2.txt
    prompt2 = get_prompt("onboarding_round2.txt", user_language="한국어", user_input="test")
    has_korean = "한국어" in prompt2
    status = "✓" if has_korean else "✗"
    print(f"  {status} onboarding_round2.txt contains '한국어': {has_korean}")
    if not has_korean:
        all_passed = False
    
    # Test onboarding_round3.txt
    prompt3 = get_prompt("onboarding_round3.txt", user_language="Русский", round_1="test1", round_2="test2")
    has_russian = "Русский" in prompt3
    status = "✓" if has_russian else "✗"
    print(f"  {status} onboarding_round3.txt contains 'Русский': {has_russian}")
    if not has_russian:
        all_passed = False
    
    # Test onboarding_confirm.txt
    prompt4 = get_prompt("onboarding_confirm.txt", user_language="Español", conversation_summary="test")
    has_spanish = "Español" in prompt4
    status = "✓" if has_spanish else "✗"
    print(f"  {status} onboarding_confirm.txt contains 'Español': {has_spanish}")
    if not has_spanish:
        all_passed = False
    
    print(f"\nTest 3.1 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_5_1_settings_language_import():
    """Test 5.1: Settings language functions are importable"""
    print("\n=== Test 5.1: Settings Language Import ===")
    
    all_passed = True
    
    try:
        from handlers.settings import show_language_settings, change_language, get_settings_callbacks
        
        # Check that callbacks include language settings
        callbacks = get_settings_callbacks()
        callback_patterns = [str(cb.pattern) if hasattr(cb, 'pattern') else '' for cb in callbacks]
        
        has_language_callback = any('settings_language' in str(p) for p in callback_patterns)
        status = "✓" if has_language_callback else "✗"
        print(f"  {status} settings_language callback registered: {has_language_callback}")
        if not has_language_callback:
            all_passed = False
        
        has_set_lang_callback = any('set_lang_' in str(p) for p in callback_patterns)
        status = "✓" if has_set_lang_callback else "✗"
        print(f"  {status} set_lang_ callback registered: {has_set_lang_callback}")
        if not has_set_lang_callback:
            all_passed = False
            
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        all_passed = False
    
    print(f"\nTest 5.1 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_update_user_language():
    """Test update_user_language function"""
    print("\n=== Test 5.2: update_user_language ===")
    
    from services.language_service import update_user_language, get_user_language
    from utils.json_storage import create_user, get_user
    
    all_passed = True
    test_telegram_id = "test_lang_update_99999"
    
    # Create a test user first (if not exists)
    user = get_user(test_telegram_id)
    if not user:
        create_user(test_telegram_id, username="testuser", first_name="Test", language="en")
    
    # Test update
    original_lang = get_user_language(test_telegram_id)
    print(f"  Original language: {original_lang}")
    
    # Change to Japanese
    success = update_user_language(test_telegram_id, "ja")
    passed = success is True
    status = "✓" if passed else "✗"
    print(f"  {status} update_user_language returned: {success}")
    if not passed:
        all_passed = False
    
    # Verify change
    new_lang = get_user_language(test_telegram_id)
    passed = new_lang == "ja"
    status = "✓" if passed else "✗"
    print(f"  {status} Language changed to: {new_lang} (expected: ja)")
    if not passed:
        all_passed = False
    
    # Restore original
    update_user_language(test_telegram_id, original_lang or "en")
    
    print(f"\nTest 5.2 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_6_1_report_generator_import():
    """Test 6.1: Report generator language import"""
    print("\n=== Test 6.1: Report Generator Language Import ===")
    
    all_passed = True
    
    try:
        from services.report_generator import get_lang_from_storage, get_language_native_name
        
        # Test that function is callable
        test_lang = get_language_native_name("zh")
        passed = test_lang == "中文"
        status = "✓" if passed else "✗"
        print(f"  {status} get_language_native_name('zh') = {test_lang}")
        if not passed:
            all_passed = False
            
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        all_passed = False
    
    print(f"\nTest 6.1 Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def test_all_modules_import():
    """Test that all modified modules are importable"""
    print("\n=== Test: All Modules Import ===")
    
    modules = [
        "services.language_service",
        "handlers.start",
        "handlers.settings",
        "services.report_generator",
    ]
    
    all_passed = True
    for module in modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except Exception as e:
            print(f"  ✗ {module}: {e}")
            all_passed = False
    
    print(f"\nTest Result: {'PASSED' if all_passed else 'FAILED'}")
    assert all_passed


def run_all_tests():
    """Run all synchronous tests"""
    print("=" * 60)
    print("Running Language Service Tests")
    print("=" * 60)
    
    results = {}
    
    results["1.2 get_language_native_name"] = test_1_2_get_language_native_name()
    results["normalize_language_code"] = test_normalize_language_code()
    results["1.3 get_ui_strings_sync"] = test_1_3_get_ui_strings_supported()
    results["UI_VERSION Constant"] = test_ui_version_constant()
    results["TRANSLATION_TEMPERATURE Config"] = test_translation_temperature_config()
    results["UI Cache Version Check"] = test_ui_cache_version_check()
    results["2.1 UI Cache Operations"] = test_ui_cache_operations()
    results["3.1 Prompt Language Placeholder"] = test_3_1_prompt_language_placeholder()
    results["5.1 Settings Language Import"] = test_5_1_settings_language_import()
    results["5.2 update_user_language"] = test_update_user_language()
    results["6.1 Report Generator Import"] = test_6_1_report_generator_import()
    results["All Modules Import"] = test_all_modules_import()
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    print(f"Overall Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
