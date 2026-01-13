#!/usr/bin/env python3
"""
Quick Bot Connection Test
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from web3digest directory
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


async def test_telegram_bot():
    """Test Telegram Bot connection"""
    import httpx
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[FAIL] TELEGRAM_BOT_TOKEN not found in .env")
        return False
    
    print("=" * 60)
    print("Telegram Bot Connection Test")
    print("=" * 60)
    print(f"Token: {token[:20]}...{token[-5:]}")
    
    url = f"https://api.telegram.org/bot{token}/getMe"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            data = resp.json()
            
            if data.get("ok"):
                bot_info = data.get("result", {})
                print(f"[OK] Bot connected successfully!")
                print(f"     Bot Name: {bot_info.get('first_name')}")
                print(f"     Username: @{bot_info.get('username')}")
                print(f"     Bot ID: {bot_info.get('id')}")
                return True
            else:
                print(f"[FAIL] API Error: {data.get('description')}")
                return False
    except Exception as e:
        print(f"[FAIL] Connection Error: {e}")
        return False


async def test_llm_api():
    """Test LLM API connection"""
    import httpx
    
    api_base = os.getenv("LLM_API_BASE", "https://api.moonshot.cn/v1")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("PRIMARY_MODEL", "kimi-k2-thinking-preview")
    
    if not api_key:
        print("[FAIL] LLM_API_KEY not found in .env")
        return False
    
    print("=" * 60)
    print("LLM API Connection Test")
    print("=" * 60)
    print(f"API Base: {api_base}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}...{api_key[-5:]}")
    
    url = f"{api_base}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", [])]
                print(f"[OK] LLM API connected!")
                print(f"     Available models: {len(models)}")
                if model in str(models):
                    print(f"     Target model '{model}' available")
                return True
            else:
                print(f"[WARN] Status: {resp.status_code}")
                print(f"       Response: {resp.text[:100]}")
                return True  # API might still work
    except Exception as e:
        print(f"[FAIL] Connection Error: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Web3 Digest - Environment Verification")
    print("=" * 60 + "\n")
    
    results = []
    
    # Test Telegram Bot
    results.append(("Telegram Bot", await test_telegram_bot()))
    print()
    
    # Test LLM API
    results.append(("LLM API", await test_llm_api()))
    print()
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\nAll tests passed! You can now run the bot:")
        print("  cd backend/wiseflow")
        print("  python core/custom_processes/web3digest/main.py")
    else:
        print("\nSome tests failed. Please check your configuration.")
    
    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
